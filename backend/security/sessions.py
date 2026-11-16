"""Server-issued conversation sessions (connect.md section 3.3).

JWT = who you are (customer_id); session id = which conversation. The
backend enforces that the second belongs to the first."""

import uuid

from fastapi import HTTPException

from security.redis_client import get_redis
from settings import settings


def _owner_key(session_id: str) -> str:
    return f"session_owner:{session_id}"


def create_session(customer_id: str) -> str:
    session_id = str(uuid.uuid4())
    get_redis().set(_owner_key(session_id), customer_id, ex=settings.session_ttl_seconds)
    return session_id


def assert_session_owner(session_id: str, customer_id: str) -> None:
    """403 unless this session was issued to this customer. Unknown/expired
    sessions get the same 403 so ids can't be probed."""
    owner = get_redis().get(_owner_key(session_id))
    if owner is None or owner != customer_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this user")
