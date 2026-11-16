import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import Header, HTTPException

from settings import settings

TokenType = Literal["access", "refresh"]


def _create_token(customer_id: str, token_type: TokenType, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": customer_id,
        "type": token_type,
        "jti": uuid.uuid4().hex,  # makes every token unique, so refresh rotation is real
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(customer_id: str, expires_minutes: int | None = None) -> str:
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_minutes
    return _create_token(customer_id, "access", timedelta(minutes=minutes))


def create_refresh_token(customer_id: str) -> str:
    return _create_token(customer_id, "refresh", timedelta(days=settings.refresh_token_days))


def decode_token(token: str, expected_type: TokenType) -> str:
    """Returns the customer_id (the "sub" claim). A refresh token presented
    as an access token (or vice versa) is rejected."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("type") != expected_type or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token type")

    return payload["sub"]


def get_current_customer_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    return decode_token(authorization.removeprefix("Bearer "), "access")
