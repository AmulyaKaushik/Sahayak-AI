"""Base worker agent: LLM + a fixed set of MCP tools scoped to its domain
(Section 4.2). Extracts fields, calls the eligibility engine via MCP, and
narrates -- never decides eligibility itself (Section 2, constraint #2).

Read-only against session context and customer profile stores (Section 2,
constraint #3): this class is never given a reference to any store's write
method -- only schemas.models.CustomerProfile data passed in by the caller
and, from Phase 5 onward, a supervisor.context_store.ReadOnlyContextView."""

import dspy

from mcp_servers.eligibility_server import mcp as eligibility_mcp
from schemas.models import CustomerProfile
from settings import settings
from workers.models import WorkerNarrationResult
from workers.narration_guard import fallback_narration, narration_contradicts_verdict
from workers.signatures import ExtractFields, NarrateEligibility


def build_lm() -> dspy.LM:
    return dspy.LM(settings.worker_llm_model, api_key=settings.groq_api_key)


class BaseWorkerAgent:
    domain_scheme_ids: list[str] = []

    def __init__(self, lm: dspy.LM | None = None):
        self._lm = lm or build_lm()
        self._extract = dspy.Predict(ExtractFields)
        self._narrate = dspy.Predict(NarrateEligibility)

    async def handle_query(
        self,
        message: str,
        profile: CustomerProfile,
        scheme_id: str,
        required_fields: list[str],
    ) -> WorkerNarrationResult:
        if scheme_id not in self.domain_scheme_ids:
            raise ValueError(f"{type(self).__name__} does not handle scheme_id={scheme_id!r}")

        known_fields = profile.model_dump()

        with dspy.context(lm=self._lm):
            extraction = self._extract(
                message=message, required_fields=required_fields, known_fields=known_fields
            )

        tool_result = await eligibility_mcp.call_tool(
            "check_eligibility",
            {
                "profile": profile.model_dump(),
                "scheme_id": scheme_id,
                "extra_fields": extraction.extracted_fields,
            },
        )
        engine_result = tool_result.structured_content

        with dspy.context(lm=self._lm):
            narration = self._narrate(
                scheme_or_loan_name=scheme_id,
                eligible=engine_result["eligible"],
                satisfied=engine_result["satisfied"],
                missing=engine_result["missing"],
                completion_fraction=engine_result["completion_fraction"],
            ).narration

        if narration_contradicts_verdict(narration, engine_result["eligible"]):
            narration = fallback_narration(
                scheme_id, engine_result["eligible"], engine_result["satisfied"], engine_result["missing"]
            )

        return WorkerNarrationResult(
            scheme_id=scheme_id,
            eligible=engine_result["eligible"],
            satisfied=engine_result["satisfied"],
            missing=engine_result["missing"],
            completion_fraction=engine_result["completion_fraction"],
            narration=narration,
            extracted_fields=extraction.extracted_fields,
        )
