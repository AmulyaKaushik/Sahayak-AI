"""Per-scheme partial-eligibility threshold config (Section 4.3).

Not part of the fixed EligibilityRule schema (Section 5) or the fixed
EligibilityResult output shape (Section 4.3) -- this is a separate,
engine-internal config the narration layer consults to decide whether a
"potentially eligible" message should be shown at all, always alongside
the explicit missing[] list and a disclaimer (Phase 12 wires the message
itself; this phase only provides the deterministic threshold check).
"""

DEFAULT_THRESHOLD = 0.6

PARTIAL_ELIGIBILITY_THRESHOLDS: dict[str, float] = {
    "sukanya_samriddhi": 0.6,
    "pm_jan_dhan_yojana": 0.5,
    "pmay_rural_housing_subsidy": 0.65,
    "kisan_credit_card": 0.7,
    "retail_micro_loan": 0.75,
    "senior_citizen_savings_scheme": 0.6,
}


def meets_partial_eligibility_threshold(scheme_id: str, completion_fraction: float) -> bool:
    threshold = PARTIAL_ELIGIBILITY_THRESHOLDS.get(scheme_id, DEFAULT_THRESHOLD)
    return completion_fraction >= threshold
