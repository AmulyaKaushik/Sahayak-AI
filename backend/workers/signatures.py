"""DSPy typed signatures shared by all worker agents (Section 6: 'DSPy typed
signatures per worker'). Auto-optimization deferred until real conversation
logs exist, per the doc -- these are hand-written prompts for now."""

import dspy


class ExtractFields(dspy.Signature):
    """Extract structured field values the customer explicitly mentioned in
    their message. Only include a field in extracted_fields if it is in
    required_fields AND its value is actually stated in the message --
    never guess or invent a value for a field that wasn't mentioned."""

    message: str = dspy.InputField()
    required_fields: list[str] = dspy.InputField(desc="Field names this worker is allowed to extract.")
    known_fields: dict = dspy.InputField(desc="Fields already known; do not re-derive these from the message.")
    extracted_fields: dict = dspy.OutputField(
        desc="Mapping of field_name -> value for fields newly and explicitly stated in the message. "
        "Empty dict if the message states none of required_fields."
    )


class NarrateEligibility(dspy.Signature):
    """Narrate a deterministic eligibility result for the customer in plain,
    warm language. You MUST cite only the facts given below (eligible,
    satisfied, missing, completion_fraction) -- never invent a number, a
    policy fact, or a reason that isn't present in these fields. State the
    eligibility verdict plainly and unambiguously first."""

    scheme_or_loan_name: str = dspy.InputField()
    eligible: bool = dspy.InputField()
    satisfied: list[str] = dspy.InputField(desc="Requirement labels already met.")
    missing: list[str] = dspy.InputField(desc="Requirement labels not yet met or not yet known.")
    completion_fraction: float = dspy.InputField()
    narration: str = dspy.OutputField(
        desc="2-4 sentence plain-language explanation of the eligible verdict above, "
        "referencing only satisfied/missing, plus a brief benefits note if eligible."
    )
