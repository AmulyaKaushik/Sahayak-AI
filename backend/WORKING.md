# Sahayak AI Backend — Working Guide

Status: Phases 0-4 are built and tested, plus a session-aware `/api/v1/query`
pipeline (sentence in -> unconditional fact extraction -> turn classification
-> worker(s) -> structured answer out) covering 9 hand-encoded schemes/loans.
RAG, document ingestion, the rest of the mobile-facing `/api/v1/...`
contract, offline resilience, security hardening, and final test/demo prep
are not yet built.

## 1. Prerequisites

- Python 3.13
- Docker Desktop (for Postgres + Redis)
- A Groq API key (for worker agent LLM calls — field extraction + narration)

## 2. One-time setup

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Create a `.env` file at the repo root:

```
DATABASE_URL=postgresql://sahayak:sahayak@localhost:5432/sahayak
REDIS_URL=redis://localhost:6379/0
GROQ_API_KEY=<your Groq key>
```

(`DATABASE_URL`/`REDIS_URL` have working defaults in `settings.py` if you
don't set them — only `GROQ_API_KEY` is required for worker-agent features
to run.)

## 3. Start the infrastructure

```
docker compose up -d postgres redis
```

This starts Postgres and Redis only (not the `app` container — for
day-to-day dev, run the app directly with `uvicorn` so code changes are
picked up without a rebuild; `docker compose up -d --build` brings up the
full containerized stack, including `app`, if you want that instead).

## 4. Apply migrations and seed data

```
.venv/Scripts/python.exe -m database.migrate
.venv/Scripts/python.exe -m scripts.seed_sample_data
.venv/Scripts/python.exe -m scripts.seed_sample_profiles
```

`migrate.py` is idempotent — safe to re-run. `seed_sample_data.py` seeds:
- The 9 hand-encoded eligibility rules (Phase 2) into `eligibility_rules`.
- 11 sample customer profiles into `customer_profiles` (see the table below).

`seed_sample_profiles.py` seeds 3 more customers (`cust-101`, `cust-102`,
`cust-103`) specifically for exercising `/api/v1/query` — see section 9b.

## 5. Run the app

```
.venv/Scripts/python.exe -m uvicorn main:app --reload --reload-exclude .venv
```

Serves on `http://127.0.0.1:8000`. Interactive API docs at `/docs`.

**`--reload-exclude .venv` matters here.** The venv lives inside the project
folder, so without it `--reload` watches every file under `.venv` too. If
anything touches those files while the server is running — a `pip install`
in another terminal, or (more likely for this repo) OneDrive re-syncing
`.venv` in the background since the project sits under `OneDrive\Desktop` —
you can hit a reload mid-write and get an `ImportError` from a package that
was only partially readable at that instant (this happened with
`pydantic-settings` during this session; fixed with a `--force-reinstall`,
but the exclude flag stops it from recurring). If you keep seeing random
import errors on reload, consider excluding `.venv/` from OneDrive sync
entirely (right-click the folder → "Always keep on this device" is the
wrong direction; you want to exclude it from sync, e.g. via OneDrive
Settings → Sync and backup → choose folders, or move `.venv` outside the
OneDrive tree).

## 6. Run the tests

```
.venv/Scripts/python.exe -m pytest -q
```

Requires Postgres, Redis, and `GROQ_API_KEY` to all be available (the
worker-agent tests make real Groq calls). 28 tests, all passing as of Phase 4.

## 7. Prove it works: the demo script

```
.venv/Scripts/python.exe -m scripts.demo_check_eligibility
```

Runs the deterministic engine over all 11 sample cases and prints the fixed
Section 4.3 result shape for each, then runs one case through a real worker
agent (LLM narration over Groq) so you can see the whole
extract → check_eligibility → narrate pipeline end to end in one command.

## 8. Sample data reference

