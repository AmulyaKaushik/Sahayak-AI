"""Field catalogue that drives the app's profile form (GET /api/v1/profile/schema).

Core fields map to customer_profiles columns; every other field comes from
required_fields_seed.py, so a field a new scheme needs appears in the app
without an app release. Labels reuse supervisor.agent.FIELD_PROMPTS-style
wording but are kept here to avoid importing the LLM pipeline for a form."""

from pydantic import BaseModel

from schemas.required_fields_seed import REQUIRED_FIELDS_ENTRIES


class ProfileFieldSpec(BaseModel):
    field: str
    label: str
    type: str  # "number" | "text" | "boolean" | "select" | "multiselect"
    options: list[str] = []
    required: bool = False


EMPLOYMENT_TYPES = ["salaried", "self_employed", "farmer", "government_employee"]

_SPECS: dict[str, ProfileFieldSpec] = {
    s.field: s
    for s in [
        ProfileFieldSpec(field="age", label="Your age", type="number", required=True),
        ProfileFieldSpec(field="monthly_income", label="Monthly income (Rs)", type="number", required=True),
        ProfileFieldSpec(field="dependents", label="Number of dependents", type="number"),
        ProfileFieldSpec(
            field="employment_type", label="Employment type", type="select",
            options=EMPLOYMENT_TYPES, required=True,
        ),
        ProfileFieldSpec(
            field="existing_products", label="Bank products or accounts you already have",
            type="multiselect",
        ),
        ProfileFieldSpec(
            field="language_preference", label="Preferred language", type="select",
            options=["en-IN", "hi-IN", "bn-IN", "mr-IN", "ta-IN", "te-IN", "gu-IN", "kn-IN", "ml-IN", "pa-IN"],
        ),
        ProfileFieldSpec(field="has_girl_child_under_10", label="Do you have a girl child under 10?", type="boolean"),
        ProfileFieldSpec(field="owns_pucca_house", label="Do you own a pucca (permanent) house?", type="boolean"),
        ProfileFieldSpec(field="is_first_time_home_buyer", label="Is this your first home purchase?", type="boolean"),
        ProfileFieldSpec(field="land_holding_acres", label="Land you own (acres)", type="number"),
        ProfileFieldSpec(field="has_business_plan", label="Do you have a business plan?", type="boolean"),
        ProfileFieldSpec(field="has_property_papers", label="Do you have the property papers ready?", type="boolean"),
    ]
}

# customer_profiles columns; everything else is an "extra fact".
CORE_FIELDS = [
    "monthly_income", "age", "dependents", "employment_type",
    "existing_products", "language_preference",
]


def get_profile_schema() -> list[ProfileFieldSpec]:
    needed: list[str] = list(CORE_FIELDS)
    for entry in REQUIRED_FIELDS_ENTRIES:
        for field in entry.required_fields:
            if field not in needed:
                needed.append(field)

    specs = []
    for field in needed:
        specs.append(
            _SPECS.get(field)
            or ProfileFieldSpec(field=field, label=field.replace("_", " ").capitalize(), type="text")
        )
    return specs


# --- Value validation (PATCH /me/profile) -----------------------------------
# Stored values are later compared by the rule engine (">=", "in", ...), so a
# wrong type saved here would break eligibility checks. Reject it up front.

INTEGER_FIELDS = {"age", "dependents"}
_MAX_NUMBER = 1_000_000_000
_MAX_TEXT = 200
_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}


class InvalidProfileValue(ValueError):
    pass


def _number(field: str, value):
    if isinstance(value, bool):
        raise InvalidProfileValue(f"{field} must be a number")
    if isinstance(value, str):
        try:
            value = float(value.strip().replace(",", ""))
        except ValueError:
            raise InvalidProfileValue(f"{field} must be a number")
    if not isinstance(value, (int, float)) or value != value or abs(value) > _MAX_NUMBER:
        raise InvalidProfileValue(f"{field} must be a number")
    if value < 0:
        raise InvalidProfileValue(f"{field} cannot be negative")
    if field in INTEGER_FIELDS:
        if value != int(value):
            raise InvalidProfileValue(f"{field} must be a whole number")
        value = int(value)
        if field == "age" and value > 120:
            raise InvalidProfileValue("age must be between 0 and 120")
    return value


def validate_profile_value(spec: ProfileFieldSpec, value):
    """Returns the value in its canonical type, or raises InvalidProfileValue.
    None is allowed and means "clear this field"."""
    field = spec.field
    if value is None:
        return None

    if spec.type == "number":
        return _number(field, value)

    if spec.type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            return value.strip().lower() in _TRUE
        raise InvalidProfileValue(f"{field} must be true or false")

    if spec.type == "select":
        if not isinstance(value, str) or (spec.options and value not in spec.options):
            raise InvalidProfileValue(f"{field} must be one of: {', '.join(spec.options)}")
        return value

    if spec.type == "multiselect":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise InvalidProfileValue(f"{field} must be a list of text values")
        if spec.options and any(v not in spec.options for v in value):
            raise InvalidProfileValue(f"{field} has an unknown option")
        return [v.strip() for v in value if v.strip()][:50]

    # "text"
    if not isinstance(value, str) or len(value) > _MAX_TEXT:
        raise InvalidProfileValue(f"{field} must be text of at most {_MAX_TEXT} characters")
    return value.strip()
