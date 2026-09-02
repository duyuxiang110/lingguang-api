"""
登录 IP 限流 — 内存级，1分钟5次失败→锁定IP 10分钟。
移植自 electron/server/middleware/loginLimiter.js
"""
import time
from collections import defaultdict

from app.config import LOGIN_RATE_LIMIT_WINDOW_SEC, LOGIN_RATE_LIMIT_MAX, LOGIN_IP_LOCK_MIN

_attempts: dict[str, list[float]] = defaultdict(list)
_locked: dict[str, float] = {}


def record_failure(ip: str):
    now = time.time()
    _attempts[ip].append(now)
    cutoff = now - LOGIN_RATE_LIMIT_WINDOW_SEC
    _attempts[ip] = [t for t in _attempts[ip] if t > cutoff]
    if len(_attempts[ip]) >= LOGIN_RATE_LIMIT_MAX:
        _locked[ip] = now + LOGIN_IP_LOCK_MIN * 60


def clear_failures(ip: str):
    _attempts.pop(ip, None)
    _locked.pop(ip, None)


def is_locked(ip: str) -> bool:
    deadline = _locked.get(ip)
    if deadline and time.time() < deadline:
        return True
    if deadline:
        _locked.pop(ip, None)
        _attempts.pop(ip, None)
    return False
