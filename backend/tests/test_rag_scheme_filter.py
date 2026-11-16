"""RAG search must not lose documents uploaded without a scheme_id."""

import uuid

import pytest

from database.db import get_connection
from rag import repository
from rag.embeddings import to_pgvector

DIM = 768


def _vector(hot: int) -> list[float]:
    v = [0.0] * DIM
    v[hot] = 1.0
    return v


@pytest.fixture
def docs():
    if not repository.vector_tables_available():
        pytest.skip("pgvector tables not available")
    ids = {}
    with get_connection() as conn:
        for key, scheme_id in [("untagged", None), ("home", "home_loan"), ("kisan", "kisan_credit_card")]:
            doc_id = str(uuid.uuid4())
            ids[key] = doc_id
            conn.execute(
                "INSERT INTO documents (doc_id, filename, status) VALUES (%s, %s, 'active')",
                (doc_id, f"test-{key}.pdf"),
            )
            conn.execute(
                "INSERT INTO loan_chunks (doc_id, scheme_id, page, section, content, embedding) "
                "VALUES (%s, %s, 1, NULL, %s, %s::vector)",
                (doc_id, scheme_id, f"{key} content", to_pgvector(_vector(0))),
            )
    yield ids
    with get_connection() as conn:
        for doc_id in ids.values():
            conn.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))


def test_active_scheme_still_finds_untagged_documents(docs):
    hits = repository.search("loan", _vector(0), "home_loan", 10)
    names = {h["filename"] for h in hits} & {f"test-{k}.pdf" for k in docs}
    assert names == {"test-untagged.pdf", "test-home.pdf"}  # never another scheme's document


def test_no_scheme_searches_everything(docs):
    hits = repository.search("loan", _vector(0), None, 10)
    names = {h["filename"] for h in hits} & {f"test-{k}.pdf" for k in docs}
    assert names == {"test-untagged.pdf", "test-home.pdf", "test-kisan.pdf"}
