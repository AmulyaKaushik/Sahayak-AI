# Sahayak AI — Architecture, Implementation Status & Roadmap

Multilingual, voice-first assistant that tells customers which bank loans and government schemes they qualify for, and answers questions about what the official documents say. Originally designed as a branch kiosk; **now delivered as a mobile app (Expo / React Native) talking to a cloud-hostable FastAPI backend.**

*Last updated: 2026-11-15. This document started as the frozen design; it now records the design **as built**, what changed from the original plan and why, the known issues, and what is still to do. Sections 9, 12 and 13 are the quickest way to see where the project stands.*

---

## 0. Where the project stands (summary)

| Area | Status |
|---|---|
| Deterministic eligibility engine (9 hand-coded schemes) | **Done, tested** |
| Profile store with versioned history + cross-session facts | **Done, tested** |
| Auth (register / login / refresh, JWT), server-owned sessions | **Done, tested** |
| Sahayak_AI layer (router → agents → refiner) | **Done, tested live** |
| Eligibility agent (fact extraction → rules → reply) | **Done, tested live** |
| RAG agent + PDF ingestion + folder sync (Gemini embeddings, pgvector) | **Done, verified with one real PDF** |
| Speech-to-text proxy (Groq Whisper behind the backend) | **Done** (not yet used by the app) |
| Backend test suite | **109 passing** (about 13–80 s depending on Groq load) |
| Cloud deployment | **Not done** (runs locally via Docker Compose) |
| Mobile app ↔ backend connection | **Not done** — app still runs on its built-in mock |
| Offline resilience, forbidden-field guard, rule proposals from documents, PII-safe logging | **Not built** |

**Verdict:** the backend is functionally complete for the core flow and works end to end against the real Groq and Gemini services. It is **not yet ready to be connected to the app**: the app needs login screens, token handling and the new response contract, and several backend gaps (section 12, items marked High) should be closed first.

---

## 1. Problem Statement & Constraints

Rural customers often don't know which bank/government schemes or loan products they qualify for, and asking a human teller doesn't scale and isn't always available. A voice-first assistant can answer this directly, in the customer's own language — and it must never give a wrong or fabricated eligibility answer, since this is a banking context.

**Hard constraints, and their current status:**

| Constraint | Status |
|---|---|
| Every eligibility decision is deterministic, versioned and auditable — never an LLM guess | **Met.** Only `eligibility_engine` decides; rules are versioned rows in Postgres. |
| Sensitive data (PIN, password, OTP) is never requested or stored by the agent | **Not enforced in code yet.** There is no forbidden-field guard (open issue H2). |
| No dependency on the customer's own device or internet | **Dropped by design.** The product is now a phone app, so the customer's phone and connectivity are required. |
| Must still answer correctly if the connection drops (offline-first) | **Not met / needs re-scoping.** The backend is cloud-only; on the phone only text-to-speech works offline. See section 13. |

**Decision recorded:** moving from a kiosk to a mobile app changes the identity model. A kiosk could trust card-reader hardware; a phone cannot. The customer now registers with phone-or-email + password and receives JWTs. (`connect.md` section 11 notes the same.)

---

## 2. Core Architectural Principles

1. **A thin coordinator over two fixed agents.** *(Changed from "Supervisor + MCP workers".)* `Sahayak_AI` routes a message to the **eligibility agent** and/or the **RAG agent** through one fixed function each, and never reaches into their internals. Neither agent imports the other.
2. **The deterministic engine is the only component that decides eligibility.** *(Unchanged, and now stricter.)* The reply sentence is built from the engine result by code. The LLM extracts facts and, for non-English, translates — it never produces the verdict.
3. **Single writer.** *(Unchanged.)* Only the supervisor pipeline writes the session context; only `db_manager` writes profiles and facts.
4. **Two separate stores.** *(Unchanged.)* Redis for per-conversation context, ownership and tokens; Postgres for profiles, facts, rules, users and documents.
5. **Grounded answers only.** *(New.)* The RAG agent answers only from retrieved passages; if nothing is similar enough it says it could not find the answer rather than guess.
6. **Offline-first, cloud-enhanced.** *(Not achieved — see section 1 and 13.)*

