from typing import Optional

import jwt
from fastapi import HTTPException, Request
from app.config import JWT_SECRET


def verify_token(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证信息")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token 无效")
    return payload


def get_auth_payload(request: Request) -> dict:
    auth = request.headers.get("Authorization")
    return verify_token(auth)
