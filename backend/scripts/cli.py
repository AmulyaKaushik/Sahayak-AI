"""Interactive REPL for testing the /api/v1/query pipeline without curl or a
mobile app. Calls supervisor.agent.run_query_pipeline() directly, in-process
-- the same function the FastAPI route uses, so there's exactly one pipeline
implementation for both.

Run from the repo root, either form works:
    python scripts/cli.py
    python -m scripts.cli
Optional: --extra-fields "{\"has_girl_child_under_10\": true}"
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

# Makes `python scripts/cli.py` work too, not just `python -m scripts.cli` --
# running the file directly puts scripts/ on sys.path instead of the repo
# root, so the top-level packages (supervisor, workers, ...) wouldn't
# otherwise be importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supervisor.agent import PipelineError, QueryResponse, run_query_pipeline  # noqa: E402

_QUIT_WORDS = {"quit", "exit"}
_NEW_SESSION_WORDS = {"new session"}


def print_response(response: QueryResponse) -> None:
    print(f"\n[{response.turn_type}] {response.reply_text}\n")
    if response.facts_updated:
        print(f"  facts updated: {', '.join(response.facts_updated)}")
    for result in response.results:
        status = "ELIGIBLE" if result.eligible else "NOT ELIGIBLE"
        print(f"  [{result.scheme_id}] {status}")
        if result.satisfied:
            print(f"    satisfied: {', '.join(result.satisfied)}")
        if result.missing:
            print(f"    missing:   {', '.join(result.missing)}")
    print()


def print_error(error: PipelineError) -> None:
    print(f"\n[error] {error.code}: {error.message}\n")


async def run_repl(extra_fields: dict) -> None:
    print("Sahayak AI query CLI. Type 'quit'/'exit' to leave, 'new session' to reset.\n")

    try:
        customer_id = input("customer_id: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    session_id = str(uuid.uuid4())
    print(f"session_id: {session_id}\n")

    while True:
        try:
            text = input("query> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if text.lower() in _QUIT_WORDS:
            break
        if text.lower() in _NEW_SESSION_WORDS:
            session_id = str(uuid.uuid4())
            print(f"\nStarted a new session: {session_id}\n")
            continue
        if not text:
            continue

        try:
            response = await run_query_pipeline(customer_id, session_id, text, extra_fields)
            print_response(response)
        except PipelineError as exc:
            print_error(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive CLI for the Sahayak AI query pipeline.")
    parser.add_argument(
        "--extra-fields",
        default="{}",
        help='JSON string of scheme-specific facts, e.g. \'{"has_girl_child_under_10": true}\'',
    )
    args = parser.parse_args()

    try:
        extra_fields = json.loads(args.extra_fields)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--extra-fields must be valid JSON: {exc}")

    asyncio.run(run_repl(extra_fields))


if __name__ == "__main__":
    main()
