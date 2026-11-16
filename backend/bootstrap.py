"""First-start setup for a fresh cloud database (AUTO_SETUP=true).

Runs on every start and is safe to repeat: migrations already applied are
skipped, eligibility rules are only seeded for schemes that have none, and the
documents folder is synced in the background (already-ingested PDFs are
skipped by content hash, so a restart costs no embedding calls)."""

import logging
import threading

from database.db import get_connection
from database.migrate import run_migrations

logger = logging.getLogger("sahayak.bootstrap")


def seed_missing_rules() -> list[str]:
    from eligibility_engine.rules_repository import upsert_and_activate
    from eligibility_engine.rules_seed import RULES

    with get_connection() as conn:
        have = {r[0] for r in conn.execute(
            "SELECT scheme_id FROM eligibility_rules WHERE is_active").fetchall()}
    seeded = []
    for rule in RULES:
        if rule.scheme_id not in have:
            upsert_and_activate(rule)
            seeded.append(rule.scheme_id)
    return seeded


def _sync_documents() -> None:
    try:
        from rag.folder_sync import sync_folder

        for item in sync_folder():
            logger.info("documents: %s %s -> %s", item.file, item.result, item.status or item.note or "")
    except Exception:
        logger.exception("document sync failed (the app keeps running)")


def run_startup_tasks() -> None:
    applied = run_migrations()
    if applied:
        logger.info("applied migrations: %s", ", ".join(applied))
    seeded = seed_missing_rules()
    if seeded:
        logger.info("seeded eligibility rules: %s", ", ".join(seeded))
    threading.Thread(target=_sync_documents, name="document-sync", daemon=True).start()
