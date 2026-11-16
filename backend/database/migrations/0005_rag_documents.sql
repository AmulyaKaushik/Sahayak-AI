-- RAG storage. loan_chunks and scheme_chunks are two physical tables on
-- purpose: two independent vector spaces, so a loan question can never
-- retrieve scheme text by accident.
--
-- vector(768) must equal settings.embedding_dimensions.
--
-- pgvector may be unavailable (e.g. plain postgres:16 locally). In that case
-- the documents table is still created and the chunk tables are skipped with
-- a notice, so the rest of the backend keeps working; RAG answers then
-- degrade to "not in the documents". Re-run `python -m database.migrate`
-- is NOT enough after installing pgvector (this migration is already
-- recorded) -- run `python -m rag.setup` instead, which is idempotent.
CREATE TABLE IF NOT EXISTS documents (
    doc_id      UUID PRIMARY KEY,
    filename    TEXT NOT NULL,
    doc_type    TEXT CHECK (doc_type IN ('loan', 'scheme')),
    scheme_id   TEXT,
    status      TEXT NOT NULL,
    title       TEXT,
    classifier_confidence DOUBLE PRECISION,
    page_count  INT,
    chunk_count INT NOT NULL DEFAULT 0,
    note        TEXT,
    raw_text    TEXT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS loan_chunks (
        chunk_id  BIGSERIAL PRIMARY KEY,
        doc_id    UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
        scheme_id TEXT,
        page      INT,
        section   TEXT,
        content   TEXT NOT NULL,
        embedding vector(768) NOT NULL
    );
    CREATE TABLE IF NOT EXISTS scheme_chunks (LIKE loan_chunks INCLUDING ALL);

    CREATE INDEX IF NOT EXISTS idx_loan_chunks_embedding
        ON loan_chunks USING hnsw (embedding vector_cosine_ops);
    CREATE INDEX IF NOT EXISTS idx_scheme_chunks_embedding
        ON scheme_chunks USING hnsw (embedding vector_cosine_ops);
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector unavailable, chunk tables not created: %', SQLERRM;
END
$$;
