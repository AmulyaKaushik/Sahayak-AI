"""Ingest every PDF in the documents folder (settings.rag_documents_dir).

    python -m rag.folder_sync

The sub-folder a PDF sits in is its scheme_id (documents/home_loan/x.pdf ->
"home_loan"); a PDF directly in documents/ takes its scheme from its file name
(home_loan.pdf) and, if the name is not a scheme id, is searched for every scheme. Safe to re-run: a file whose content was already ingested is
skipped, and one whose embedding failed earlier is retried."""

import hashlib
from pathlib import Path

from pydantic import BaseModel

from rag import repository
from rag.extract import PdfError
from rag.ingestion import approve_document, ingest_pdf
from schemas.required_fields_seed import REQUIRED_FIELDS_ENTRIES
from settings import settings

MAX_PDF_BYTES = 20 * 1024 * 1024
KNOWN_SCHEME_IDS = [e.scheme_or_loan_id for e in REQUIRED_FIELDS_ENTRIES]
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class SyncItem(BaseModel):
    file: str  # path relative to the documents folder
    scheme_id: str | None = None
    result: str  # ingested | unchanged | retagged | retried | skipped | error
    status: str | None = None  # document status: active, needs_review, ...
    note: str | None = None
    doc_id: str | None = None


def documents_dir() -> Path:
    path = Path(settings.rag_documents_dir)
    return path if path.is_absolute() else _BACKEND_DIR / path


def _scheme_for(relative: Path) -> tuple[str | None, str | None]:
    """(scheme_id, problem). A top-level PDF takes its scheme from its file
    name (home_loan.pdf -> home_loan) and has none if the name is not a scheme."""
    if len(relative.parts) == 1:
        stem = relative.stem.lower()
        return (stem if stem in KNOWN_SCHEME_IDS else None), None
    folder = relative.parts[0]
    if folder not in KNOWN_SCHEME_IDS:
        return None, f"Folder '{folder}' is not a known scheme. Use one of: {', '.join(KNOWN_SCHEME_IDS)}."
    return folder, None


def _sync_file(path: Path, relative: Path) -> SyncItem:
    scheme_id, problem = _scheme_for(relative)
    item = SyncItem(file=relative.as_posix(), scheme_id=scheme_id, result="skipped")
    if problem:
        item.note = problem
        return item

    data = path.read_bytes()
    if len(data) > MAX_PDF_BYTES:
        item.result, item.note = "error", "Larger than 20 MB."
        return item
    if not data.startswith(b"%PDF"):
        item.result, item.note = "error", "Not a valid PDF file."
        return item

    existing = repository.find_by_hash(hashlib.sha256(data).hexdigest())
    if existing:
        item.doc_id, item.status = existing["doc_id"], existing["status"]
        if existing["status"] == "active":
            if scheme_id and existing["scheme_id"] != scheme_id:
                # Moved into a scheme folder: re-tag, no need to re-embed.
                repository.set_scheme(existing["doc_id"], scheme_id)
                item.result, item.note = "retagged", f"scheme set to {scheme_id}"
            else:
                item.result = "unchanged"
        elif existing["status"] == "embedding_failed" and existing["doc_type"]:
            outcome = approve_document(existing["doc_id"], existing["doc_type"], scheme_id)
            item.result, item.status, item.note = "retried", outcome.status, outcome.note
        else:
            item.result = "skipped"
            item.note = (
                "Already uploaded and waiting for a decision "
                f"(status {existing['status']}); see GET /api/v1/admin/documents."
            )
        return item

    try:
        outcome = ingest_pdf(path.name, data, scheme_id)
    except PdfError as exc:
        item.result, item.note = "error", str(exc)
        return item
    item.result, item.doc_id = "ingested", outcome.doc_id
    item.status, item.note = outcome.status, outcome.note
    return item


def sync_folder(directory: Path | None = None) -> list[SyncItem]:
    root = directory or documents_dir()
    if not root.is_dir():
        return []
    items = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"):
        items.append(_sync_file(path, path.relative_to(root)))
    return items


if __name__ == "__main__":
    print(f"Reading PDFs from {documents_dir()}")
    results = sync_folder()
    if not results:
        print("No PDF files found.")
    for r in results:
        scheme = r.scheme_id or "(no scheme)"
        line = f"[{r.result:9}] {r.file}  scheme={scheme}  status={r.status or '-'}"
        print(line + (f"\n            {r.note}" if r.note else ""))
