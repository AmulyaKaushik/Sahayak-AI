"""Idempotently (re)apply the RAG migration. Use this after installing the
pgvector extension on a database where migration 0005 already ran and had to
skip the chunk tables:  python -m rag.setup"""

import psycopg

from database.migrate import MIGRATIONS_DIR
from settings import settings

if __name__ == "__main__":
    sql = (MIGRATIONS_DIR / "0005_rag_documents.sql").read_text()
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(sql)
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('loan_chunks', 'scheme_chunks')"
        ).fetchall()
    print("chunk tables present:", sorted(t[0] for t in tables) or "NONE (pgvector missing?)")
