# -*- coding: utf8 -*-
"""Flask 主程序：登录认证 + 手动同步 + 自动管理 + 批量导入 + 历史记录"""
import os
import io
import random
import traceback
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, jsonify, send_file,
                   redirect, url_for, Response, session, g)

from models import database as db
from services.crypto import encrypt_password, decrypt_password
from services.sync_wechat import sync_wechat_steps
from services import scheduler as sched

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'zepp-life-step-manager-secret-key-2026')


# ==================== 登录认证 ====================
def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_current_user():
    """向所有模板注入当前用户信息"""
    current_user = None
    if 'user_id' in session:
        user = db.get_user_by_id(session['user_id'])
        if user:
            current_user = {'id': user['id'], 'username': user['username'], 'role': user['role']}
    return {'current_user': current_user}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            return render_template('login.html', error='账号和密码不能为空')

        user = db.get_user(username)
        if user is None:
            return render_template('login.html', error='账号或密码错误')

        try:
            decrypted = decrypt_password(user['password_encrypted'])
            if decrypted == password:
                session['user_id'] = user['id']
                session['username'] = user['username']
                next_url = request.args.get('next') or url_for('index')
                return redirect(next_url)
            else:
                return render_template('login.html', error='账号或密码错误')
        except Exception:
            return render_template('login.html', error='账号或密码错误')

    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ==================== 用户管理 ====================
@app.route('/user/manage')
@login_required
def user_manage():
    users = db.list_users()
    return render_template('user_manage.html', active='users', users=users)


