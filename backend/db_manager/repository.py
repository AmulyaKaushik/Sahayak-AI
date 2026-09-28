from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from database.db import get_connection
from schemas.models import CustomerProfile

PROFILE_FIELDS = [
    "monthly_income",
    "age",
    "dependents",
    "employment_type",
    "existing_products",
    "language_preference",
]


def get_profile(customer_id: str) -> CustomerProfile | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT customer_id, monthly_income, age, dependents, employment_type, "
            "existing_products, language_preference "
            "FROM customer_profiles WHERE customer_id = %s",
            (customer_id,),
        ).fetchone()

    if row is None:
        return None

    return CustomerProfile(
        customer_id=row[0],
        monthly_income=float(row[1]) if row[1] is not None else None,
        age=row[2],
        dependents=row[3],
        employment_type=row[4],
        existing_products=list(row[5]) if row[5] else [],
        language_preference=row[6],
    )


def upsert_profile(profile: CustomerProfile, source: str = "api") -> CustomerProfile:
    """Single-writer entry point for the customer profile store (DB Manager only).
    Old field values are archived with a timestamp, never overwritten in place."""
    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT monthly_income, age, dependents, employment_type, "
            "existing_products, language_preference "
            "FROM customer_profiles WHERE customer_id = %s",
            (profile.customer_id,),
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO customer_profiles
                    (customer_id, monthly_income, age, dependents, employment_type,
                     existing_products, language_preference, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    profile.customer_id,
                    profile.monthly_income,
                    profile.age,
                    profile.dependents,
                    profile.employment_type,
                    profile.existing_products,
                    profile.language_preference,
                    now,
                ),
            )
            return profile

        existing_values = dict(zip(PROFILE_FIELDS, existing))
        new_values = profile.model_dump(exclude={"customer_id"})

        for field in PROFILE_FIELDS:
            old_value = existing_values[field]
            new_value = new_values[field]
            if old_value is not None and old_value != new_value:
                conn.execute(
                    "INSERT INTO customer_profile_field_history "
                    "(customer_id, field_name, value, source, recorded_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        profile.customer_id,
                        field,
                        Jsonb(float(old_value) if field == "monthly_income" else old_value),
                        source,
                        now,
                    ),
                )

        conn.execute(
            """
            UPDATE customer_profiles
            SET monthly_income = %s, age = %s, dependents = %s, employment_type = %s,
                existing_products = %s, language_preference = %s, updated_at = %s
            WHERE customer_id = %s
            """,
            (
                profile.monthly_income,
                profile.age,
                profile.dependents,
                profile.employment_type,
                profile.existing_products,
                profile.language_preference,
                now,
                profile.customer_id,
            ),
        )

    return profile


def get_latest_known_extra_values(customer_id: str) -> dict:
    """Latest recorded value per field_name in the field-history table for
    this customer -- covers scheme-specific facts (has_girl_child_under_10,
    land_holding_acres, ...) that have no other home, via the SAME table as
    the versioned-upsert audit trail (no new columns; see the migration
    0002 comment -- it was already an EAV-style table, just only used for
    CustomerProfile's 6 fields until now).

    Unlike a CustomerProfile field's history (which only logs the value
    BEFORE an overwrite -- the current value lives in customer_profiles),
    a fact written via upsert_extra_facts has nowhere else to live, so its
    latest row IS its current value."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT ON (field_name) field_name, value
            FROM customer_profile_field_history
            WHERE customer_id = %s
            ORDER BY field_name, recorded_at DESC
            """,
            (customer_id,),
        ).fetchall()
    return dict(rows)


def get_known_fields(customer_id: str) -> dict:
    """Combined current-known-fact view for a customer: CustomerProfile's 6
    native fields (customer_profiles) overlaid with any conversation-
    extracted extra facts (latest value per field_name in the history
    table). Extra-fact values win on overlap, since they're necessarily
    more recent than whatever's in customer_profiles (this pipeline never
    writes customer_profiles directly for conversation-extracted facts)."""
    profile = get_profile(customer_id)
    known = profile.model_dump() if profile else {}
    known.update(get_latest_known_extra_values(customer_id))
    return known


def upsert_extra_facts(customer_id: str, facts: dict, source: str = "conversation") -> dict:
    """Persists facts extracted from conversation via the field-history
    table, writing only values that are new or changed versus what's
    already known (never rewrites an unchanged fact every turn). Returns
    the subset of facts actually written."""
    if not facts:
        return {}

    current = get_latest_known_extra_values(customer_id)
    now = datetime.now(timezone.utc)
    written: dict = {}

    with get_connection() as conn:
        # field_history has an FK to customer_profiles -- make sure a row
        # exists so a customer_id with no profile yet can still have facts
        # recorded for them.
        conn.execute(
            "INSERT INTO customer_profiles (customer_id, updated_at) VALUES (%s, %s) "
            "ON CONFLICT (customer_id) DO NOTHING",
            (customer_id, now),
        )
        for field_name, value in facts.items():
            if field_name in current and current[field_name] == value:
                continue
            conn.execute(
                "INSERT INTO customer_profile_field_history "
                "(customer_id, field_name, value, source, recorded_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (customer_id, field_name, Jsonb(value), source, now),
            )
            written[field_name] = value

    return written


def get_field_history(customer_id: str, field_name: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT value, source, recorded_at FROM customer_profile_field_history "
            "WHERE customer_id = %s AND field_name = %s ORDER BY recorded_at",
            (customer_id, field_name),
        ).fetchall()

    return [{"value": value, "source": source, "recorded_at": recorded_at.isoformat()} for value, source, recorded_at in rows]
