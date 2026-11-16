"""RAG persistence. loan_chunks / scheme_chunks are separate physical tables
(separate vector spaces); the table name is always picked from _CHUNK_TABLES,
never from user input."""

import re
import uuid

from database.db import get_connection
from rag.embeddings import to_pgvector

_CHUNK_TABLES = {"loan": "loan_chunks", "scheme": "scheme_chunks"}

_DOC_COLUMNS = (
    "doc_id, filename, doc_type, scheme_id, status, title, classifier_confidence, "
    "page_count, chunk_count, note, uploaded_at"
)


def _doc_row(row) -> dict:
    keys = _DOC_COLUMNS.replace(" ", "").split(",")
    doc = dict(zip(keys, row))
    doc["doc_id"] = str(doc["doc_id"])
    doc["uploaded_at"] = doc["uploaded_at"].isoformat()
    return doc


def vector_tables_available() -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name IN ('loan_chunks', 'scheme_chunks')"
        ).fetchone()
    return row[0] == 2


def create_document(
    filename: str, raw_text: str, page_count: int, content_hash: str | None = None
) -> str:
    doc_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO documents (doc_id, filename, status, raw_text, page_count, content_hash) "
            "VALUES (%s, %s, 'processing', %s, %s, %s)",
            (doc_id, filename, raw_text, page_count, content_hash),
        )
    return doc_id


def find_by_hash(content_hash: str) -> dict | None:
    """Most recent document ingested from exactly this file content."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT doc_id, status, doc_type, scheme_id FROM documents "
            "WHERE content_hash = %s ORDER BY uploaded_at DESC LIMIT 1",
            (content_hash,),
        ).fetchone()
    if row is None:
        return None
    return {"doc_id": str(row[0]), "status": row[1], "doc_type": row[2], "scheme_id": row[3]}


def update_document(doc_id: str, **fields) -> None:
    allowed = {"doc_type", "scheme_id", "status", "title", "classifier_confidence", "chunk_count", "note"}
    assert set(fields) <= allowed, set(fields) - allowed
    if not fields:
        return
    assignments = ", ".join(f"{name} = %s" for name in fields)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE documents SET {assignments} WHERE doc_id = %s", (*fields.values(), doc_id)
        )


def set_scheme(doc_id: str, scheme_id: str) -> None:
    """Re-tag an already-embedded document (and its chunks) without re-embedding."""
    with get_connection() as conn:
        conn.execute("UPDATE documents SET scheme_id = %s WHERE doc_id = %s", (scheme_id, doc_id))
        for table in _CHUNK_TABLES.values():
            conn.execute(f"UPDATE {table} SET scheme_id = %s WHERE doc_id = %s", (scheme_id, doc_id))


def get_document(doc_id: str) -> dict | None:
    try:
        uuid.UUID(doc_id)
    except ValueError:
        return None
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT {_DOC_COLUMNS}, raw_text FROM documents WHERE doc_id = %s", (doc_id,)
        ).fetchone()
    if row is None:
        return None
    doc = _doc_row(row[:-1])
    doc["raw_text"] = row[-1]
    return doc


def list_documents(status: str | None = None) -> list[dict]:
    query = f"SELECT {_DOC_COLUMNS} FROM documents"
    params: tuple = ()
    if status:
        query += " WHERE status = %s"
        params = (status,)
    query += " ORDER BY uploaded_at DESC"
    with get_connection() as conn:
        return [_doc_row(row) for row in conn.execute(query, params).fetchall()]


def replace_chunks(
    doc_type: str,
    doc_id: str,
    scheme_id: str | None,
    chunks: list,  # rag.chunking.Chunk
    vectors: list[list[float]],
) -> None:
    table = _CHUNK_TABLES[doc_type]
    with get_connection() as conn:
        for other in _CHUNK_TABLES.values():  # re-typing a doc must not leave stale chunks
            conn.execute(f"DELETE FROM {other} WHERE doc_id = %s", (doc_id,))
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {table} (doc_id, scheme_id, page, section, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s::vector)",
                [
                    (doc_id, scheme_id, c.page, c.section, c.content, to_pgvector(v))
                    for c, v in zip(chunks, vectors)
                ],
            )


_STOPWORDS = {
    "the", "and", "for", "are", "what", "which", "who", "how", "when", "where", "why", "can", "does",
    "this", "that", "with", "have", "has", "need", "tell", "about", "please", "from", "your", "you",
    "get", "any", "all", "its", "not", "was", "were", "will", "would", "should", "could", "into",
}


def _keywords(text: str) -> list[str]:
    words = []
    for word in re.findall(r"[a-z0-9]{3,}", text.lower()):
        if word not in _STOPWORDS and word not in words:
            words.append(word)
    return words[:12]


def search_text(doc_type: str, question: str, scheme_id: str | None, limit: int) -> list[dict]:
    """Keyword (full-text) search. Used when the embedding service is not
    available: it needs no external API and works offline."""
    words = _keywords(question)
    if not words:
        return []
    table = _CHUNK_TABLES[doc_type]
    query = " | ".join(words)
    where, params = "", [query, query]
    if scheme_id:
        where = "AND (c.scheme_id = %s OR c.scheme_id IS NULL)"
        params.append(scheme_id)
    params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT c.chunk_id, d.filename, c.page, c.section, c.content, "
            f"ts_rank_cd(to_tsvector('english', c.content), to_tsquery('english', %s)) AS rank "
            f"FROM {table} c JOIN documents d ON d.doc_id = c.doc_id "
            f"WHERE to_tsvector('english', c.content) @@ to_tsquery('english', %s) {where} "
            f"ORDER BY rank DESC LIMIT %s",
            params,
        ).fetchall()
    return [
        {
            "chunk_id": r[0], "filename": r[1], "page": r[2], "section": r[3],
            "content": r[4], "similarity": float(r[5]), "doc_type": doc_type, "by_keyword": True,
        }
        for r in rows
    ]


def search(
    doc_type: str, query_vector: list[float], scheme_id: str | None, limit: int
) -> list[dict]:
    table = _CHUNK_TABLES[doc_type]
    vector = to_pgvector(query_vector)
    where, params = "", [vector]
    if scheme_id:
        # Chunks of a document uploaded without a scheme_id (NULL) are generic:
        # they stay searchable instead of vanishing once a scheme is active.
        where = "WHERE (c.scheme_id = %s OR c.scheme_id IS NULL)"
        params.append(scheme_id)
    params.extend([vector, limit])
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT c.chunk_id, d.filename, c.page, c.section, c.content, "
            f"1 - (c.embedding <=> %s::vector) AS similarity "
            f"FROM {table} c JOIN documents d ON d.doc_id = c.doc_id "
            f"{where} ORDER BY c.embedding <=> %s::vector LIMIT %s",
            params,
        ).fetchall()
    return [
        {
            "chunk_id": r[0], "filename": r[1], "page": r[2], "section": r[3],
            "content": r[4], "similarity": float(r[5]), "doc_type": doc_type,
        }
        for r in rows
    ]
