"""MCP tool wrappers around the deterministic eligibility engine and its
calculators (Section 4.3). Every tool has a strict, typed input/output
schema -- the MCP layer rejects malformed input before it ever reaches
eligibility_engine code (Phase 3 test)."""

from mcp.server.mcpserver import MCPServer

from eligibility_engine.calculators import calculate_emi as _calculate_emi
from eligibility_engine.calculators import calculate_maturity_amount as _calculate_maturity_amount
from eligibility_engine.engine import check_eligibility as _check_eligibility
from schemas.models import CustomerProfile, EligibilityResult

mcp = MCPServer("eligibility-tools")


@mcp.tool()
def check_eligibility(
    profile: CustomerProfile, scheme_id: str, extra_fields: dict = {}
) -> EligibilityResult:
    """Deterministically check eligibility for one scheme/loan type.
    No LLM call is involved -- this is the only component allowed to
    produce an eligibility verdict (Section 2, constraint #2)."""
    known_fields = {**profile.model_dump(), **extra_fields}
    return _check_eligibility(scheme_id, known_fields)


@mcp.tool()
def calculate_emi(principal: float, annual_rate_percent: float, tenure_months: int) -> dict:
    """Deterministic EMI calculator for loan products."""
    return _calculate_emi(principal, annual_rate_percent, tenure_months)


@mcp.tool()
def calculate_maturity_amount(principal: float, annual_rate_percent: float, tenure_years: int) -> dict:
    """Deterministic maturity-value calculator for savings schemes (annual compounding)."""
    return _calculate_maturity_amount(principal, annual_rate_percent, tenure_years)


if __name__ == "__main__":
    mcp.run()
