"""Runs the deterministic eligibility engine over every sample case and
prints the fixed-shape result (Section 4.3), then runs ONE case through a
real worker agent (LLM narration over Groq) to demonstrate the full
narrate-without-deciding pipeline end to end.

Run: python -m scripts.demo_check_eligibility
"""

import asyncio
import json

from eligibility_engine.engine import check_eligibility
from eligibility_engine.rules_repository import get_required_field_names
from scripts.sample_data import SAMPLE_CASES
from workers.scheme_agent.agent import SchemeAgent


def run_engine_only_demo() -> None:
    print("=== Deterministic eligibility engine (no LLM) ===\n")
    for case in SAMPLE_CASES:
        known_fields = {**case["profile"].model_dump(), **case["extra_fields"]}
        result = check_eligibility(case["scheme_id"], known_fields)
        print(f"-- {case['label']}")
        print(json.dumps(result.model_dump(), indent=2))
        print()


async def run_worker_narration_demo() -> None:
    print("=== One case through the Scheme worker agent (real LLM narration) ===\n")
    case = SAMPLE_CASES[0]  # Meena, Sukanya Samriddhi
    profile = case["profile"]
    scheme_id = case["scheme_id"]
    required_fields = get_required_field_names(scheme_id)

    worker = SchemeAgent()
    result = await worker.handle_query(
        message="My daughter is 4 years old, can I open a Sukanya Samriddhi account for her?",
        profile=profile,
        scheme_id=scheme_id,
        required_fields=required_fields,
    )
    print(f"customer_id={profile.customer_id} scheme_id={scheme_id}")
    print(f"extracted_fields={result.extracted_fields}")
    print(f"eligible={result.eligible} satisfied={result.satisfied} missing={result.missing}")
    print(f"narration: {result.narration}")


if __name__ == "__main__":
    run_engine_only_demo()
    asyncio.run(run_worker_narration_demo())
