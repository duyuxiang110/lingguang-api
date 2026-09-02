"""
认证路由 — 注册/登录/刷新/登出/改密/忘记密码/会话验证。
移植自 electron/server/routes/auth.js
"""
import re

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from app.deps import get_auth_payload
from app.services import auth_service

router = APIRouter()

MD5_REGEX = re.compile(r"^[a-f0-9]{32}$", re.I)


class RegisterBody(BaseModel):
    username: str
    email: str
    password: str
    phone: str | None = None


class LoginBody(BaseModel):
    username: str
    password: str


class RefreshBody(BaseModel):
    refreshToken: str


class LogoutBody(BaseModel):
    sessionId: str | None = None
    refreshToken: str | None = None


class ChangePasswordBody(BaseModel):
    oldPassword: str
    newPassword: str


class ForgotPasswordBody(BaseModel):
    username: str
    email: str
    newPassword: str


def _validate_md5(password: str):
    if not MD5_REGEX.match(password):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "message": "密码格式无效，请使用客户端加密后重试", "code": "INVALID_PASSWORD_FORMAT"},
        )


@router.post("/auth/register")
async def register(body: RegisterBody):
    if not body.username or not body.email or not body.password:
        raise HTTPException(400, detail={"success": False, "message": "用户名、邮箱和密码为必填项"})
    if len(body.username) < 3 or len(body.username) > 50:
        raise HTTPException(400, detail={"success": False, "message": "用户名长度需为3-50个字符"})
    _validate_md5(body.password)
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", body.email):
        raise HTTPException(400, detail={"success": False, "message": "邮箱格式不正确"})
    try:
        user = auth_service.register(body.username, body.email, body.password, body.phone)
        return {"success": True, "data": user, "message": "注册成功，请等待管理员审核"}
    except ValueError as e:
        raise HTTPException(409, detail={"success": False, "message": str(e)})


@router.post("/auth/login")
async def login(request: Request, body: LoginBody):
    if not body.username or not body.password:
        raise HTTPException(400, detail={"success": False, "message": "请输入用户名和密码"})
    _validate_md5(body.password)
    ip = request.client.host if request.client else "127.0.0.1"
    from app.middleware.login_limiter import is_locked, record_failure, clear_failures
    if is_locked(ip):
        raise HTTPException(429, detail={"success": False, "message": "登录失败次数过多，请10分钟后重试"})
    device = request.headers.get("user-agent", "Unknown")
    try:
        result = auth_service.login(body.username, body.password, device, ip)
        clear_failures(ip)
        return {"success": True, "data": result}
    except ValueError as e:
        record_failure(ip)
        raise HTTPException(401, detail={"success": False, "message": str(e)})
    except PermissionError as e:
        record_failure(ip)
        status = 423 if "锁定" in str(e) else 403
        raise HTTPException(status, detail={"success": False, "message": str(e)})


@router.post("/auth/refresh")
async def refresh(request: Request, body: RefreshBody):
    if not body.refreshToken:
        raise HTTPException(400, detail={"success": False, "message": "缺少 Refresh Token"})
    ip = request.client.host if request.client else "127.0.0.1"
    try:
        result = auth_service.refresh_token(body.refreshToken, ip)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(401, detail={"success": False, "message": str(e)})


@router.post("/auth/logout")
async def logout(payload: dict = Depends(get_auth_payload), body: LogoutBody = None):
    auth_service.logout(payload["userId"], body.sessionId if body else None, body.refreshToken if body else None)
    return {"success": True, "message": "已成功登出"}


@router.post("/auth/change-password")
async def change_password(body: ChangePasswordBody, payload: dict = Depends(get_auth_payload)):
    if not body.oldPassword or not body.newPassword:
        raise HTTPException(400, detail={"success": False, "message": "请提供原密码和新密码"})
    _validate_md5(body.oldPassword)
    _validate_md5(body.newPassword)
    try:
        result = auth_service.change_password(payload["userId"], body.oldPassword, body.newPassword)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(400, detail={"success": False, "message": str(e)})


@router.post("/auth/forgot-password")
async def forgot_password(request: Request, body: ForgotPasswordBody):
    if not body.username or not body.email or not body.newPassword:
        raise HTTPException(400, detail={"success": False, "message": "请完整填写用户名、邮箱和新密码"})
    _validate_md5(body.newPassword)
    ip = request.client.host if request.client else "127.0.0.1"
    try:
        result = auth_service.forgot_password(body.username, body.email, body.newPassword, ip)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(404, detail={"success": False, "message": str(e)})
    except PermissionError as e:
        raise HTTPException(403, detail={"success": False, "message": str(e)})


@router.get("/auth/validate-session")
async def validate_session(sessionId: str):
    if not sessionId:
        raise HTTPException(400, detail={"success": False, "message": "缺少 sessionId"})
    session = auth_service.validate_session(sessionId)
    if not session:
        raise HTTPException(401, detail={"success": False, "message": "会话无效或已过期"})
    return {"success": True, "data": session}
