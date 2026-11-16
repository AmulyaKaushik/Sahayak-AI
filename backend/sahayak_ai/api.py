"""The mobile app's chat entry point: server-issued sessions and messages.
customer_id only ever comes from the JWT."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sahayak_ai.models import SahayakResponse
from sahayak_ai.orchestrator import handle_message
from security import sessions
from security.auth import get_current_customer_id

router = APIRouter(prefix="/api/v1", tags=["chat"])


class SessionResponse(BaseModel):
    session_id: str


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    language: str = "en-IN"


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def create_session(customer_id: str = Depends(get_current_customer_id)) -> SessionResponse:
    return SessionResponse(session_id=sessions.create_session(customer_id))


@router.post("/sessions/{session_id}/messages", response_model=SahayakResponse)
async def post_message(
    session_id: str,
    request: MessageRequest,
    customer_id: str = Depends(get_current_customer_id),
) -> SahayakResponse:
    sessions.assert_session_owner(session_id, customer_id)
    return await handle_message(customer_id, session_id, request.text.strip(), request.language)
