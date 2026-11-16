"""Admin upload pipeline: extract -> classify -> (chunk -> embed -> store).

Anything uncertain stops at status 'needs_review' with the text kept, so a
human picks the type before anything goes live (architecture doc principle).

Statuses: processing -> active | needs_review | needs_ocr | embedding_failed"""

import hashlib

from pydantic import BaseModel

from rag import repository
from rag.chunking import chunk_pages
from rag.classifier import classify_document
from rag.embeddings import EmbeddingError, embed_texts
from rag.extract import Page, blank_pages, extract_pages
from settings import settings

_PAGE_SEPARATOR = "\f"


class IngestResult(BaseModel):
    doc_id: str
    doc_type: str | None
    status: str
    note: str | None = None


def _join(pages: list[Page]) -> str:
    return _PAGE_SEPARATOR.join(p.text for p in pages)


def _split(raw_text: str) -> list[Page]:
    return [Page(i + 1, t) for i, t in enumerate(raw_text.split(_PAGE_SEPARATOR))]


def ingest_pdf(filename: str, pdf_bytes: bytes, scheme_id: str | None = None) -> IngestResult:
    pages = extract_pages(pdf_bytes)  # raises PdfError
    blanks = blank_pages(pages)
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()

    if len(blanks) == len(pages):
        doc_id = repository.create_document(filename, "", len(pages), content_hash)
        note = "No extractable text (scanned PDF); OCR is required."
        repository.update_document(doc_id, status="needs_ocr", note=note)
        return IngestResult(doc_id=doc_id, doc_type=None, status="needs_ocr", note=note)

    doc_id = repository.create_document(filename, _join(pages), len(pages), content_hash)
    notes = []
    if blanks:
        notes.append(f"Pages with no text (need OCR): {blanks}")
    if not scheme_id:
        notes.append(
            "No scheme_id given: this document is searched for every scheme. "
            "Pass scheme_id (e.g. home_loan) so answers stay scoped to one scheme."
        )
    note = " ".join(notes) or None

    classification = classify_document(filename, pages)
    repository.update_document(
        doc_id,
        title=classification.suggested_name or filename,
        classifier_confidence=classification.confidence,
        scheme_id=scheme_id,
        note=note,
    )

    if (
        classification.doc_type == "unclear"
        or classification.confidence < settings.rag_classify_min_confidence
    ):
        review_note = "Classifier unsure whether this is a loan or a scheme; needs human review."
        repository.update_document(
            doc_id, status="needs_review", note=f"{note + ' ' if note else ''}{review_note}"
        )
        return IngestResult(doc_id=doc_id, doc_type=None, status="needs_review", note=review_note)

    return _embed_and_store(doc_id, classification.doc_type, scheme_id, pages, note)


def approve_document(doc_id: str, doc_type: str, scheme_id: str | None = None) -> IngestResult:
    """Human review step: set the type (and optionally scheme_id) and
    embed. Also used to retry a document whose embedding failed."""
    doc = repository.get_document(doc_id)
    if doc is None:
        raise LookupError(doc_id)
    pages = _split(doc["raw_text"] or "")
    return _embed_and_store(doc_id, doc_type, scheme_id or doc["scheme_id"], pages, doc["note"])


def _embed_and_store(
    doc_id: str, doc_type: str, scheme_id: str | None, pages: list[Page], note: str | None
) -> IngestResult:
    def fail(status: str, message: str, with_type: bool) -> IngestResult:
        fields = {"status": status, "note": message}
        if with_type:
            fields["doc_type"] = doc_type
        repository.update_document(doc_id, **fields)
        return IngestResult(
            doc_id=doc_id, doc_type=doc_type if with_type else None, status=status, note=message
        )

    chunks = chunk_pages(pages)
    if not chunks:
        return fail("needs_review", "No text chunks produced.", with_type=False)

    if not repository.vector_tables_available():
        return fail(
            "embedding_failed",
            "pgvector tables are missing; run `python -m rag.setup` on a database with pgvector.",
            with_type=True,
        )

    try:
        vectors = embed_texts([c.content for c in chunks])
    except EmbeddingError as exc:
        return fail("embedding_failed", str(exc), with_type=True)

    repository.replace_chunks(doc_type, doc_id, scheme_id, chunks, vectors)
    repository.update_document(
        doc_id, status="active", doc_type=doc_type, scheme_id=scheme_id,
        chunk_count=len(chunks), note=note,
    )
    return IngestResult(doc_id=doc_id, doc_type=doc_type, status="active", note=note)
