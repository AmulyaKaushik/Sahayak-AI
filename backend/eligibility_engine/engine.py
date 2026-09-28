"""The only component allowed to produce an eligibility verdict (Section 2,
constraint #2). Plain deterministic code -- no LLM call anywhere in this
module. Worker agents (Phase 4+) call check_eligibility via an MCP tool
(Phase 3) and narrate its output; they never compute or invent it.
"""

from typing import Any

from eligibility_engine.conditions import evaluate_node, evaluate_tree
from eligibility_engine.rules_repository import load_active_rule
from schemas.models import EligibilityResult

# Confidence is not yet computed from anything real: the input-corroboration
# mechanism that would give it meaning (self-reported claims checked against
# on-file KYC data) doesn't exist until Phase 11. Hardcoding 1.0 for now
# rather than inventing an unfounded heuristic; revisit in Phase 11.
_PLACEHOLDER_CONFIDENCE = 1.0


class UnknownSchemeError(ValueError):
    pass


def check_eligibility(scheme_id: str, known_fields: dict[str, Any]) -> EligibilityResult:
    rule = load_active_rule(scheme_id)
    if rule is None:
        raise UnknownSchemeError(f"No active eligibility rule for scheme_id={scheme_id!r}")

    # Reported per top-level requirement, not per nested leaf -- see the
    # rules_seed module docstring for why (an OR-group's untaken branch
    # would otherwise show up as a misleading "missing" item).
    satisfied: list[str] = []
    missing: list[str] = []

    for node in rule.conditions:
        result = evaluate_node(node, known_fields)
        if result is True:
            satisfied.append(node["id"])
        else:
            missing.append(node["id"])

    completion_fraction = len(satisfied) / len(rule.conditions) if rule.conditions else 0.0
    eligible = evaluate_tree(rule.conditions, known_fields) is True

    return EligibilityResult(
        scheme_id=scheme_id,
        eligible=eligible,
        satisfied=satisfied,
        missing=missing,
        completion_fraction=completion_fraction,
        confidence=_PLACEHOLDER_CONFIDENCE,
        rule_source=f"scheme_rules_v{rule.version}",
        rule_updated_at=rule.updated_at.date().isoformat(),
    )
