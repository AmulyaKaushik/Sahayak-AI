from fastapi import APIRouter, HTTPException

from schemas.models import ContextEntry
from supervisor.context_store import SessionContextStore

router = APIRouter(prefix="/session-context", tags=["session-context"])
_store = SessionContextStore()


@router.post("/{session_id}", response_model=ContextEntry)
def write_context_entry(session_id: str, entry: ContextEntry) -> ContextEntry:
    if entry.session_id != session_id:
        raise HTTPException(status_code=400, detail="session_id mismatch")
    _store.write(entry)
    return entry


@router.get("/{session_id}", response_model=list[ContextEntry])
def read_context_entries(session_id: str) -> list[ContextEntry]:
    return _store.read(session_id)
