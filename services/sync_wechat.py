# -*- coding: utf8 -*-
"""微信步数同步服务，封装 Zepp Life 接口调用"""
import uuid
import util.zepp_helper as zeppHelper


def sync_wechat_steps(username, password, steps):
    """
    同步步数到 Zepp Life
    :param username: 微信运动账号（邮箱或手机号）
    :param password: 账号密码
    :param steps: 目标步数
    :return: (success: bool, message: str)
    """
    user = str(username).strip()
    pwd = str(password)
    if not user or not pwd:
        return False, "账号或密码为空"
    try:
        steps = int(steps)
        if steps < 1 or steps > 98800:
            return False, "步数范围应在 1~98800 之间"
    except (TypeError, ValueError):
        return False, "步数格式不正确"

    # 手机号自动加 +86 前缀
    if not user.startswith("+86") and "@" not in user:
        user = "+86" + user
    is_phone = user.startswith("+86")
    device_id = str(uuid.uuid4())

    try:
        # 步骤1: 账号密码登录获取 access_token
        access_token, msg = zeppHelper.login_access_token(user, pwd)
        if access_token is None:
            return False, f"登录失败: {msg}"
        # 步骤2: 获取 login_token / app_token / user_id
        login_token, app_token, user_id, msg = zeppHelper.grant_login_tokens(
            access_token, device_id, is_phone)
        if login_token is None:
            return False, f"获取登录令牌失败: {msg}"
        # 步骤3: 提交步数
        ok, msg = zeppHelper.post_fake_brand_data(str(steps), app_token, user_id)
        if ok:
            return True, f"修改步数成功: {steps} 步"
        return False, f"修改步数失败: {msg}"
    except Exception as e:
        return False, f"执行异常: {e}"