**What changed from the original plan, and why**

| Original plan | As built | Reason |
|---|---|---|
| Branch kiosk | Mobile app | Project scope; the app was built first |
| LangGraph state machine | Plain async pipeline in `supervisor/agent.py` | Simpler; LangGraph was never needed |
| MCP tool calls from workers | MCP server still exists, but the live pipeline calls the engine directly | The worker round-trip cost 2 LLM calls per scheme and its output was discarded |
| Anthropic + fallback LLM | Groq (`gpt-oss-120b` main, `gpt-oss-20b` fast) via DSPy | Free tier; changed at the user's request |
| Loan/Scheme worker agents narrate results | Reply text is templated from the engine result | Guarantees the verdict; removed LLM latency |
| Bhashini/Whisper STT in a backend voice layer | Groq Whisper, proxied by the backend; TTS on the phone (`expo-speech`) | Matches `mobile_voice_client_plan.md` |
| Staff upload + LLM rule proposals + human approval | Staff upload / folder sync feeds **RAG only**; rules are still hand-coded | Rule proposals (Phase 8) not built yet |

---

## 3. System Architecture Overview (as built)

```
 Expo app (voice in/out)                       Branch staff / admin
   │  record → /api/v1/transcribe (STT)          │  PDFs in backend/documents/<scheme_id>/
   │  HTTPS + JWT                                │  python -m rag.folder_sync  (or admin API)
   ▼                                             ▼
 FastAPI backend ───────────────────────────────────────────────────────────────
   /auth/*   /api/v1/me/*   /api/v1/sessions[/{id}/messages]   /api/v1/transcribe
   /api/v1/admin/documents*        (X-Admin-Key)
        │
        ▼
 Sahayak_AI  (sahayak_ai/)
   router (fast LLM)  →  orchestrator  →  refiner
        │                    │
        │      ┌─────────────┴──────────────┐
        ▼      ▼                            ▼
   Eligibility agent                    RAG agent
   (eligibility_agent/ →                (rag/agent.py)
    supervisor/agent.py)                 embed question (Gemini)
    1. extract facts (main LLM)          → pgvector search (loan_chunks / scheme_chunks)
       ∥ resolve target scheme           → main LLM answers ONLY from passages
    2. save facts per customer           → {answer | None, sources, confidence}
    3. deterministic rules engine
    4. templated, friendly reply
        │                                    │
        ▼                                    ▼
   Postgres: customers, customer_profiles,   Postgres + pgvector:
   field history (facts), eligibility_rules  documents, loan_chunks, scheme_chunks
   Redis: session owner, session context, refresh tokens, login rate limit
```

**One chat turn, step by step** (`POST /api/v1/sessions/{id}/messages`)

