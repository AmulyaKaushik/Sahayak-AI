"""Authenticated profile endpoints: the customer is always the token's
customer_id, never a path/body value."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from db_manager import repository
from schemas.models import CustomerProfile
from schemas.profile_schema import (
    CORE_FIELDS,
    InvalidProfileValue,
    ProfileFieldSpec,
    get_profile_schema,
    validate_profile_value,
)
from security import repository as auth_repository
from security.auth import get_current_customer_id

router = APIRouter(prefix="/api/v1", tags=["profile"])


def _profile_response(customer_id: str) -> dict:
    return {
        "fields": repository.get_known_fields(customer_id),
        "profile_completed": auth_repository.is_profile_completed(customer_id),
    }


@router.get("/profile/schema", response_model=list[ProfileFieldSpec])
def profile_schema(customer_id: str = Depends(get_current_customer_id)):
    return get_profile_schema()


@router.get("/me/profile")
def read_my_profile(customer_id: str = Depends(get_current_customer_id)) -> dict:
    response = _profile_response(customer_id)
    response["fields"].pop("customer_id", None)
    return response


@router.patch("/me/profile")
def update_my_profile(
    updates: dict[str, Any], customer_id: str = Depends(get_current_customer_id)
) -> dict:
    """Partial update. Core fields go through upsert_profile (versioned
    history kept); anything else is stored as an extra fact -- the same
    store the chatbot writes to, so form and conversation stay in sync."""
    updates = {k: v for k, v in updates.items() if k != "customer_id"}
    specs = {spec.field: spec for spec in get_profile_schema()}
    unknown = sorted(set(updates) - set(specs))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown profile field(s): {', '.join(unknown)}")

    try:
        updates = {field: validate_profile_value(specs[field], v) for field, v in updates.items()}
    except InvalidProfileValue as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    core_updates = {k: v for k, v in updates.items() if k in CORE_FIELDS}
    extra_updates = {k: v for k, v in updates.items() if k not in CORE_FIELDS}

    if core_updates:
        current = repository.get_profile(customer_id)
        base = current.model_dump() if current else {"customer_id": customer_id}
        merged = {**base, **core_updates}
        try:
            profile = CustomerProfile(
                customer_id=customer_id,
                monthly_income=merged.get("monthly_income"),
                age=merged.get("age"),
                dependents=merged.get("dependents"),
                employment_type=merged.get("employment_type"),
                existing_products=merged.get("existing_products") or [],
                language_preference=merged.get("language_preference"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        repository.upsert_profile(profile, source="user_form")

    if extra_updates:
        repository.upsert_extra_facts(customer_id, extra_updates, source="user_form")

    # Any save counts, including an empty PATCH {} -- that is how the app's
    # "Skip" on onboarding unblocks the chat.
    auth_repository.mark_profile_completed(customer_id)

    response = _profile_response(customer_id)
    response["fields"].pop("customer_id", None)
    return response
