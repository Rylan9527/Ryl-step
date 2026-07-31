# -*- coding: utf8 -*-
"""定时调度服务：基于 APScheduler，启动时自动加载所有启用的自动任务

调度器时区统一使用北京时间（Asia/Shanghai），确保 CronTrigger 的 hour/minute
按北京时间解析，避免因容器/服务器本地时区差异导致执行时间不对。
"""
import os
import random
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from models import database as db
from services.sync_wechat import sync_wechat_steps
from services.crypto import decrypt_password

# 统一调度时区：北京时间
_SCHEDULER_TZ = 'Asia/Shanghai'

# 日志配置：输出到 sync.log
logger = logging.getLogger('sync')
logger.setLevel(logging.INFO)
_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sync.log')
_fh = logging.FileHandler(_log_path, encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(_fh)

scheduler = None


def _job_id(task_id, hour):
    return f"task_{task_id}_h{hour}"


def run_task(task_id):
    """定时任务执行入口：随机步数 + 同步 + 失败重试1次 + 记录历史"""
    task = db.get_auto_task(task_id)
    if task is None:
        logger.warning(f"任务 {task_id} 不存在，跳过")
        return
    if not task['enabled']:
        logger.info(f"任务 {task_id} 已停用，跳过")
        return
    account = db.get_account(task['account_id'])
    if account is None:
        logger.warning(f"任务 {task_id} 关联账号不存在")
        return
    try:
        pwd = decrypt_password(account['password_encrypted'])
    except Exception as e:
        db.add_sync_history(account['id'], account['username'], 0, 'fail', f"解密密码失败: {e}", 'auto')
        db.update_auto_task_status(task_id, 'fail')
        logger.error(f"账号 {account['username']} 解密密码失败: {e}")
        return

    # 范围步数随机，固定步数直接取
    if task['steps_max']:
        steps = random.randint(task['steps_min'], task['steps_max'])
    else:
        steps = task['steps_min']

    logger.info(f"自动同步开始: 账号={account['username']} 步数={steps}")
    success, msg = sync_wechat_steps(account['username'], pwd, steps)
    # 失败重试1次
    if not success:
        logger.warning(f"首次同步失败，重试1次: {account['username']} 原因={msg}")
        success, msg = sync_wechat_steps(account['username'], pwd, steps)

    if success:
        db.add_sync_history(account['id'], account['username'], steps, 'success', msg, 'auto')
        db.update_auto_task_status(task_id, 'success')
        logger.info(f"自动同步成功: {account['username']} {msg}")
    else:
        db.add_sync_history(account['id'], account['username'], steps, 'fail', msg, 'auto')
        db.update_auto_task_status(task_id, 'fail')
        logger.error(f"自动同步失败: {account['username']} {msg}")


def schedule_task(task):
    """为单个任务添加定时 job（按 exec_hours 中每个小时各建一个）"""
    if not task['enabled']:
        return
    hours = [h.strip() for h in str(task['exec_hours']).split(',') if h.strip()]
    for h in hours:
        try:
            hour = int(h)
        except ValueError:
            logger.warning(f"任务 {task['id']} 执行时间配置无效: {h}")
            continue
        trigger = CronTrigger(hour=hour, minute=task['exec_minute'], timezone=_SCHEDULER_TZ)
        scheduler.add_job(run_task, trigger, args=[task['id']],
                          id=_job_id(task['id'], hour), replace_existing=True)
        logger.info(f"任务 {task['id']} 已调度: 每天北京时间 {hour:02d}:{task['exec_minute']:02d}")


def unschedule_task(task_id):
    """移除某任务的所有定时 job"""
    jobs = scheduler.get_jobs()
    prefix = f"task_{task_id}_h"
    for job in jobs:
        if job.id.startswith(prefix):
            scheduler.remove_job(job.id)


def reschedule_task(task_id):
    """更新任务后重新调度"""
    unschedule_task(task_id)
    task = db.get_auto_task(task_id)
    if task and task['enabled']:
        schedule_task(task)


def init_scheduler():
    """初始化调度器并加载所有启用任务（防止重复初始化）"""
    global scheduler
    if scheduler is not None:
        return scheduler
    scheduler = BackgroundScheduler(timezone=_SCHEDULER_TZ)
    scheduler.start()
    tasks = db.list_auto_tasks()
    count = 0
    for t in tasks:
        if t['enabled']:
            schedule_task(t)
            count += 1
    logger.info(f"调度器初始化完成，共加载 {count} 个启用任务 (时区={_SCHEDULER_TZ})")
    return scheduler


def shutdown_scheduler():
    """关闭调度器"""
    global scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
