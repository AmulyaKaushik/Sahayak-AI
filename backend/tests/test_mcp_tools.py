"""Phase 3: any MCP client can call check_eligibility(profile, scheme_id) and
get back the Phase 2 result, and malformed tool input is rejected by the MCP
layer's schema validation before it ever reaches eligibility_engine code."""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_servers.eligibility_server import mcp as eligibility_mcp

VALID_PROFILE = {
    "customer_id": "cust-mcp-test",
    "monthly_income": None,
    "age": 65,
    "dependents": None,
    "employment_type": None,
    "existing_products": [],
    "language_preference": None,
}


@pytest.mark.asyncio
async def test_check_eligibility_tool_returns_phase2_result_shape():
    result = await eligibility_mcp.call_tool(
        "check_eligibility",
        {"profile": VALID_PROFILE, "scheme_id": "senior_citizen_savings_scheme"},
    )
    assert result.is_error is False
    assert result.structured_content == {
        "scheme_id": "senior_citizen_savings_scheme",
        "eligible": True,
        "satisfied": ["minimum_age_60"],
        "missing": [],
        "completion_fraction": 1.0,
        "confidence": 1.0,
        "rule_source": "scheme_rules_v1",
        "rule_updated_at": "2026-09-01",
    }


@pytest.mark.asyncio
async def test_malformed_tool_input_rejected_before_reaching_engine():
    malformed_profile = {"customer_id": "cust-mcp-test"}  # missing required fields

    with pytest.raises(ToolError):
        await eligibility_mcp.call_tool(
            "check_eligibility",
            {"profile": malformed_profile, "scheme_id": 123},  # wrong type too
        )


@pytest.mark.asyncio
async def test_malformed_calculator_input_rejected():
    with pytest.raises(ToolError):
        await eligibility_mcp.call_tool(
            "calculate_emi",
            {"principal": "not-a-number", "annual_rate_percent": 8.5, "tenure_months": 12},
        )
