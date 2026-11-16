from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from security import repository
from security.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from security.passwords import hash_password, verify_password
from security.rate_limit import check_login_rate_limit, clear_login_attempts
from security.redis_client import get_redis
from settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    login_id: str = Field(min_length=3, max_length=100)  # phone number or email
    password: str = Field(min_length=8, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    customer_id: str
    profile_completed: bool


def _normalize_login_id(login_id: str) -> str:
    return login_id.strip().lower()


def _refresh_key(customer_id: str) -> str:
    return f"refresh_token:{customer_id}"


def _issue_tokens(customer_id: str, profile_completed: bool) -> AuthResponse:
    refresh_token = create_refresh_token(customer_id)
    # Only the most recent refresh token per customer is valid (rotation).
    get_redis().set(
        _refresh_key(customer_id), refresh_token, ex=settings.refresh_token_days * 86400
    )
    return AuthResponse(
        access_token=create_access_token(customer_id),
        refresh_token=refresh_token,
        customer_id=customer_id,
        profile_completed=profile_completed,
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(credentials: Credentials) -> AuthResponse:
    login_id = _normalize_login_id(credentials.login_id)
    check_login_rate_limit(login_id)
    try:
        customer = repository.create_customer(login_id, hash_password(credentials.password))
    except repository.LoginIdTaken:
        raise HTTPException(status_code=409, detail="An account with this phone/email already exists")
    return _issue_tokens(customer.customer_id, customer.profile_completed)


@router.post("/login", response_model=AuthResponse)
def login(credentials: Credentials) -> AuthResponse:
    login_id = _normalize_login_id(credentials.login_id)
    check_login_rate_limit(login_id)

    customer = repository.get_by_login_id(login_id)
    # Same error for unknown id and wrong password, so accounts can't be probed.
    if customer is None or not verify_password(credentials.password, customer.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect phone/email or password")

    clear_login_attempts(login_id)
    repository.touch_last_login(customer.customer_id)
    return _issue_tokens(customer.customer_id, customer.profile_completed)


@router.post("/refresh", response_model=AuthResponse)
def refresh(request: RefreshRequest) -> AuthResponse:
    customer_id = decode_token(request.refresh_token, "refresh")

    if get_redis().get(_refresh_key(customer_id)) != request.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token has been replaced or revoked")

    customer = repository.get_by_id(customer_id)
    if customer is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return _issue_tokens(customer.customer_id, customer.profile_completed)
