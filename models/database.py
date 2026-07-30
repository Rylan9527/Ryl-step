# -*- coding: utf8 -*-
"""数据库模块：accounts / auto_tasks / sync_history 三张表及 CRUD"""
import sqlite3
import os
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'mimotion.db')


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库表，若已存在则跳过"""
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_encrypted TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS auto_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        steps_min INTEGER NOT NULL,
        steps_max INTEGER,
        enabled INTEGER DEFAULT 1,
        exec_hours TEXT DEFAULT '8',
        exec_minute INTEGER DEFAULT 0,
        next_run_time TEXT,
        last_sync_status TEXT,
        last_sync_time TEXT,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER,
        username TEXT,
        steps INTEGER,
        sync_time TEXT DEFAULT CURRENT_TIMESTAMP,
        status TEXT,
        error_msg TEXT,
        sync_type TEXT
    );
    """)
    conn.commit()
    conn.close()


# ---------------- accounts ----------------
def add_account(username, encrypted_pwd):
    """新增账号，若已存在则更新密码，返回 account id"""
    conn = get_conn()
    cur = conn.cursor()
    existing = cur.execute("SELECT id FROM accounts WHERE username=?", (username,)).fetchone()
    if existing:
        cur.execute("UPDATE accounts SET password_encrypted=? WHERE id=?", (encrypted_pwd, existing['id']))
        conn.commit()
        account_id = existing['id']
    else:
        cur.execute("INSERT INTO accounts(username, password_encrypted) VALUES(?,?)",
                    (username, encrypted_pwd))
        conn.commit()
        account_id = cur.lastrowid
    conn.close()
    return account_id


def get_account(account_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    conn.close()
    return row


def get_account_by_username(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
    conn.close()
    return row


def list_accounts():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
    conn.close()
    return rows


# ---------------- auto_tasks ----------------
def add_auto_task(account_id, steps_min, steps_max, enabled, exec_hours, exec_minute=0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO auto_tasks(account_id, steps_min, steps_max, enabled, exec_hours, exec_minute)
                   VALUES(?,?,?,?,?,?)""",
                (account_id, steps_min, steps_max, 1 if enabled else 0, exec_hours, exec_minute))
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id


def update_auto_task(task_id, steps_min, steps_max, enabled, exec_hours, exec_minute=0):
    conn = get_conn()
    conn.execute("""UPDATE auto_tasks SET steps_min=?, steps_max=?, enabled=?, exec_hours=?, exec_minute=?
                    WHERE id=?""",
                 (steps_min, steps_max, 1 if enabled else 0, exec_hours, exec_minute, task_id))
    conn.commit()
    conn.close()


def delete_auto_task(task_id):
    conn = get_conn()
    conn.execute("DELETE FROM auto_tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()


def get_auto_task(task_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM auto_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return row


def list_auto_tasks():
    """返回任务列表（关联账号信息）"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.*, a.username, a.password_encrypted
        FROM auto_tasks t LEFT JOIN accounts a ON t.account_id = a.id
        ORDER BY t.id
    """).fetchall()
    conn.close()
    return rows


def set_auto_task_enabled(task_id, enabled):
    conn = get_conn()
    conn.execute("UPDATE auto_tasks SET enabled=? WHERE id=?", (1 if enabled else 0, task_id))
    conn.commit()
    conn.close()


def update_auto_task_status(task_id, status):
    conn = get_conn()
    conn.execute("UPDATE auto_tasks SET last_sync_status=?, last_sync_time=? WHERE id=?",
                 (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), task_id))
    conn.commit()
    conn.close()


# ---------------- sync_history ----------------
def add_sync_history(account_id, username, steps, status, error_msg, sync_type):
    conn = get_conn()
    conn.execute("""INSERT INTO sync_history(account_id, username, steps, sync_time, status, error_msg, sync_type)
                    VALUES(?,?,?,?,?,?,?)""",
                 (account_id, username, steps, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  status, error_msg, sync_type))
    conn.commit()
    conn.close()


def list_sync_history(username=None, status=None, date_from=None, date_to=None, page=1, per_page=20):
    """分页查询历史记录，按时间倒序"""
    conditions = []
    params = []
    if username:
        conditions.append("username LIKE ?")
        params.append(f"%{username}%")
    if status:
        conditions.append("status=?")
        params.append(status)
    if date_from:
        conditions.append("sync_time >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("sync_time <= ?")
        params.append(date_to + " 23:59:59")
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * per_page
    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) AS c FROM sync_history{where}", params).fetchone()['c']
    rows = conn.execute(f"SELECT * FROM sync_history{where} ORDER BY sync_time DESC LIMIT ? OFFSET ?",
                        params + [per_page, offset]).fetchall()
    conn.close()
    return rows, total


# ---------------- 工具函数 ----------------
def desensitize(username):
    """账号脱敏：前2后2可见，中间用 * 号"""
    s = str(username)
    if len(s) <= 4:
        return s[:1] + "***" + s[-1:] if len(s) > 1 else s
    return s[:2] + "*" * (len(s) - 4) + s[-2:]
