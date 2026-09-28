from fastapi import APIRouter
from pydantic import BaseModel

from security.auth import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    # Identity is assumed already verified out-of-band by kiosk hardware
    # (card reader / biometric) before this call is made -- this service
    # never sees or stores a PIN, OTP, or password (Section 4.9).
    customer_id: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    token = create_access_token(request.customer_id)
    return LoginResponse(access_token=token)