| customer_id | Who | Demonstrates |
|---|---|---|
| `cust-001` | Meena, 32, salaried | Eligible for `sukanya_samriddhi` (needs `has_girl_child_under_10` supplied separately — not a CustomerProfile field) |
| `cust-002` | Ramesh, 22 | Eligible for `pm_jan_dhan_yojana` |
| `cust-003` | Suresh, 29, daily wage | Eligible for `pmay_rural_housing_subsidy` |
| `cust-004` | Ganpat, 50, farmer | Eligible for `kisan_credit_card` |
| `cust-005` | Priya, 35, salaried | Eligible for `retail_micro_loan` (via the OR-group's salaried branch) |
| `cust-006` | Krishnan, 68 | Eligible for `senior_citizen_savings_scheme` |
| `cust-007` | Anita, 45, income too high | **Not** eligible for `pmay_rural_housing_subsidy` — negative case |
| `cust-008` | Farida, 28 | **Partially** eligible for `sukanya_samriddhi` (girl-child fact not yet known — `completion_fraction = 0.5`) |
| `cust-009` | Irfan, 27, self-employed | Eligible for `pm_mudra_yojana_shishu` (micro-business loan) |
| `cust-010` | Kavita, 33, self-employed | Eligible for `home_loan` (regular housing loan, distinct from the PMAY subsidy) |
| `cust-011` | Naveen, 25, government employee | **Not** eligible for `atal_pension_yojana` — negative case |

Full definitions, including each case's supplementary `extra_fields`, are in
`scripts/sample_data.py`.

## 9. What's runnable right now, feature by feature

All endpoints below are direct-call/testing endpoints from Phase 1 — they are
**not** the mobile client contract (that's a separate, not-yet-built API
layer). There is no authorization on these routes — auth is being built
separately (by a teammate) and will sit in front of this backend rather than
inside it, so nothing here checks who's calling.

### Health

```
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/deps
```

### Customer profile store (Phase 1 — versioned upsert)

```
curl -X PUT http://127.0.0.1:8000/profiles/cust-001 \
  -H "Content-Type: application/json" \
  -d "{\"customer_id\":\"cust-001\",\"monthly_income\":19000,\"age\":32,\"dependents\":1,\"employment_type\":\"salaried\",\"existing_products\":[],\"language_preference\":\"hi\"}"

curl http://127.0.0.1:8000/profiles/cust-001

curl http://127.0.0.1:8000/profiles/cust-001/history/monthly_income
```

The history call shows the old `monthly_income` (18000) archived with a
timestamp after the PUT above changes it to 19000 — that's the versioned
upsert / single-writer audit trail from Phase 1.

### Session context store (Phase 1 — Redis-backed, supervisor-only writer)

```
curl -X POST http://127.0.0.1:8000/session-context/session-1 \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"session-1\",\"turn_index\":0,\"summary\":\"Customer asked about a loan.\",\"fields_collected_this_session\":{},\"workers_called\":[],\"written_by\":\"supervisor\"}"

curl http://127.0.0.1:8000/session-context/session-1
```

### Deterministic eligibility engine (Phase 2 — no LLM, no HTTP route yet)

Not exposed over HTTP yet (that comes with the mobile contract layer). Call
it directly in Python:

```python
from eligibility_engine.engine import check_eligibility
check_eligibility("kisan_credit_card", {"employment_type": "farmer", "land_holding_acres": 2.5, "age": 45})
```

Or run `scripts/demo_check_eligibility.py` (section 7 above) to see all 6
schemes exercised at once.

### MCP tools (Phase 3)

`mcp_servers/eligibility_server.py` exposes `check_eligibility`,
`calculate_emi`, `calculate_maturity_amount` as MCP tools;
`mcp_servers/db_manager_server.py` exposes `get_customer_profile`,
`upsert_customer_profile`, `get_field_history`. Not run as a standalone MCP
server process yet — currently called in-process (see
`tests/test_mcp_tools.py` for examples), the same way the Phase 4 workers
call `check_eligibility` under the hood.

### Worker agents (Phase 4 — real Groq LLM calls)

```python
import asyncio
from schemas.models import CustomerProfile
from workers.scheme_agent.agent import SchemeAgent
from eligibility_engine.rules_repository import get_required_field_names

profile = CustomerProfile(customer_id="cust-006", monthly_income=8000, age=68,
                           dependents=0, employment_type=None, existing_products=[],
                           language_preference="ta")
worker = SchemeAgent()
result = asyncio.run(worker.handle_query(
    "I'm 68, can I open a senior citizen savings account?",
    profile, "senior_citizen_savings_scheme",
    get_required_field_names("senior_citizen_savings_scheme"),
))
print(result.eligible, result.narration)
```

`LoanAgent` handles `kisan_credit_card` and `retail_micro_loan`; `SchemeAgent`
handles the other 4 schemes.

### `/api/v1/query` — the full pipeline, session-aware, fact-persistent

Every turn, unconditionally: extract facts from the message against the
union of *every* scheme's required fields (not just one scheme) → persist
genuinely new/changed facts per-customer (so they're known in *future
sessions too*, not just this conversation) → *then* classify the turn into
exactly one of three cases:
- a new single-scheme/loan question → check just that scheme_id
- a new enumerate question ("which all X am I eligible for") → check every
  scheme_id in that domain
- no question at all, just a fact → re-check whichever scheme_id(s) were
  discussed earlier this session and are still unresolved, using the new
  fact; if nothing was discussed yet, just acknowledge the fact was
  recorded — this never errors

```
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d "{\"customer_id\":\"cust-101\",\"session_id\":\"11111111-1111-1111-1111-111111111111\",\"text\":\"Can I get a retail micro loan?\"}"
```

Response shape: `{"reply_text": str, "results": [{"scheme_id", "eligible", "satisfied", "missing"}, ...], "facts_updated": [str, ...], "turn_type": "new_question" | "recheck_unresolved" | "acknowledgment"}`.
`results` is `[]` for an `acknowledgment` turn. When a scheme isn't
eligible, `reply_text` names what's still needed in plain terms (e.g. "how
many acres of land you own"), not just the internal requirement id
(`has_land_holding`) — a numeric field like acreage needs an actual
quantity, and the extractor correctly won't invent one from a vague "I do
have land holding", so the prompt has to be explicit about what to say
instead (`supervisor/agent.py`'s `FIELD_PROMPTS`). On an unroutable
eligibility question, returns HTTP 422 with `{"error": {"code", "message"}}` — a
message with no question in it at all (e.g. small talk) is *not* an error,
it's an `acknowledgment`.

**Worked example — the gap this was built to fix** (a follow-up naming
neither the scheme nor repeating the original question):

```
curl -X POST http://127.0.0.1:8000/api/v1/query -H "Content-Type: application/json" \
  -d "{\"customer_id\":\"cust-301\",\"session_id\":\"<same-uuid>\",\"text\":\"Can I open a Sukanya Samriddhi account? I am 30.\"}"
# -> eligible: false, missing: ["girl_child_under_10"], turn_type: new_question

curl -X POST http://127.0.0.1:8000/api/v1/query -H "Content-Type: application/json" \
  -d "{\"customer_id\":\"cust-301\",\"session_id\":\"<same-uuid>\",\"text\":\"I have a girl who is 8\"}"
# -> eligible: true, satisfied: ["girl_child_under_10", "guardian_age_requirement"], turn_type: recheck_unresolved
```

Because facts persist per-customer (not just per-session), that second fact
is *also* known in a brand-new session for `cust-301` from then on.

Scheme-specific facts that don't live in `CustomerProfile` (e.g.
`has_girl_child_under_10`, `owns_pucca_house`, `is_first_time_home_buyer`,
`land_holding_acres`) can still be supplied directly via the request's
`extra_fields` for a one-off override, on top of whatever's been extracted
and persisted from the conversation itself:

```
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d "{\"customer_id\":\"cust-201\",\"session_id\":\"<uuid>\",\"text\":\"Can I open a Sukanya Samriddhi account? I am 30.\",\"extra_fields\":{\"has_girl_child_under_10\":true}}"
```

Phrase single-scheme queries close to the actual `scheme_id` names ("retail
micro loan", "Kisan Credit Card", "Jan Dhan account") — the domain/scheme
classifier only sees the bare `scheme_id` strings (no human-readable
descriptions), so it deliberately falls back to enumerate-mode instead of
guessing on vaguer phrasing like "personal loan" when more than one loan
product could plausibly match.

**cust-101 / cust-102 / cust-103** (from `seed_sample_profiles.py`) are built
specifically to exercise this endpoint — see the "eligible for both a loan
and a scheme", "missing 2 fields", and "hard-fails outright" cases described
next to the seed script's output.

### CLI (`scripts/cli.py`)

Interactive REPL over the same pipeline function the HTTP route uses — no
server needs to be running. Either invocation form works (run from the repo
root):

```
.venv/Scripts/python.exe scripts/cli.py
.venv/Scripts/python.exe -m scripts.cli --extra-fields "{\"has_girl_child_under_10\": true}"
```

Prompts once for `customer_id`, generates one `session_id` (shown on
screen) and reuses it for every query. Prints `facts_updated` distinctly
when a turn captures new information, and tags each reply with its
`turn_type` (`new_question` / `recheck_unresolved` / `acknowledgment`).
`quit`/`exit` to leave, `new session` to reset to a fresh `session_id`
without restarting the process (facts persisted per-customer still carry
over even after `new session`, by design — only the session's own memory
resets).

## 10. Not built yet

- `/api/v1/query`'s session memory doesn't track a running conversation
  summary or session archival/expiry (Section 4.5's `summary` field is set
  to a terse one-liner each turn, not a real rolling summary).
- Scheme-specific extra facts (`has_girl_child_under_10`,
  `owns_pucca_house`, `is_first_time_home_buyer`, `land_holding_acres`,
  ...) are persisted, but **not** through a new `CustomerProfile` column —
  `CustomerProfile` still has exactly 6 fixed fields. They're stored via
  the same EAV-style `customer_profile_field_history` table the versioned-
  upsert audit trail already used (see `db_manager/repository.py`'s
  `upsert_extra_facts`/`get_known_fields`), which only worked because that
  table was already `field_name TEXT` / `value JSONB` with no column
  constraints tying it to the 6 core fields. Reading `get_profile()`
  directly (e.g. via `/profiles/{id}`) still won't show these — only the
  query pipeline's combined `get_known_fields()` view does.
- DB-backed required-fields registry — `schemas/required_fields_seed.py` is
  hand-authored and in-code, not in Postgres (Phase 4 also has a derived
  stand-in, `get_required_field_names`, unrelated to this one)
- RAG / knowledge base, document ingestion + human rule approval (Phases 7-8)
- The mobile-facing `/api/v1/health`, `/api/v1/sessions`,
  `/api/v1/sessions/{id}/messages` contract (pending the API contract doc)
- Offline resilience layer, security hardening, narration/threshold polish,
  kiosk UX, final CI/demo prep (Phases 10-14)
