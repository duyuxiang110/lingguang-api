"""
认证服务 — 注册/登录/刷新/登出/改密/忘记密码/会话验证。
移植自 electron/server/services/authService.js
"""
import uuid
from datetime import datetime, timedelta

import bcrypt
import jwt

from app.config import (
    JWT_SECRET, JWT_REFRESH_SECRET, JWT_ACCESS_EXPIRY, JWT_REFRESH_EXPIRY,
    BCRYPT_ROUNDS, MAX_LOGIN_ATTEMPTS, LOGIN_LOCK_TIME_MIN,
)
from app.db import query


def _hash_password(password_md5: str) -> str:
    return bcrypt.hashpw(password_md5.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


def _verify_password(password_md5: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password_md5.encode(), password_hash.encode())


def _generate_tokens(user: dict, device_info: str = None, ip_address: str = None) -> dict:
    access_token = jwt.encode(
        {"userId": user["id"], "username": user["username"], "role": user["role"]},
        JWT_SECRET, algorithm="HS256",
    )
    refresh_token = jwt.encode(
        {"userId": user["id"], "type": "refresh"},
        JWT_REFRESH_SECRET, algorithm="HS256",
    )
    expires_at = datetime.now() + timedelta(days=7)
    query(
        "INSERT INTO refresh_tokens (user_id, token, device_info, ip_address, expires_at) VALUES (%s, %s, %s, %s, %s)",
        [user["id"], refresh_token, device_info, ip_address, expires_at],
    )
    return {"accessToken": access_token, "refreshToken": refresh_token}


def _log_login(user_id, username, ip_address, device_info, action, detail):
    try:
        query(
            "INSERT INTO login_logs (user_id, username, ip_address, device_info, action, detail) VALUES (%s, %s, %s, %s, %s, %s)",
            [user_id, username, ip_address, device_info, action, detail],
        )
    except Exception as e:
        print(f"[Auth] 记录日志失败: {e}")


def register(username: str, email: str, password: str, phone: str = None) -> dict:
    existing = query("SELECT id FROM users WHERE username = %s OR email = %s", [username, email])
    if existing:
        raise ValueError("用户名或邮箱已被注册")
    password_hash = _hash_password(password)
    result = query(
        "INSERT INTO users (username, email, password_hash, phone, role, status) VALUES (%s, %s, %s, %s, 'user', 'pending')",
        [username, email, password_hash, phone],
    )
    return {"id": result, "username": username, "email": email, "role": "user"}


def login(username: str, password: str, device_info: str, ip_address: str) -> dict:
    users = query("SELECT * FROM users WHERE username = %s OR email = %s", [username, username])
    if not users:
        _log_login(None, username, ip_address, device_info, "login_failed", "用户不存在")
        raise ValueError("用户名或密码错误")
    user = users[0]

    if user["status"] == "inactive":
        _log_login(user["id"], username, ip_address, device_info, "login_failed", "账户已被限制登录")
        raise PermissionError("您的账户已被限制登录，请联系管理员")

    if user["status"] == "pending":
        _log_login(user["id"], username, ip_address, device_info, "login_failed", "账户待管理员审核")
        raise PermissionError("您的账户正在等待管理员审核，请耐心等待")

    if user["status"] == "locked" or (user.get("locked_until") and user["locked_until"] > datetime.now()):
        remain = max(1, int((user["locked_until"] - datetime.now()).total_seconds() // 60))
        raise PermissionError(f"账户已锁定，请 {remain} 分钟后重试")

    if not _verify_password(password, user["password_hash"]):
        attempts = (user.get("login_attempts") or 0) + 1
        if attempts >= MAX_LOGIN_ATTEMPTS:
            locked_until = datetime.now() + timedelta(minutes=LOGIN_LOCK_TIME_MIN)
            query("UPDATE users SET login_attempts=%s, locked_until=%s, status='locked' WHERE id=%s", [attempts, locked_until, user["id"]])
            _log_login(user["id"], username, ip_address, device_info, "login_failed", "密码错误次数过多，账户已锁定")
            raise PermissionError("密码错误次数过多，账户已锁定15分钟")
        query("UPDATE users SET login_attempts=%s WHERE id=%s", [attempts, user["id"]])
        _log_login(user["id"], username, ip_address, device_info, "login_failed", f"密码错误 ({attempts}/{MAX_LOGIN_ATTEMPTS})")
        raise ValueError(f"用户名或密码错误 (剩余 {MAX_LOGIN_ATTEMPTS - attempts} 次机会)")

    query("UPDATE users SET login_attempts=0, locked_until=NULL, status='active', last_login_at=NOW(), last_login_ip=%s WHERE id=%s", [ip_address, user["id"]])
    tokens = _generate_tokens(user, device_info, ip_address)
    session_id = str(uuid.uuid4())
    session_expiry = datetime.now() + timedelta(hours=24)
    query("INSERT INTO sessions (session_id, user_id, ip_address, user_agent, expires_at) VALUES (%s, %s, %s, %s, %s)", [session_id, user["id"], ip_address, device_info, session_expiry])
    _log_login(user["id"], username, ip_address, device_info, "login_success", "登录成功")

    return {
        "user": {"id": user["id"], "username": user["username"], "email": user["email"], "role": user["role"], "avatar": user.get("avatar"), "phone": user.get("phone"), "lastLoginAt": user.get("last_login_at")},
        **tokens,
        "sessionId": session_id,
    }


def refresh_token(token: str, ip_address: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_REFRESH_SECRET, algorithms=["HS256"])
    except Exception:
        raise ValueError("Refresh Token 无效或已过期")

    tokens = query("SELECT * FROM refresh_tokens WHERE token = %s AND user_id = %s AND expires_at > NOW()", [token, payload["userId"]])
    if not tokens:
        raise ValueError("Token 已失效，请重新登录")

    users = query("SELECT * FROM users WHERE id = %s AND status = 'active'", [payload["userId"]])
    if not users:
        raise ValueError("用户不存在或已被禁用")
    user = users[0]

    query("DELETE FROM refresh_tokens WHERE token = %s", [token])
    new_tokens = _generate_tokens(user, None, ip_address)
    _log_login(user["id"], user["username"], ip_address, None, "token_refresh", "Token 刷新")

    return {
        "user": {"id": user["id"], "username": user["username"], "email": user["email"], "role": user["role"], "avatar": user.get("avatar")},
        **new_tokens,
    }


def logout(user_id: int, session_id: str = None, refresh_token: str = None):
    if refresh_token:
        query("DELETE FROM refresh_tokens WHERE token = %s AND user_id = %s", [refresh_token, user_id])
    if session_id:
        query("UPDATE sessions SET is_active = 0 WHERE session_id = %s AND user_id = %s", [session_id, user_id])
    users = query("SELECT username FROM users WHERE id = %s", [user_id])
    if users:
        _log_login(user_id, users[0]["username"], None, None, "logout", "用户登出")


def change_password(user_id: int, old_password: str, new_password: str) -> dict:
    users = query("SELECT * FROM users WHERE id = %s", [user_id])
    if not users:
        raise ValueError("用户不存在")
    user = users[0]
    if not _verify_password(old_password, user["password_hash"]):
        raise ValueError("原密码错误")
    new_hash = _hash_password(new_password)
    query("UPDATE users SET password_hash = %s WHERE id = %s", [new_hash, user_id])
    query("DELETE FROM refresh_tokens WHERE user_id = %s", [user_id])
    query("UPDATE sessions SET is_active = 0 WHERE user_id = %s", [user_id])
    _log_login(user_id, user["username"], None, None, "password_change", "密码已修改")
    return {"message": "密码修改成功，请重新登录"}


def forgot_password(username: str, email: str, new_password: str, ip_address: str = None) -> dict:
    users = query("SELECT * FROM users WHERE username = %s AND email = %s", [username, email])
    if not users:
        raise ValueError("用户名与邮箱不匹配，请核对后重试")
    user = users[0]
    if user["status"] == "inactive":
        raise PermissionError("账户已被限制登录，请联系管理员")
    new_hash = _hash_password(new_password)
    new_status = "active" if user["status"] == "locked" else user["status"]
    query("UPDATE users SET password_hash=%s, login_attempts=0, locked_until=NULL, status=%s WHERE id=%s", [new_hash, new_status, user["id"]])
    query("DELETE FROM refresh_tokens WHERE user_id = %s", [user["id"]])
    query("UPDATE sessions SET is_active = 0 WHERE user_id = %s", [user["id"]])
    _log_login(user["id"], username, ip_address, None, "password_change", "忘记密码自助重置")
    return {"message": "密码重置成功，请使用新密码登录"}


def validate_session(session_id: str) -> dict | None:
    sessions = query(
        "SELECT s.*, u.username, u.email, u.role, u.avatar FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.session_id = %s AND s.is_active = 1 AND s.expires_at > NOW()",
        [session_id],
    )
    if not sessions:
        return None
    query("UPDATE sessions SET last_activity = NOW() WHERE session_id = %s", [session_id])
    return sessions[0]
