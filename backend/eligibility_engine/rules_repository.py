import logging
import time

from psycopg.types.json import Jsonb

from database.db import get_connection
from eligibility_engine.conditions import collect_leaves
from schemas.models import EligibilityRule


logger = logging.getLogger(__name__)

# Rules change rarely, so each is cached in memory. A cached rule is also what
# keeps eligibility checks working when the database cannot be reached.
_RULE_TTL_SECONDS = 300
_rule_cache: dict[str, tuple[float, EligibilityRule | None]] = {}


def clear_rule_cache() -> None:
    _rule_cache.clear()


def load_active_rule(scheme_id: str) -> EligibilityRule | None:
    cached = _rule_cache.get(scheme_id)
    if cached and time.monotonic() - cached[0] < _RULE_TTL_SECONDS:
        return cached[1]
    try:
        rule = _load_active_rule_from_db(scheme_id)
    except Exception:
        if cached:
            logger.warning("Rules: database unreachable; using cached rule for %s", scheme_id, exc_info=True)
            return cached[1]
        raise
    _rule_cache[scheme_id] = (time.monotonic(), rule)
    return rule


def _load_active_rule_from_db(scheme_id: str) -> EligibilityRule | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT scheme_id, version, conditions, source_document, approved_by, updated_at "
            "FROM eligibility_rules WHERE scheme_id = %s AND is_active = true",
            (scheme_id,),
        ).fetchone()

    if row is None:
        return None

    return EligibilityRule(
        scheme_id=row[0],
        version=row[1],
        conditions=row[2],
        source_document=row[3],
        approved_by=row[4],
        updated_at=row[5],
    )


def get_required_field_names(scheme_id: str) -> list[str]:
    """Derives the field names a scheme's active rule actually reads, straight
    from its condition tree. A stand-in for the DB-backed required-fields
    registry (RequiredFieldsEntry) that Phase 6 builds around this same
    primitive -- Phase 4 workers use it directly in the meantime."""
    rule = load_active_rule(scheme_id)
    if rule is None:
        return []
    seen: list[str] = []
    for leaf in collect_leaves(rule.conditions):
        if leaf["field"] not in seen:
            seen.append(leaf["field"])
    return seen


def upsert_and_activate(rule: EligibilityRule) -> None:
    """Insert a new rule version and make it the only active version for its
    scheme_id. Never mutates a previously inserted version's row in place --
    the eligibility_rules table is append-only per version (Phase 1 migration
    0003 comment)."""
    _rule_cache.pop(rule.scheme_id, None)
    with get_connection() as conn:
        conn.execute(
            "UPDATE eligibility_rules SET is_active = false WHERE scheme_id = %s",
            (rule.scheme_id,),
        )
        conn.execute(
            """
            INSERT INTO eligibility_rules
                (scheme_id, version, conditions, source_document, approved_by, updated_at, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, true)
            ON CONFLICT (scheme_id, version) DO UPDATE SET
                conditions = EXCLUDED.conditions,
                source_document = EXCLUDED.source_document,
                approved_by = EXCLUDED.approved_by,
                updated_at = EXCLUDED.updated_at,
                is_active = true
            """,
            (
                rule.scheme_id,
                rule.version,
                Jsonb(rule.conditions),
                rule.source_document,
                rule.approved_by,
                rule.updated_at,
            ),
        )
