from psycopg.types.json import Jsonb

from database.db import get_connection
from eligibility_engine.conditions import collect_leaves
from schemas.models import EligibilityRule


def load_active_rule(scheme_id: str) -> EligibilityRule | None:
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