@app.route('/user/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pwd = request.form.get('current_password', '').strip()
        new_pwd = request.form.get('new_password', '').strip()
        confirm_pwd = request.form.get('confirm_password', '').strip()

        user = db.get_user_by_id(session['user_id'])
        try:
            decrypted = decrypt_password(user['password_encrypted'])
            if decrypted != current_pwd:
                return render_template('change_password.html', error='当前密码错误')
        except Exception:
            return render_template('change_password.html', error='密码验证失败')

        if not new_pwd or len(new_pwd) < 6:
            return render_template('change_password.html', error='新密码至少6位')

        if new_pwd != confirm_pwd:
            return render_template('change_password.html', error='两次新密码不一致')

        db.update_user_password(user['username'], encrypt_password(new_pwd))
        return redirect(url_for('user_manage', msg='密码修改成功'))

    return render_template('change_password.html', active='change_pwd')


@app.route('/api/users', methods=['POST'])
@login_required
def api_add_user():
    """创建新用户"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'user')

    if not username or not password:
        return jsonify({"success": False, "message": "账号和密码不能为空"})

    if len(password) < 6:
        return jsonify({"success": False, "message": "密码至少6位"})

    existing = db.get_user(username)
    if existing:
        return jsonify({"success": False, "message": "账号已存在"})

    db.add_user(username, encrypt_password(password), role)
    return jsonify({"success": True, "message": "用户创建成功"})


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def api_delete_user(user_id):
    """删除用户"""
    if user_id == session['user_id']:
        return jsonify({"success": False, "message": "不能删除自己"})
    db.delete_user(user_id)
    return jsonify({"success": True, "message": "用户已删除"})


@app.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
def api_reset_user_password(user_id):
    """重置用户密码"""
    data = request.get_json()
    new_password = data.get('password', '').strip()
    if not new_password or len(new_password) < 6:
        return jsonify({"success": False, "message": "密码至少6位"})
    user = db.get_user_by_id(user_id)
    if not user:
        return jsonify({"success": False, "message": "用户不存在"})
    db.update_user_password(user['username'], encrypt_password(new_password))
    return jsonify({"success": True, "message": "密码重置成功"})


# ==================== 原有路由（保持不变，添加登录验证） ====================
@app.route('/')
@login_required
def index():
    return render_template('index.html', active='manual')


@app.route('/api/status')
def api_status():
    return jsonify({"online": True})


@app.route('/api/sync-step', methods=['POST'])
@login_required
def sync_step():
    """原有手动同步接口，保留并增加历史记录"""
    data = request.get_json()
    user = data.get('user', '').strip()
    pwd = data.get('pwd', '').strip()
    step = data.get('step', '')

    if not user or not pwd:
        return jsonify({"success": False, "message": "账号和密码不能为空"})

    try:
        step = int(step)
        if step < 1 or step > 98800:
            return jsonify({"success": False, "message": "步数范围应在 1~98800 之间"})
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "步数格式不正确"})

    # 记录到历史表（手动同步）
    account = db.get_account_by_username(user)
    account_id = account['id'] if account else None

    success, msg = sync_wechat_steps(user, pwd, step)
    db.add_sync_history(account_id, user, step, 'success' if success else 'fail',
                        msg, 'manual')

    if success:
        return jsonify({"success": True, "message": msg, "step": step})
    return jsonify({"success": False, "message": msg})


# ==================== 自动任务管理 ====================
@app.route('/auto/manage')
@login_required
def auto_manage():
    return render_template('auto_manage.html', active='auto')


@app.route('/api/auto/tasks')
@login_required
def api_list_tasks():
    tasks = db.list_auto_tasks()
    result = []
    for t in tasks:
        result.append({
            "id": t['id'],
            "account_id": t['account_id'],
            "username": db.desensitize(t['username']),
            "steps_min": t['steps_min'],
            "steps_max": t['steps_max'],
            "enabled": bool(t['enabled']),
            "exec_hours": t['exec_hours'],
            "exec_minute": t['exec_minute'],
            "last_sync_status": t['last_sync_status'],
            "last_sync_time": t['last_sync_time'],
        })
    return jsonify(result)


@app.route('/api/auto/tasks', methods=['POST'])
@login_required
def api_add_task():
    data = request.get_json()
    user = data.get('username', '').strip()
    pwd = data.get('password', '').strip()
    steps_min = data.get('steps_min')
    steps_max = data.get('steps_max')
    enabled = data.get('enabled', True)
    exec_hours = data.get('exec_hours', '8')
    exec_minute = int(data.get('exec_minute', 0))

    if not user or not pwd:
        return jsonify({"success": False, "message": "账号和密码不能为空"})
    try:
        steps_min = int(steps_min)
        if steps_max not in (None, '', 0):
            steps_max = int(steps_max)
            if steps_max < steps_min:
                return jsonify({"success": False, "message": "最大步数不能小于最小步数"})
        else:
            steps_max = None
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "步数格式不正确"})

    # 保存账号（加密密码）
    account_id = db.add_account(user, encrypt_password(pwd))
    # 若该账号已有任务则更新，否则新增
    existing = [t for t in db.list_auto_tasks() if t['account_id'] == account_id]
    if existing:
        task_id = existing[0]['id']
        db.update_auto_task(task_id, steps_min, steps_max, enabled, exec_hours, exec_minute)
    else:
        task_id = db.add_auto_task(account_id, steps_min, steps_max, enabled, exec_hours, exec_minute)

    # 同步到调度器
    db.set_auto_task_enabled(task_id, enabled)
    sched.reschedule_task(task_id)
    return jsonify({"success": True, "message": "任务保存成功", "id": task_id})


@app.route('/api/auto/tasks/<int:task_id>', methods=['PUT'])
@login_required
def api_update_task(task_id):
    data = request.get_json()
    task = db.get_auto_task(task_id)
    if task is None:
        return jsonify({"success": False, "message": "任务不存在"})

    pwd = data.get('password', '').strip()
    steps_min = int(data.get('steps_min', task['steps_min']))
    steps_max = data.get('steps_max')
    if steps_max in (None, '', 0):
        steps_max = None
    else:
        steps_max = int(steps_max)
        if steps_max < steps_min:
            return jsonify({"success": False, "message": "最大步数不能小于最小步数"})
    enabled = data.get('enabled', bool(task['enabled']))
    exec_hours = data.get('exec_hours', task['exec_hours'])
    exec_minute = int(data.get('exec_minute', task['exec_minute']))

    # 若提供了新密码则更新
    if pwd:
        account = db.get_account(task['account_id'])
        if account:
            db.add_account(account['username'], encrypt_password(pwd))

    db.update_auto_task(task_id, steps_min, steps_max, enabled, exec_hours, exec_minute)
    sched.reschedule_task(task_id)
    return jsonify({"success": True, "message": "任务更新成功"})


@app.route('/api/auto/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def api_delete_task(task_id):
    sched.unschedule_task(task_id)
    db.delete_auto_task(task_id)
    return jsonify({"success": True, "message": "任务已删除"})


@app.route('/api/auto/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
def api_toggle_task(task_id):
    task = db.get_auto_task(task_id)
    if task is None:
        return jsonify({"success": False, "message": "任务不存在"})
    new_enabled = not bool(task['enabled'])
    db.set_auto_task_enabled(task_id, new_enabled)
    sched.reschedule_task(task_id)
    return jsonify({"success": True, "message": "已启用" if new_enabled else "已停用",
                    "enabled": new_enabled})


@app.route('/api/auto/tasks/<int:task_id>/run', methods=['POST'])
@login_required
def api_run_task_now(task_id):
    """立即执行一次自动任务"""
    task = db.get_auto_task(task_id)
    if task is None:
        return jsonify({"success": False, "message": "任务不存在"})
    account = db.get_account(task['account_id'])
    if account is None:
        return jsonify({"success": False, "message": "账号不存在"})
    try:
        pwd = decrypt_password(account['password_encrypted'])
    except Exception as e:
        return jsonify({"success": False, "message": f"解密密码失败: {e}"})
    if task['steps_max']:
        steps = random.randint(task['steps_min'], task['steps_max'])
    else:
        steps = task['steps_min']
    success, msg = sync_wechat_steps(account['username'], pwd, steps)
    db.add_sync_history(account['id'], account['username'], steps,
                        'success' if success else 'fail', msg, 'auto')
    db.update_auto_task_status(task_id, 'success' if success else 'fail')
    return jsonify({"success": success, "message": msg, "steps": steps})


# ==================== 批量导入 ====================
@app.route('/batch/import')
@login_required
def batch_import():
    return render_template('batch_import.html', active='batch')


@app.route('/batch/template')
def batch_template():
    """下载 CSV 模板"""
    content = "username,password,steps_min,steps_max,enable\n"
    return Response(content, mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=batch_template.csv"})


@app.route('/batch/import', methods=['POST'])
@login_required
def batch_import_process():
    """处理上传的 CSV/Excel 文件"""
    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"success": False, "message": "请选择文件"})

    filename = file.filename.lower()
    rows = []
    try:
        if filename.endswith('.csv'):
            import csv as csvmod
            stream = io.TextIOWrapper(file.stream, encoding='utf-8-sig')
            reader = csvmod.DictReader(stream)
            rows = list(reader)
        elif filename.endswith(('.xlsx', '.xls')):
            import pandas as pd
            df = pd.read_excel(file.stream)
            rows = df.to_dict('records')
        else:
            return jsonify({"success": False, "message": "仅支持 CSV 或 Excel(.xlsx) 文件"})
    except Exception as e:
        return jsonify({"success": False, "message": f"文件解析失败: {e}"})

    success_count = 0
    fail_count = 0
    errors = []
    for i, row in enumerate(rows, start=2):  # 第2行开始（第1行表头）
        try:
            user = str(row.get('username', '')).strip()
            pwd = str(row.get('password', '')).strip()
            steps_min = row.get('steps_min')
            steps_max = row.get('steps_max')
            enable = row.get('enable', 1)

            if not user or not pwd:
                errors.append(f"第{i}行: 账号或密码为空")
                fail_count += 1
                continue
            try:
                steps_min = int(steps_min)
            except (TypeError, ValueError):
                errors.append(f"第{i}行: 最小步数格式错误")
                fail_count += 1
                continue
            if steps_max in (None, '', 0, 'nan'):
                steps_max = None
            else:
                steps_max = int(steps_max)
            enable = int(enable) if str(enable).strip() not in ('', 'nan') else 1
            enabled = enable == 1

            account_id = db.add_account(user, encrypt_password(pwd))
            existing = [t for t in db.list_auto_tasks() if t['account_id'] == account_id]
            if existing:
                task_id = existing[0]['id']
                db.update_auto_task(task_id, steps_min, steps_max, enabled, '8', 0)
            else:
                task_id = db.add_auto_task(account_id, steps_min, steps_max, enabled, '8', 0)
            sched.reschedule_task(task_id)
            success_count += 1
        except Exception as e:
            errors.append(f"第{i}行: {e}")
            fail_count += 1

    msg = f"导入完成：成功 {success_count} 条，失败 {fail_count} 条"
    if errors:
        msg += "\n失败详情:\n" + "\n".join(errors[:20])
        if len(errors) > 20:
            msg += f"\n...等共 {len(errors)} 条失败"
    return jsonify({"success": True, "message": msg,
                    "success_count": success_count, "fail_count": fail_count,
                    "errors": errors[:50]})


# ==================== 历史记录 ====================
@app.route('/history')
@login_required
def history():
    page = int(request.args.get('page', 1))
    username = request.args.get('username', '')
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    per_page = 20

    rows, total = db.list_sync_history(
        username=username or None,
        status=status or None,
        date_from=date_from or None,
        date_to=date_to or None,
        page=page, per_page=per_page)

    total_pages = (total + per_page - 1) // per_page
    records = [{
        "id": r['id'],
        "username": db.desensitize(r['username']),
        "steps": r['steps'],
        "sync_time": r['sync_time'],
        "status": r['status'],
        "error_msg": r['error_msg'],
        "sync_type": r['sync_type']
    } for r in rows]

    return render_template('history.html', active='history',
                           records=records, page=page, total_pages=total_pages,
                           total=total, username=username, status=status,
                           date_from=date_from, date_to=date_to)


# ==================== Jinja 过滤器 ====================
@app.template_filter('desensitize')
def desensitize_filter(username):
    return db.desensitize(username)


@app.template_filter('mask_user')
def mask_user_filter(username):
    return db.desensitize(username)


# ==================== 启动初始化 ====================
def init_default_user():
    """初始化默认管理员账号"""
    user = db.get_user('Rylan')
    if user is None:
        db.add_user('Rylan', encrypt_password('8876678'), role='admin')
        print("[INIT] 默认管理员 Rylan 已创建")


def init_app():
    """初始化数据库与调度器"""
    db.init_db()
    init_default_user()
    sched.init_scheduler()


# 防止 Flask debug 模式 reloader 重复初始化调度器
if __name__ == '__main__':
    db.init_db()
    init_default_user()
    # 仅在主进程（非 reloader 子进程）启动调度器
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        sched.init_scheduler()
    app.run(debug=True, host='0.0.0.0', port=5000)
