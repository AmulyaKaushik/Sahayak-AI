"""Admin document endpoints (X-Admin-Key). Not for the mobile app."""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from rag import repository
from rag.extract import PdfError
from rag.folder_sync import SyncItem, sync_folder
from rag.ingestion import IngestResult, approve_document, ingest_pdf
from security.admin import require_admin

router = APIRouter(
    prefix="/api/v1/admin/documents", tags=["admin"], dependencies=[Depends(require_admin)]
)

MAX_PDF_BYTES = 20 * 1024 * 1024


class ReviewRequest(BaseModel):
    doc_type: Literal["loan", "scheme"]
    scheme_id: str | None = None


@router.post("", response_model=IngestResult, status_code=201)
async def upload_document(file: UploadFile = File(...), scheme_id: str | None = Form(default=None)):
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF is larger than 20 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail="Only PDF files are accepted")
    try:
        return await run_in_threadpool(ingest_pdf, file.filename or "document.pdf", data, scheme_id)
    except PdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/sync", response_model=list[SyncItem])
async def sync_documents_folder():
    """Ingest every new PDF in the server's documents folder (see
    documents/README.md). Safe to repeat."""
    return await run_in_threadpool(sync_folder)


@router.get("")
def list_documents(status: str | None = None) -> list[dict]:
    return repository.list_documents(status)


@router.post("/{doc_id}/review", response_model=IngestResult)
async def review_document(doc_id: str, request: ReviewRequest):
    """Human decision for a needs_review document (also retries failed embeds)."""
    try:
        return await run_in_threadpool(approve_document, doc_id, request.doc_type, request.scheme_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Document not found")
