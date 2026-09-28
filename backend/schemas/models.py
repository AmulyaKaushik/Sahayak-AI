from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


# Customer Profile (persistent, JWT-gated)
class CustomerProfile(BaseModel):
    customer_id: str
    monthly_income: float | None
    age: int | None
    dependents: int | None
    employment_type: str | None
    existing_products: list[str] = []
    language_preference: str | None
    # each field internally versioned: {value, source, updated_at, previous[]}


# Internal representation of one archived prior value for a CustomerProfile field.
# Not one of the Section 5 models itself -- it is what the CustomerProfile comment
# above ("each field internally versioned") refers to, used by the DB manager's
# versioned-upsert audit trail (customer_profile_field_history table).
class VersionedFieldRecord(BaseModel):
    value: Any
    source: str | None
    updated_at: datetime


# Required Fields Registry entry
class RequiredFieldsEntry(BaseModel):
    scheme_or_loan_id: str
    required_fields: list[str]


# Eligibility Rule (versioned config, human-approved)
class EligibilityRule(BaseModel):
    scheme_id: str
    version: int
    conditions: list[dict]  # field/op/value triples, AND/OR structure
    source_document: str
    approved_by: str
    updated_at: datetime


# Eligibility Result (engine output -- fixed shape, Section 4.3)
class EligibilityResult(BaseModel):
    scheme_id: str
    eligible: bool
    satisfied: list[str]
    missing: list[str]
    completion_fraction: float
    confidence: float
    rule_source: str
    rule_updated_at: str


# Session Context entry
class ContextEntry(BaseModel):
    session_id: str
    turn_index: int
    summary: str
    fields_collected_this_session: dict
    workers_called: list[str]
    written_by: Literal["supervisor"]  # enforced, never a worker
