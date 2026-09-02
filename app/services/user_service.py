"""
用户管理服务 — CRUD/权限/统计/日志/状态管理。
移植自 electron/server/services/userService.js
"""
import bcrypt

from app.config import BCRYPT_ROUNDS
from app.db import query


def get_users(page=1, page_size=20, keyword="", role="", status=""):
    offset = (page - 1) * page_size
    where = "WHERE 1=1"
    params = []
    if keyword:
        where += " AND (username LIKE %s OR email LIKE %s)"
        params += [f"%{keyword}%", f"%{keyword}%"]
    if role:
        where += " AND role = %s"
        params.append(role)
    if status:
        where += " AND status = %s"
        params.append(status)

    count = query(f"SELECT COUNT(*) as total FROM users {where}", params)
    total = count[0]["total"] if count else 0
    users = query(
        f"""SELECT id, username, email, avatar, phone, role, status, login_attempts,
                  locked_until, last_login_at, last_login_ip, created_at, updated_at
           FROM users {where} ORDER BY created_at DESC LIMIT %s OFFSET %s""",
        params + [page_size, offset],
    )
    return {"users": users, "total": total, "page": page, "pageSize": page_size, "totalPages": (total + page_size - 1) // page_size}


def get_user_by_id(user_id: int) -> dict:
    users = query(
        """SELECT id, username, email, avatar, phone, role, status,
                  last_login_at, last_login_ip, created_at, updated_at
           FROM users WHERE id = %s""",
        [user_id],
    )
    if not users:
        raise ValueError("用户不存在")
    return users[0]


def update_user(user_id: int, email=None, phone=None, avatar=None, role=None, status=None) -> dict:
    fields, params = [], []
    for k, v in [("email", email), ("phone", phone), ("avatar", avatar), ("role", role), ("status", status)]:
        if v is not None:
            fields.append(f"{k} = %s")
            params.append(v)
    if not fields:
        raise ValueError("没有需要更新的字段")
    params.append(user_id)
    query(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", params)
    return get_user_by_id(user_id)


def delete_user(user_id: int) -> dict:
    users = query("SELECT id, username, role FROM users WHERE id = %s", [user_id])
    if not users:
        raise ValueError("用户不存在")
    if users[0]["role"] == "admin":
        raise PermissionError("不能删除管理员账户")
    query("DELETE FROM refresh_tokens WHERE user_id = %s", [user_id])
    query("DELETE FROM sessions WHERE user_id = %s", [user_id])
    query("DELETE FROM login_logs WHERE user_id = %s", [user_id])
    query("DELETE FROM users WHERE id = %s", [user_id])
    return {"message": f"用户 {users[0]['username']} 及其所有关联数据已删除"}


def unlock_user(user_id: int) -> dict:
    query("UPDATE users SET status = 'active', login_attempts = 0, locked_until = NULL WHERE id = %s", [user_id])
    return {"message": "用户已解锁"}


def restrict_user(user_id: int) -> dict:
    users = query("SELECT id, username, role FROM users WHERE id = %s", [user_id])
    if not users:
        raise ValueError("用户不存在")
    if users[0]["role"] == "admin":
        raise PermissionError("不能限制管理员账户")
    query("UPDATE users SET status = 'inactive' WHERE id = %s", [user_id])
    query("DELETE FROM refresh_tokens WHERE user_id = %s", [user_id])
    query("UPDATE sessions SET is_active = 0 WHERE user_id = %s", [user_id])
    return {"message": f"用户 {users[0]['username']} 已被限制登录"}


def unrestrict_user(user_id: int) -> dict:
    users = query("SELECT id, username FROM users WHERE id = %s", [user_id])
    if not users:
        raise ValueError("用户不存在")
    query("UPDATE users SET status = 'active', login_attempts = 0, locked_until = NULL WHERE id = %s", [user_id])
    return {"message": f"用户 {users[0]['username']} 已解除限制"}


def approve_user(user_id: int) -> dict:
    users = query("SELECT id, username, status FROM users WHERE id = %s", [user_id])
    if not users:
        raise ValueError("用户不存在")
    if users[0]["status"] != "pending":
        raise ValueError("该账户无需审核")
    query("UPDATE users SET status = 'active' WHERE id = %s", [user_id])
    return {"message": f"用户 {users[0]['username']} 已通过审核，可以登录了"}


def reset_password(user_id: int, new_password: str) -> dict:
    password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
    query("UPDATE users SET password_hash = %s WHERE id = %s", [password_hash, user_id])
    query("DELETE FROM refresh_tokens WHERE user_id = %s", [user_id])
    query("UPDATE sessions SET is_active = 0 WHERE user_id = %s", [user_id])
    return {"message": "密码已重置，用户需重新登录"}


def get_user_permissions(user_id: int) -> list:
    users = query("SELECT role FROM users WHERE id = %s", [user_id])
    if not users:
        return []
    return query(
        "SELECT p.code, p.name, p.description FROM role_permissions rp JOIN permissions p ON rp.permission_id = p.id WHERE rp.role = %s",
        [users[0]["role"]],
    )


def get_login_logs(page=1, page_size=50, user_id=None, action=""):
    offset = (page - 1) * page_size
    where = "WHERE 1=1"
    params = []
    if user_id:
        where += " AND l.user_id = %s"
        params.append(user_id)
    if action:
        where += " AND l.action = %s"
        params.append(action)
    count = query(f"SELECT COUNT(*) as total FROM login_logs l {where}", params)
    total = count[0]["total"] if count else 0
    logs = query(
        f"""SELECT l.*, u.username as user_username FROM login_logs l
            LEFT JOIN users u ON l.user_id = u.id {where}
            ORDER BY l.created_at DESC LIMIT %s OFFSET %s""",
        params + [page_size, offset],
    )
    return {"logs": logs, "total": total, "page": page, "pageSize": page_size}


def get_stats() -> dict:
    total = query("SELECT COUNT(*) as count FROM users")[0]["count"]
    active = query("SELECT COUNT(*) as count FROM users WHERE status = 'active'")[0]["count"]
    locked = query("SELECT COUNT(*) as count FROM users WHERE status = 'locked'")[0]["count"]
    sessions = query("SELECT COUNT(*) as count FROM sessions WHERE is_active = 1 AND expires_at > NOW()")[0]["count"]
    today = query("SELECT COUNT(*) as count FROM login_logs WHERE action = 'login_success' AND DATE(created_at) = CURDATE()")[0]["count"]
    return {"totalUsers": total, "activeUsers": active, "lockedUsers": locked, "activeSessions": sessions, "todayLogins": today}
