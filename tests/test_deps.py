import pytest
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.deps import verify_token
from app.config import JWT_SECRET

def _make_token(payload: dict) -> str:
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def test_valid_token():
    token = _make_token({"sub": "user1", "exp": datetime.now(timezone.utc) + timedelta(hours=2)})
    payload = verify_token(f"Bearer {token}")
    assert payload["sub"] == "user1"

def test_missing_token():
    with pytest.raises(HTTPException) as exc:
        verify_token(None)
    assert exc.value.status_code == 401

def test_invalid_format():
    with pytest.raises(HTTPException) as exc:
        verify_token("NotBearer abc")
    assert exc.value.status_code == 401

def test_expired_token():
    token = _make_token({"sub": "user1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)})
    with pytest.raises(HTTPException) as exc:
        verify_token(f"Bearer {token}")
    assert exc.value.status_code == 401

def test_bad_signature():
    token = jwt.encode({"sub": "x"}, "wrong-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        verify_token(f"Bearer {token}")
    assert exc.value.status_code == 401
