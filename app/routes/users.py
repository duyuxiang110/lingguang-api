"""
用户管理路由 — CRUD/权限/统计/日志/状态管理。
移植自 electron/server/routes/users.js
"""
import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.deps import get_auth_payload, require_role
from app.services import user_service

router = APIRouter()

MD5_REGEX = re.compile(r"^[a-f0-9]{32}$", re.I)


class UpdateProfileBody(BaseModel):
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None


class UpdateUserBody(BaseModel):
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    role: str | None = None
    status: str | None = None


class ResetPasswordBody(BaseModel):
    newPassword: str


@router.get("/users")
async def list_users(
    page: int = 1, pageSize: int = 20, keyword: str = "", role: str = "", status: str = "",
    _payload: dict = Depends(require_role("admin")),
):
    result = user_service.get_users(page, pageSize, keyword, role, status)
    return {"success": True, "data": result}


@router.get("/users/stats")
async def stats(_payload: dict = Depends(require_role("admin"))):
    return {"success": True, "data": user_service.get_stats()}


@router.get("/users/logs")
async def logs(
    page: int = 1, pageSize: int = 50, userId: int | None = None, action: str = "",
    _payload: dict = Depends(require_role("admin")),
):
    result = user_service.get_login_logs(page, pageSize, userId, action)
    return {"success": True, "data": result}


@router.get("/users/permissions")
async def permissions(payload: dict = Depends(get_auth_payload)):
    return {"success": True, "data": user_service.get_user_permissions(payload["userId"])}


@router.get("/users/profile")
async def profile(payload: dict = Depends(get_auth_payload)):
    try:
        return {"success": True, "data": user_service.get_user_by_id(payload["userId"])}
    except ValueError as e:
        raise HTTPException(404, detail={"success": False, "message": str(e)})


@router.put("/users/profile")
async def update_profile(body: UpdateProfileBody, payload: dict = Depends(get_auth_payload)):
    try:
        user = user_service.update_user(payload["userId"], email=body.email, phone=body.phone, avatar=body.avatar)
        return {"success": True, "data": user, "message": "资料更新成功"}
    except ValueError as e:
        raise HTTPException(400, detail={"success": False, "message": str(e)})


@router.get("/users/{user_id}")
async def get_user(user_id: int, _payload: dict = Depends(require_role("admin"))):
    try:
        return {"success": True, "data": user_service.get_user_by_id(user_id)}
    except ValueError as e:
        raise HTTPException(404, detail={"success": False, "message": str(e)})


@router.put("/users/{user_id}")
async def update_user(user_id: int, body: UpdateUserBody, _payload: dict = Depends(require_role("admin"))):
    try:
        user = user_service.update_user(user_id, email=body.email, phone=body.phone, avatar=body.avatar, role=body.role, status=body.status)
        return {"success": True, "data": user, "message": "用户更新成功"}
    except ValueError as e:
        raise HTTPException(400, detail={"success": False, "message": str(e)})


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, _payload: dict = Depends(require_role("admin"))):
    try:
        result = user_service.delete_user(user_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(404, detail={"success": False, "message": str(e)})
    except PermissionError as e:
        raise HTTPException(403, detail={"success": False, "message": str(e)})


@router.post("/users/{user_id}/unlock")
async def unlock(user_id: int, _payload: dict = Depends(require_role("admin"))):
    return {"success": True, "data": user_service.unlock_user(user_id)}


@router.post("/users/{user_id}/restrict")
async def restrict(user_id: int, _payload: dict = Depends(require_role("admin"))):
    try:
        return {"success": True, "data": user_service.restrict_user(user_id)}
    except ValueError as e:
        raise HTTPException(404, detail={"success": False, "message": str(e)})
    except PermissionError as e:
        raise HTTPException(403, detail={"success": False, "message": str(e)})


@router.post("/users/{user_id}/unrestrict")
async def unrestrict(user_id: int, _payload: dict = Depends(require_role("admin"))):
    try:
        return {"success": True, "data": user_service.unrestrict_user(user_id)}
    except ValueError as e:
        raise HTTPException(404, detail={"success": False, "message": str(e)})


@router.post("/users/{user_id}/approve")
async def approve(user_id: int, _payload: dict = Depends(require_role("admin"))):
    try:
        return {"success": True, "data": user_service.approve_user(user_id)}
    except ValueError as e:
        raise HTTPException(400, detail={"success": False, "message": str(e)})


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: int, body: ResetPasswordBody, _payload: dict = Depends(require_role("admin"))):
    if not body.newPassword or not MD5_REGEX.match(body.newPassword):
        raise HTTPException(400, detail={"success": False, "message": "密码格式无效，请使用客户端加密后重试"})
    return {"success": True, "data": user_service.reset_password(user_id, body.newPassword)}