1. JWT checked; `customer_id` comes only from the token; the session must belong to that customer (else 403).
2. **Router** (fast LLM): splits the message into 1–3 ordered sub-tasks, each `eligibility` or `rag`, each a **standalone** question naming its subject. It also decides `has_question` (asks vs. merely states a fact) and `scheme_id` (resolving "this loan" from the session's active scheme; left empty for "which loans…"). On any failure a keyword heuristic is used — a voice user never sees an error.
3. **Orchestrator** runs the sub-tasks concurrently (at most one eligibility sub-task, because it is the single writer of session context). A crashed agent becomes a safe fallback reply.
4. **Eligibility agent** (runs on its own thread so it never blocks the server): extracts facts against the union of every scheme's required fields, saves new facts to Postgres, then either checks the named / enumerated scheme(s) with the engine, or — if the message was only a fact — re-checks schemes discussed earlier that were still missing information.
5. **RAG agent**: answers document questions with sources (document + page).
6. **Refiner**: English replies get a deterministic cleanup only (no LLM): "Rs 25,000" → "25,000 rupees", markdown stripped, raw ids replaced by friendly names. Non-English replies are translated by the fast LLM, with a guard that every number survives.
7. Response: `reply_text` (spoken), `display_text` (on screen, with sources), `results[]`, `facts_updated[]`, `sources[]`, `turn_type`, plus `eligible` / `missing_fields` for the app's existing fields.

Typical cost after optimisation: **2 LLM calls per eligibility turn, 2 per document question** (was 5–7 and 3).

---

## 4. Component Reference (as built)

### 4.1 Mobile app (`sahayak-mobile/`) — partially built
Expo SDK app with expo-router, Zustand and axios. Working: microphone recording with silence detection (`expo-audio`), speech-to-text (currently **directly against Groq with a key inside the app bundle**), chat transcript, text-to-speech with `expo-speech` and voice-availability notices, retry on failure, a Settings screen, and a **mock backend** (`EXPO_PUBLIC_USE_MOCK_API=true`, the default). Missing: login/register, token storage, the new API contract, profile screens (see section 13).

### 4.2 API & auth (`security/`, `main.py`)
- `POST /auth/register`, `/auth/login`, `/auth/refresh` → `{access_token, refresh_token, customer_id, profile_completed}`.
- JWT HS256; access token 30 min, refresh token 30 days; tokens carry a `type` claim so a refresh token cannot be used as an access token. Only the **latest** refresh token per customer is valid (rotation, kept in Redis).
- Passwords: stdlib **scrypt**, salted, cost parameters stored in the hash so they can be raised later.
- Login/registration attempts rate-limited per `login_id` (5 per 60 s, Redis).
- Server-issued sessions: `POST /api/v1/sessions` stores `session_owner:{id}` in Redis for 24 h; a message to someone else's (or an expired) session returns 403.
- Admin routes need `X-Admin-Key` (constant-time compare); with no key configured they return 403, so a forgotten variable cannot leave uploads open.
- Errors use one shape: `{"error": {"code", "message"}, "detail"}`.
- Debug routes that take `customer_id` from the body (`/profiles/*`, `/session-context/*`, `/api/v1/query`) exist only when `ENABLE_DEBUG_ROUTES=true` (default off; required by the older tests). **Must stay off in any deployment.**

### 4.3 Sahayak_AI (`sahayak_ai/`)
`router.py` (one DSPy call, fast model, keyword fallback), `orchestrator.py`, `refiner.py`, `models.py`. It holds no business logic. Friendly naming lives in `workers/friendly.py` (scheme and requirement names; unknown ids degrade to readable text).

### 4.4 Eligibility agent (`eligibility_agent/`, `supervisor/agent.py`)
Wraps `run_query_pipeline`. Per turn: fact extraction (against all required fields) → persist facts → classify turn (question / fact) → resolve target scheme(s) only when not already pinned → engine check → templated reply. A message that is only a fact re-checks earlier-discussed unresolved schemes using facts known **before** the turn, so the scheme the fact just resolved is still reported. Stated facts are saved even when the question can't be routed.

### 4.5 Deterministic rules engine (`eligibility_engine/`)
Condition trees (AND/OR) over fields, three-valued logic so "unknown" never becomes "eligible". Versioned, append-only rows in `eligibility_rules`. Output: `eligible`, `satisfied[]`, `missing[]`, `completion_fraction`, `confidence`, `rule_source`, `rule_updated_at`. A stored value of the wrong type is treated as "unknown" instead of crashing.
**Nine schemes encoded:** `sukanya_samriddhi`, `pm_jan_dhan_yojana`, `pmay_rural_housing_subsidy`, `kisan_credit_card`, `retail_micro_loan`, `senior_citizen_savings_scheme`, `pm_mudra_yojana_shishu`, `home_loan`, `atal_pension_yojana`.
`confidence` is a placeholder (1.0). Per-scheme partial-eligibility thresholds exist in `eligibility_engine/threshold.py` but **the "you'd qualify if…" message is not yet used in replies**.

### 4.6 Profile store & facts (`db_manager/`, `schemas/`)
`customer_profiles` holds six core fields; every other fact (e.g. `has_girl_child_under_10`, `land_holding_acres`) lives in `customer_profile_field_history` as an append-only value history, so facts persist across sessions and nothing is overwritten. The same store is written by the chat (source `conversation`) and by the profile form (`user_form`). `GET /api/v1/profile/schema` drives the form, so a field a new scheme needs appears in the app without an app release. `PATCH /api/v1/me/profile` validates every value by type and range (numbers, whole-number age 0–120, booleans, select options, text length) and rejects bad values with 422.

### 4.7 Session context (`supervisor/context_store.py`)
Redis list per session: summary, fields collected, schemes discussed, `active_scheme_id`. Read-only for everything except the supervisor.

### 4.8 RAG (`rag/`)
- **Retrieval:** Gemini `gemini-embedding-001` (768 dimensions, multilingual) → cosine search in `loan_chunks` / `scheme_chunks` (two physical tables = two vector spaces) → top 5, minimum similarity 0.45. When a scheme is active the search covers chunks tagged for that scheme **plus untagged chunks**.
- **Answering:** main LLM, only from the numbered passages, in complete sentences; empty answer → "not found". Returns sources (document + page) and confidence.
- **Ingestion:** `pypdf` text per page → classify loan/scheme (fast LLM, confidence ≥ 0.7 else `needs_review`) → heading-aware chunking (≈2400 chars, 400 overlap) → embed → store. Statuses: `processing → active | needs_review | needs_ocr | embedding_failed`.
- **Folder sync:** put PDFs in `backend/documents/<scheme_id>/…` (top-level files have no scheme) and run `python -m rag.folder_sync`, or `POST /api/v1/admin/documents/sync`. Files are recognised by content hash, so re-running never duplicates; a file moved into a scheme folder is re-tagged without re-embedding; failed embeddings are retried. Unknown folder names and non-PDF content are reported, not ingested.
- **Verified** with one real PDF (Sukanya Samriddhi factsheet): correct answers with page citations for documents required, yearly deposit limit, minimum deposit, maturity; "not found" for out-of-scope questions; Hindi questions answered in Hindi.

### 4.9 Speech (`speech/api.py`)
`POST /api/v1/transcribe` forwards audio to Groq Whisper (`whisper-large-v3`) with the server-side key, drops segments Whisper itself flags as silence, and maps the detected language to BCP-47. Text-to-speech stays on the phone.

### 4.10 Security layer
Done: JWT with typed tokens, scrypt, rate-limited login, session ownership, admin key, PII-free error shape, debug routes off by default, secrets kept in a git-ignored `.env`.
Not done: forbidden-field guard (PIN/OTP/CVV/password), PII-redacted logging, corroboration of self-reported facts against bank records (section 12).

### 4.11 Offline layer (`offline/`)
Empty package. Not built (section 13).

---

## 5. Data Model

Migrations (`backend/database/migrations`, applied by `python -m database.migrate`, idempotent):

| # | Adds |
|---|---|
| 0001 | `customer_profiles` |
| 0002 | `customer_profile_field_history` (versioned values + extra facts) |
| 0003 | `eligibility_rules` (append-only per version) |
| 0004 | `customers` (auth identity; `customer_id` = JWT `sub`) |
| 0005 | `documents`, `loan_chunks`, `scheme_chunks` (pgvector, `vector(768)`, HNSW indexes) |
| 0006 | `documents.content_hash` (folder-sync de-duplication) |

Redis keys: `session_owner:{id}`, `session_context:{id}`, `refresh_token:{customer_id}`, `login_attempts:{login_id}`.

Seed rules and demo data: `python -m scripts.seed_sample_data` (also creates demo customers `cust-001…`; **skip the demo profiles in a real deployment**).

---

## 6. API Contract

All routes except `/auth/*`, `/health` need `Authorization: Bearer <access_token>`.

| Method + path | Purpose |
|---|---|
| `GET /health`, `GET /api/v1/health` | Public liveness |
| `GET /health/deps` | Postgres/Redis status (admin key) |
| `POST /auth/register` · `/auth/login` · `/auth/refresh` | Tokens |
| `GET /api/v1/profile/schema` | Field list for the profile form |
| `GET` / `PATCH /api/v1/me/profile` | View / partially update profile (validated) |
| `POST /api/v1/sessions` | New server-owned session |
| `POST /api/v1/sessions/{id}/messages` | `{text, language}` → `{reply_text, display_text, language, results[], facts_updated[], sources[], turn_type, eligible, missing_fields}` |
| `POST /api/v1/transcribe` | Multipart audio → `{text, language}` |
| `POST /api/v1/admin/documents` | Upload one PDF (+ optional `scheme_id`) |
| `POST /api/v1/admin/documents/sync` | Ingest everything in `backend/documents/` |
| `GET /api/v1/admin/documents` | List documents and statuses |
| `POST /api/v1/admin/documents/{id}/review` | Human decision for `needs_review`, or retry a failed embed |

`results[]` and `missing_fields` carry **raw ids** (stable keys). Text meant for people (`reply_text`, `display_text`) uses friendly names.

---

## 7. Technology Stack (actual)

| Layer | Choice |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic |
| LLM | Groq via DSPy: `openai/gpt-oss-120b` (extraction, target resolution, RAG answers), `openai/gpt-oss-20b` (routing, document classification, translation), `reasoning_effort=low` |
| Embeddings | Google Gemini `gemini-embedding-001`, 768-d |
| Speech | Groq Whisper (STT, via backend); `expo-speech` (TTS, on device) |
| Data | PostgreSQL 16 + pgvector; Redis 7 |
| Auth | JWT (PyJWT), scrypt |
| PDF | `pypdf` (text PDFs only) |
| Mobile | Expo / React Native, expo-router, Zustand, axios |
| Packaging | Dockerfile + `docker-compose.yml` (`pgvector/pgvector:pg16`, `redis:7-alpine`, app) |

---

## 8. Repository Structure (actual)

```
backend/
  main.py                    app, routers, error shape, health
  settings.py                all configuration (env-driven)
  sahayak_ai/                router, orchestrator, refiner, models, api (chat routes)
  eligibility_agent/         fixed interface over the supervisor pipeline
  supervisor/                run_query_pipeline, context store, debug routes
  eligibility_engine/        rules, evaluator, threshold, calculators, seed
  workers/                   Loan/Scheme agent classes, friendly names, narration guard
  mcp_servers/               MCP wrappers (engine, calculators, DB) — not on the live path
  rag/                       agent, ingestion, folder_sync, chunking, embeddings, repository, api
  security/                  auth, passwords, sessions, rate_limit, admin, repository
  db_manager/                profile repository, profile API (me_api), debug API
  speech/                    transcribe proxy
  schemas/                   models, required-fields registry, profile form schema
  database/                  connection, migrations
  documents/                 drop PDFs here (sub-folder = scheme_id)
  document_ingestion/, offline/   empty placeholders
  tests/                     109 tests
sahayak-mobile/              Expo app
docs/                        this file, mobile_voice_client_plan.md
connect.md                   frontend ↔ backend connection plan
```

---

## 9. Phase-by-Phase Status

| Phase | Original goal | Status |
|---|---|---|
| 0 Setup | Repo, Docker Compose | **Done** |
| 1 Data layer | Profile/rules/context stores, JWT scaffold | **Done**, JWT now real login |
| 2 Rules engine | Deterministic engine, 5–10 schemes, threshold | **Done** (9 schemes); threshold not surfaced in replies |
| 3 MCP tool layer | Engine/calculators as MCP tools | **Done**, but not on the live path |
| 4 Worker agents | LLM extraction + narration | **Done, then simplified** — narration replaced by templated reply |
| 5 Supervisor + context | Conversation flow, no re-asking | **Done** (plain pipeline, not LangGraph) |
| 6 DB manager + required fields | Registry, versioned upsert, asks only for missing | **Done** |
| 7 RAG | Vector KB, cited answers | **Done**, verified with a real PDF |
| 8 Document ingestion + rule proposals | Upload → classify → embed + draft rules → human review | **Partial** — upload, classify, embed, review of document type done; **rule proposals not built** |
| 9 Voice layer | LangID → STT → … → TTS | **Partial** — STT proxy done, TTS on phone; app not yet using the proxy; no Bhashini/local fallback |
| 10 Offline-first | Local cache, local STT/TTS, sync queue | **Not started** |
| 11 Security hardening | Forbidden fields, PII redaction, corroboration | **Partial** — auth/session isolation done; the rest not started |
| 12 Reasoning & benefits polish | Narration quality, partial-eligibility message | **Partial** — friendly wording done; benefits and "you'd qualify if…" not done |
| 13 Kiosk UX / printed summary | Take-home slip, teller handoff | **Not started** (kiosk-specific; re-scope for mobile) |
| 14 Testing & demo prep | Regression suite, demo script | **Partial** — suite exists; no offline test, no demo script, no CI |
| *New* — Mobile client | App per `mobile_voice_client_plan.md` | **Phases A–E done against a mock; Phase F (real backend) not done** |
| *New* — Cloud deployment | Neon/Upstash/Render per `connect.md` | **Not started** |

---

## 10. Testing

- **109 tests pass.** Coverage: rules engine and threshold, MCP tools, profile versioning, session context, auth (register/login/refresh, typed tokens, rate limit, session ownership, admin key), router/refiner/chunking/password units, friendly wording, profile-value validation, engine type-safety, non-blocking eligibility agent, RAG scheme filter, folder sync, and end-to-end query-pipeline regressions.
- **Caveat:** the query-pipeline and worker tests call the **real Groq API** (needs `GROQ_API_KEY`, network, and consumes the free-tier quota). They can be slow or flaky under rate limiting, and running the suite right before a live chat can throttle the chat.
- RAG verification was done by hand with one PDF (not an automated test).
- Not tested: Hindi verdict correctness, load/concurrency beyond a single event-loop check, the mobile app against the real backend, deployment.

## 11. Performance & Rate Limits (measured)

| | Before optimisation | After |
|---|---|---|
| LLM calls (4 representative turns) | 18 | 9 |
| Tokens (same turns) | ≈14,800 | ≈9,100 |
| Time per turn | 4–22 s | 1.3–2.5 s (1.2–4.8 s live over HTTP) |
| Test suite time | 55–80 s | 12–18 s |

What produced it: removed the worker round-trip whose output was discarded; merged two classifiers into one; let the router decide question-vs-fact; ran independent calls concurrently; used a smaller model for routing/translation; English replies need no LLM rewrite; eligibility runs off the event loop (`/health` answered in 19 ms during a chat turn).

**The binding constraint is Groq's free tier: 8,000 tokens per minute per model** (checked from response headers). Bursts of chat plus the test suite exhaust it and each call then waits for the minute to reset (seen as 14–31 s turns). Splitting work across two models roughly doubles the headroom; a paid/dev-tier key removes the limit.

---

## 12. Known Issues

### Fixed during this work
| Issue | Fix |
|---|---|
| Eligibility pipeline blocked the whole server during LLM/DB calls | Runs on its own thread; verified `/health` stays fast |
| A wrongly-typed stored value (e.g. age "abc") crashed every later check with a 500 | Profile values validated on save (422); engine treats uncomparable values as unknown |
| Raw ids on screen (`retail_micro_loan`, `employment_type_requirement`) | Friendly names in all text; classifier error messages rewritten |
| RAG found nothing for documents uploaded without a scheme once a scheme was active | Search includes untagged chunks; upload warns when `scheme_id` is missing |
| "Which loans am I eligible for?" only checked the loan discussed last | Router no longer pins "all" questions to the active scheme |
| Document questions mis-routed to eligibility; fragments like "why only till then?" sent without context | Router prompt: standalone sub-questions, document questions → RAG |
| Refiner turned "21 years" into "Your age is 21 years" and once promised "I will ask a bank officer" | RAG answers in full sentences; refiner forbidden from guessing referents or promising actions; English replies skip the refiner LLM |
| 5–7 LLM calls per turn, 2 of them wasted | See section 11 |
| Failures swallowed silently (RAG, router, refiner, orchestrator) | Warnings logged with tracebacks |
| Folder of PDFs needed by hand-upload | `documents/` folder + sync (CLI and API) |

### Open — High
| ID | Issue | Impact / suggested fix |
|---|---|---|
| H1 | **Non-English replies skip the verdict check.** The refiner verifies the eligible/not-eligible phrase only for English; for Hindi etc. only numbers are checked | A translation could flip "not eligible". Fix: translate **templated** sentences per language instead of using the LLM, or check the verdict in each language |
| H2 | **No forbidden-field guard** (PIN, OTP, CVV, password) | Violates a hard constraint; a customer could state an OTP and it could be extracted and stored. Fix: reject at extraction and at the profile API |
| H3 | **Groq free-tier throttling** (8,000 tokens/min/model) | Latency spikes under load. Fix: dev-tier key; retries with backoff; per-user rate limits |
| H4 | **RAG says "not found" on any LLM/embedding failure**, including rate limits | Misleading to users. Fix: distinguish "not in documents" from "temporarily unavailable"; retry on 429 |
| H5 | **Embedding calls have no retry/backoff and one provider (Gemini)** | A large upload can end `embedding_failed` on a rate limit. Fix: throttle + retry; provider switch (e.g. Jina) |
| H6 | **Nothing runs migrations or seeds the rules on start-up** | A fresh cloud database has no rules, so every eligibility check fails. Fix: run both on boot or in the release command |
| H7 | **Not deployed**; app not connected | See section 13 |

### Open — Medium
| ID | Issue |
|---|---|
| M1 | Open registration and no rate limit on `/messages` or `/transcribe`: anyone can create accounts and drain the Groq quota |
| M2 | Login rate limit is keyed on `login_id` only, so anyone can lock a user out by spamming their number; no per-IP limit |
| M3 | Only the latest refresh token per customer is valid (logging in on a second phone signs out the first); two simultaneous refreshes make the second fail — the app must serialise refreshes |
| M4 | No logout/revoke endpoint, password reset, or account deletion; phone/email not validated or normalised (`+91 99999…` and `99999…` become two accounts) |
| M5 | Session ownership expires after 24 h (→ 403, the app must start a new session) but `session_context:*` has no TTL and grows forever |
| M6 | Voice UX: multi-scheme answers read as long paragraphs; the refiner can add extras ("Do you want to ask another question?"); "Not met yet" mixes unmet requirements with unknown ones |
| M7 | Partial-eligibility ("you'd qualify if…") not used in replies; engine `confidence` is a placeholder 1.0; no benefits/explanations beyond the document answers |
| M8 | Field prompts and eligibility sentences are English; other languages rely on LLM translation |
| M9 | Self-reported facts are trusted as given (no corroboration with bank records) |
| M10 | Rules are hand-coded; PDFs feed RAG only, so a document and a rule can disagree. Rule proposals + human approval (Phase 8) not built |
| M11 | No OCR: scanned PDFs end `needs_ocr` and are skipped |
| M12 | No automated tests run without live Groq; no CI |
| M13 | Logging is minimal; no PII redaction, no metrics |

### Open — Low
- Chunk overlap can start mid-word (`ent from time to time…`); retrieval still works.
- The source line can repeat the same file for two pages.
- A changed PDF is ingested as a new document and the old one stays searchable; there is no delete or replace-in-place endpoint.
- `results[]` exposes raw ids only; the app would need friendly-name fields to show them.
- `document_ingestion/` and `offline/` are empty placeholders.

---

## 13. What Still Needs To Be Done (recommended order)

**R1 — Make the backend safe to connect** (small, mostly independent)
1. Verdict-safe translation for non-English replies (H1).
2. Forbidden-field guard (H2).
3. RAG: separate "not found" from "unavailable", retry on rate limits (H4); embedding retry + provider switch (H5).
4. Run migrations and seed rules automatically on start (H6).
5. Rate limits on chat/transcribe and per-IP on auth (M1, M2).

**R2 — Deploy**
Neon (or Supabase) Postgres with pgvector, Upstash Redis, a container host with HTTPS (Render / Cloud Run), env vars from `connect.md` section 4.1, `ENABLE_DEBUG_ROUTES=false`, the `documents/` folder baked into the image or synced through the admin endpoint. Tolerate cold starts (60 s timeout, "waking up" message).

**R3 — Connect the mobile app** (`connect.md` section 3.4–8)
- Dependencies/files: `expo-secure-store`, token store, auth store, login/register screens, route guard (`Stack.Protected`), onboarding + profile screens driven by `/profile/schema`.
- `api.ts`: new paths and types, bearer interceptor, single-flight 401 → refresh → retry, 60 s timeout, health ping on launch, new session on 403.
- `stt.ts`: call `/api/v1/transcribe` and remove `EXPO_PUBLIC_GROQ_API_KEY` from the app.
- Show `display_text` on screen and speak `reply_text`; clear chat and session on logout.
- Update the mock so demos still work offline; set `EXPO_PUBLIC_USE_MOCK_API=false` and the real URL.
- Test on real devices (Android and iOS TTS voices differ).

**R4 — Product polish**
Shorter spoken summaries for multi-scheme answers; partial-eligibility message with disclaimer; benefits explanations from documents; per-language templates for the fixed sentences; friendly-name fields in `results[]`.

**R5 — Rules from documents (Phase 8)**
LLM-drafted rule proposals stored **inactive**, a review queue, and approval before activation; keep `documents.scheme_id` aligned with `eligibility_rules.scheme_id`; OCR for scanned PDFs; delete/replace for documents.

**R6 — Hardening and operations**
PII-redacted structured logging and basic metrics; session-context TTL; refresh-token handling for multiple devices, logout/revoke, password reset (OTP provider), account deletion; fact corroboration; CI with a recorded or fake LLM so tests don't use live quota; load test.

**R7 — Resilience, re-scoped for a phone**
Decide what "offline" means now: the phone can still speak and show cached text, but eligibility needs the server. Options: a small bundled copy of the rules for an on-device check, a retry queue, and clear offline messaging. The kiosk-specific items (printed slip, teller hand-off) are optional.

---

## 14. Running It Locally

```
cd backend
docker compose up -d postgres redis          # pgvector/pgvector:pg16 + redis:7
python -m database.migrate                   # migrations 0001–0006
python -m scripts.seed_sample_data           # rules (+ demo profiles)
python -m uvicorn main:app --port 8000
python -m rag.folder_sync                    # ingest PDFs from backend/documents/
python -m pytest -q                          # 109 tests (some call real Groq)
```
`backend/.env` (git-ignored; template in `.env.example`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL`, `REDIS_URL` | Postgres / Redis (cloud: Neon pooled URL, Upstash `rediss://`) |
| `JWT_SECRET` | **Required**; `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GROQ_API_KEY` | LLM + speech-to-text |
| `EMBEDDING_API_KEY` | Gemini key for RAG |
| `ADMIN_API_KEY` | Enables `/api/v1/admin/*` and `/health/deps` |
| `ENABLE_DEBUG_ROUTES` | `true` only for local development and the legacy tests |
| `WORKER_LLM_MODEL`, `FAST_LLM_MODEL`, `LLM_REASONING_EFFORT` | Model choices (defaults in `settings.py`) |
| `RAG_DOCUMENTS_DIR` | Folder read by the sync (default `documents`) |

Quick end-to-end check with `curl`: see `connect.md` section 10.

---

## 15. Risks

| Risk | Mitigation / status |
|---|---|
| Free-tier LLM and embedding limits stall the demo | Fewer calls per turn (done); dev-tier key; retries (R1); keep a rehearsed script |
| A translated reply states the wrong verdict | Open (H1) — fix before demoing in Hindi to real users |
| Wrong answers from documents | RAG refuses below similarity 0.45 and answers only from retrieved text; spot-check each new PDF |
| Rule encoding for real schemes is slow and error-prone | Rules are hand-coded and versioned; Phase 8 review flow would help |
| Secrets in the app bundle | Fixed on the backend (`/transcribe`); the app still ships the Groq key until R3 |
| Scope creep (A2A, marketplace, kiosk hardware) | This file is the reference; deviations are recorded in section 2 |
