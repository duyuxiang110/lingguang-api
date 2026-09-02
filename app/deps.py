"""
认证依赖 — JWT 验证、角色检查、统一错误响应。
401 响应格式匹配前端拦截器：{success: false, message: "...", code: "TOKEN_EXPIRED"}
"""
from typing import Optional, Callable

import jwt
from fastapi import HTTPException, Request, Depends
from app.config import JWT_SECRET


def verify_token(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "未提供认证令牌"},
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "Token 已过期", "code": "TOKEN_EXPIRED"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail={"success": False, "message": "Token 无效"},
        )
    return payload


def get_auth_payload(request: Request) -> dict:
    return verify_token(request.headers.get("Authorization"))


def require_role(*roles: str) -> Callable:
    def checker(payload: dict = Depends(get_auth_payload)) -> dict:
        if payload.get("role") not in roles:
            raise HTTPException(
                status_code=403,
                detail={"success": False, "message": f"权限不足，需要角色: {'/'.join(roles)}"},
            )
        return payload
    return checker
