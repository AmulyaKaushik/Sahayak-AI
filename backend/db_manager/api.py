from fastapi import APIRouter, HTTPException

from db_manager import repository
from schemas.models import CustomerProfile

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.put("/{customer_id}", response_model=CustomerProfile)
def upsert_profile(customer_id: str, profile: CustomerProfile) -> CustomerProfile:
    if profile.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="customer_id mismatch")
    return repository.upsert_profile(profile)


@router.get("/{customer_id}", response_model=CustomerProfile)
def read_profile(customer_id: str) -> CustomerProfile:
    profile = repository.get_profile(customer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.get("/{customer_id}/history/{field_name}")
def read_field_history(customer_id: str, field_name: str) -> list[dict]:
    return repository.get_field_history(customer_id, field_name)
