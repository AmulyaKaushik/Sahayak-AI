# Sahayak AI — Architecture, Implementation Status & Roadmap

Multilingual, voice-first assistant that tells customers which bank loans and government schemes they qualify for, and answers questions about what the official documents say. Originally designed as a branch kiosk; **now delivered as a mobile app (Expo / React Native) talking to a cloud-hostable FastAPI backend.**

*Last updated: 2026-11-16. This document started as the frozen design; it now records the design **as built**, what changed from the original plan and why, the known issues, and what is still to do. Sections 9, 12 and 13 are the quickest way to see where the project stands.*

---

## 0. Where the project stands (summary)

| Area | Status |
|---|---|
| Deterministic eligibility engine (9 hand-coded schemes) | **Done, tested** |
| Profile store with versioned history + cross-session facts | **Done, tested** |
| Auth (register / login / refresh, JWT), server-owned sessions | **Done, tested** |
| Sahayak_AI layer (router → agents → refiner) | **Done, tested live** |
| Eligibility agent (fact extraction → rules → reply) | **Done, tested live** |
| RAG agent + PDF ingestion + folder sync (Gemini embeddings, pgvector, keyword-search fallback) | **Done; all 10 PDFs ingested and spot-checked** |
| Speech-to-text proxy (Groq Whisper behind the backend) | **Done** (not yet used by the app; not tested with real audio on Render) |
| Groq key rotation (round-robin over several keys) | **Done** |
| LLM-free fallback for eligibility (regex facts, keyword routing, cached rules) | **Done, tested** |
| Forbidden-field guard (PIN / OTP / CVV / password / card number) in chat | **Done** |
| Short spoken replies (refiner summaries) | **Done** |
| Terminal chat (`python main.py`) | **Done** |
| Backend test suite | **126 passing** (about 12–25 s; some tests call live Groq) |
| Cloud deployment (demo) | **Deployed on Render** (Docker) with Supabase Postgres + Upstash Redis; register, login, chat, RAG, Hindi, profile and security checks verified over HTTPS. Replies take 6–11 s there (section 11) |
| Mobile app ↔ backend connection | **Not done** — app still runs on its built-in mock |
| On-device offline mode, rule proposals from documents, PII-safe logging, connection pooling | **Not built** |

**Verdict:** the backend is functionally complete for the core flow, is deployed for a demo, and works end to end against the real Groq and Gemini services. The one big missing piece is the **mobile app connection**: the app still needs login screens, token handling and the new response contract (section 13, R3). The remaining High issues are H1 (non-English verdict check) and H3 (Groq free-tier limits).

---

## 1. Problem Statement & Constraints

Rural customers often don't know which bank/government schemes or loan products they qualify for, and asking a human teller doesn't scale and isn't always available. A voice-first assistant can answer this directly, in the customer's own language — and it must never give a wrong or fabricated eligibility answer, since this is a banking context.

**Hard constraints, and their current status:**

| Constraint | Status |
|---|---|
| Every eligibility decision is deterministic, versioned and auditable — never an LLM guess | **Met.** Only `eligibility_engine` decides; rules are versioned rows in Postgres. |
| Sensitive data (PIN, password, OTP) is never requested or stored by the agent | **Met for chat.** A message containing a PIN, OTP, CVV, password or card number is refused before any model sees it and nothing is stored (`sahayak_ai/orchestrator.py`). The profile API only accepts known profile fields. |
| No dependency on the customer's own device or internet | **Dropped by design.** The product is now a phone app, so the customer's phone and connectivity are required. |
| Must still answer correctly if the connection drops (offline-first) | **Partly met.** The backend still needs the internet, but eligibility checks keep working when the *LLM* is unreachable (regex facts + keyword routing + cached rules, section 4.11). Document answers still need the LLM. On the phone only text-to-speech works offline. |

**Decision recorded:** moving from a kiosk to a mobile app changes the identity model. A kiosk could trust card-reader hardware; a phone cannot. The customer now registers with phone-or-email + password and receives JWTs. (`connect.md` section 11 notes the same.)

---

## 2. Core Architectural Principles

1. **A thin coordinator over two fixed agents.** *(Changed from "Supervisor + MCP workers".)* `Sahayak_AI` routes a message to the **eligibility agent** and/or the **RAG agent** through one fixed function each, and never reaches into their internals. Neither agent imports the other.
2. **The deterministic engine is the only component that decides eligibility.** *(Unchanged, and now stricter.)* The reply sentence is built from the engine result by code. The LLM extracts facts and, for non-English, translates — it never produces the verdict.
3. **Single writer.** *(Unchanged.)* Only the supervisor pipeline writes the session context; only `db_manager` writes profiles and facts.
4. **Two separate stores.** *(Unchanged.)* Redis for per-conversation context, ownership and tokens; Postgres for profiles, facts, rules, users and documents.
5. **Grounded answers only.** *(New.)* The RAG agent answers only from retrieved passages; if nothing is similar enough it says it could not find the answer rather than guess.
6. **Degrade, don't fail.** *(Partly achieved.)* If the LLM is down, eligibility still answers from regex-extracted facts, keyword routing and cached rules; if the embedding service is down, documents are searched by keyword; a lookup failure is reported as "trouble looking that up", never as "not found". True on-device offline mode is not built.

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
    supervisor/agent.py)                 embed question (Gemini; keyword search if unavailable)
    1. extract facts (main LLM + regex)  → pgvector search (loan_chunks / scheme_chunks)
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

1. JWT checked; `customer_id` comes only from the token; the session must belong to that customer (else 403). A message containing a PIN/OTP/password/card number is refused here, before any model sees it.
2. **Router** (fast LLM): splits the message into 1–3 ordered sub-tasks, each `eligibility` or `rag`, each a **standalone** question naming its subject. It also decides `has_question` (asks vs. merely states a fact) and `scheme_id` (resolving "this loan" from the session's active scheme; left empty for "which loans…"). On any failure a keyword heuristic is used — a voice user never sees an error.
3. **Orchestrator** runs the sub-tasks concurrently (at most one eligibility sub-task, because it is the single writer of session context). A crashed agent becomes a safe fallback reply.
4. **Eligibility agent** (runs on its own thread so it never blocks the server): extracts facts from the customer's **original** message (not the router's shortened question, which used to drop facts) against the union of every scheme's required fields, with regex facts merged underneath the LLM's, saves new facts to Postgres, then either checks the named / enumerated scheme(s) with the engine, or — if the message was only a fact — re-checks schemes discussed earlier that were still missing information.
5. **RAG agent**: answers document questions with sources (document + page).
6. **Refiner**: English replies get a deterministic cleanup only (no LLM): "Rs 25,000" → "25,000 rupees", markdown stripped, raw ids replaced by friendly names. Multi-scheme answers and plain facts are **summarised**: who you are eligible for, up to two closest schemes and what they still need, how many others are not yet eligible, and **one** thing to ask next. The full per-scheme detail stays in `results[]`. Non-English replies are translated by the fast LLM, with a guard that every number survives.
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
`router.py` (one DSPy call, fast model, keyword fallback), `orchestrator.py` (also the secret-message guard), `refiner.py` (cleanup, translation, `summarize_eligibility`), `models.py`. It holds no business logic. Friendly naming lives in `workers/friendly.py` (scheme and requirement names; unknown ids degrade to readable text).

### 4.4 Eligibility agent (`eligibility_agent/`, `supervisor/agent.py`)
Wraps `run_query_pipeline` (takes `facts_text`, the customer's original message, for fact extraction). Per turn: fact extraction (against all required fields) → persist facts → classify turn (question / fact) → resolve target scheme(s) only when not already pinned → engine check → templated reply. A message that is only a fact re-checks earlier-discussed unresolved schemes using facts known **before** the turn, so the scheme the fact just resolved is still reported. Stated facts are saved even when the question can't be routed. `supervisor/offline.py` provides `extract_facts_regex` (age, monthly income incl. "40k" / "6 lakh per year", dependents, land, employment type, yes/no facts; a new amount replaces the saved one) and `keyword_target_scheme_ids` (which loans/schemes a question names). Regex facts are always merged under the LLM's, and are used alone when the LLM fails. Each result also carries `ask[]`, the fields still needed.

### 4.5 Deterministic rules engine (`eligibility_engine/`)
Condition trees (AND/OR) over fields, three-valued logic so "unknown" never becomes "eligible". Versioned, append-only rows in `eligibility_rules`. Output: `eligible`, `satisfied[]`, `missing[]`, `completion_fraction`, `confidence`, `rule_source`, `rule_updated_at`. A stored value of the wrong type is treated as "unknown" instead of crashing. Active rules are cached in memory for 5 minutes, and a cached rule is used if the database cannot be reached.
**Nine schemes encoded:** `sukanya_samriddhi`, `pm_jan_dhan_yojana`, `pmay_rural_housing_subsidy`, `kisan_credit_card`, `retail_micro_loan`, `senior_citizen_savings_scheme`, `pm_mudra_yojana_shishu`, `home_loan`, `atal_pension_yojana`.
`confidence` is a placeholder (1.0). Per-scheme partial-eligibility thresholds exist in `eligibility_engine/threshold.py` but **the "you'd qualify if…" message is not yet used in replies**.

### 4.6 Profile store & facts (`db_manager/`, `schemas/`)
`customer_profiles` holds six core fields; every other fact (e.g. `has_girl_child_under_10`, `land_holding_acres`) lives in `customer_profile_field_history` as an append-only value history, so facts persist across sessions and nothing is overwritten. The same store is written by the chat (source `conversation`) and by the profile form (`user_form`). `GET /api/v1/profile/schema` drives the form, so a field a new scheme needs appears in the app without an app release. `PATCH /api/v1/me/profile` validates every value by type and range (numbers, whole-number age 0–120, booleans, select options, text length) and rejects bad values with 422.

### 4.7 Session context (`supervisor/context_store.py`)
Redis list per session: summary, fields collected, schemes discussed, `active_scheme_id`. Read-only for everything except the supervisor.

### 4.8 RAG (`rag/`)
- **Retrieval:** Gemini `gemini-embedding-001` (768 dimensions, multilingual; retried on 429/5xx) → cosine search in `loan_chunks` / `scheme_chunks` (two physical tables = two vector spaces) → top 5, minimum similarity 0.45. When a scheme is active the search covers chunks tagged for that scheme **plus untagged chunks**.
- **Keyword fallback:** if there is no `EMBEDDING_API_KEY` or the embedding call fails, chunks are searched by Postgres full-text search (a scheme named in the question narrows it). Weaker than vectors, and poor for Hindi questions; new PDFs still need embeddings.
- **Answering:** main LLM, only from the numbered passages, in complete sentences. Returns sources (document + page) and confidence. A genuinely empty answer → "not found"; an LLM or database failure → `unavailable=True` → "I am having trouble looking that up right now".
- **Ingestion:** `pypdf` text per page → classify loan/scheme (fast LLM, confidence ≥ 0.7 else `needs_review`) → heading-aware chunking (≈2400 chars, 400 overlap) → embed → store. Statuses: `processing → active | needs_review | needs_ocr | embedding_failed`.
- **Folder sync:** put PDFs in `backend/documents/<scheme_id>/…` (a top-level file takes its scheme from its name, e.g. `home_loan.pdf`; other names have no scheme) and run `python -m rag.folder_sync`, or `POST /api/v1/admin/documents/sync`. Files are recognised by content hash, so re-running never duplicates; a file moved into a scheme folder is re-tagged without re-embedding; failed embeddings are retried. Unknown folder names and non-PDF content are reported, not ingested.
- **Verified** with all 10 PDFs (one per scheme): correct, cited answers for documents required, deposit limits, credit limits, pension amounts, tenures; "not found" for out-of-scope questions; Hindi questions answered in Hindi; also verified on the Render deployment.

### 4.9 Speech (`speech/api.py`)
`POST /api/v1/transcribe` forwards audio to Groq Whisper (`whisper-large-v3`) with a server-side key (taken round-robin from `GROQ_API_KEY` / `GROQ_API_KEYS`, `workers/keys.py`; the LLM calls rotate the same way), drops segments Whisper itself flags as silence, and maps the detected language to BCP-47. Text-to-speech stays on the phone.

### 4.10 Security layer
Done: JWT with typed tokens, scrypt, rate-limited login, session ownership, admin key, PII-free error shape, debug routes off by default, secrets kept in a git-ignored `.env`.
Also done: forbidden-field guard for chat (PIN/OTP/CVV/password/card number). Not done: PII-redacted logging, per-user rate limits on chat/transcribe, corroboration of self-reported facts against bank records (section 12).

### 4.11 Degraded-mode layer
`offline/` is still an empty package (no on-device mode). What exists instead is the server-side fallback described above: cached rules, regex facts and keyword routing for eligibility; keyword search for documents; `unavailable` instead of "not found"; startup that survives a failed setup (`AUTO_SETUP`, `bootstrap.py`: migrate, seed missing rules, sync documents in the background). Remaining limit: if the **database** is unreachable, saved facts can't be read, so a check fails.

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
| Embeddings | Google Gemini `gemini-embedding-001`, 768-d (optional at query time: keyword-search fallback) |
| Speech | Groq Whisper (STT, via backend); `expo-speech` (TTS, on device) |
| Data | PostgreSQL 16 + pgvector; Redis 7 |
| Auth | JWT (PyJWT), scrypt |
| PDF | `pypdf` (text PDFs only) |
| Mobile | Expo / React Native, expo-router, Zustand, axios |
| Packaging | Dockerfile (honours `$PORT`) + `docker-compose.yml` (`pgvector/pgvector:pg16`, `redis:7-alpine`, app) |
| Hosting (demo) | Render (Docker web service, root directory `backend`), Supabase Postgres via the **Session pooler**, Upstash Redis (`rediss://`) |

---

## 8. Repository Structure (actual)

```
backend/
  main.py                    app, routers, error shape, health; `python main.py` = terminal chat
  bootstrap.py               AUTO_SETUP: migrate + seed missing rules + sync documents
  settings.py                all configuration (env-driven)
  sahayak_ai/                router, orchestrator, refiner, models, api (chat routes)
  eligibility_agent/         fixed interface over the supervisor pipeline
  supervisor/                run_query_pipeline, context store, offline.py (regex facts, keyword routing), debug routes
  eligibility_engine/        rules, evaluator, threshold, calculators, seed
  workers/                   Loan/Scheme agent classes, friendly names, narration guard, keys.py (Groq key rotation)
  mcp_servers/               MCP wrappers (engine, calculators, DB) — not on the live path
  rag/                       agent, ingestion, folder_sync, chunking, embeddings, repository, api
  security/                  auth, passwords, sessions, rate_limit, admin, repository
  db_manager/                profile repository, profile API (me_api), debug API
  speech/                    transcribe proxy
  schemas/                   models, required-fields registry, profile form schema
  database/                  connection, migrations
  documents/                 drop PDFs here (sub-folder = scheme_id)
  document_ingestion/, offline/   empty placeholders
  tests/                     126 tests
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
| 11 Security hardening | Forbidden fields, PII redaction, corroboration | **Partial** — auth/session isolation and the chat forbidden-field guard done; PII redaction, rate limits, corroboration not started |
| 12 Reasoning & benefits polish | Narration quality, partial-eligibility message | **Partial** — friendly wording and short summaries done; benefits and "you'd qualify if…" not done |
| 13 Kiosk UX / printed summary | Take-home slip, teller handoff | **Not started** (kiosk-specific; re-scope for mobile) |
| 14 Testing & demo prep | Regression suite, demo script | **Partial** — suite exists; no offline test, no demo script, no CI |
| *New* — Mobile client | App per `mobile_voice_client_plan.md` | **Phases A–E done against a mock; Phase F (real backend) not done** |
| *New* — Cloud deployment | Supabase / Upstash / Render | **Done for a demo** (verified over HTTPS); no pooling, free tier sleeps |

---

## 10. Testing

- **126 tests pass.** Coverage: rules engine and threshold, MCP tools, profile versioning, session context, auth (register/login/refresh, typed tokens, rate limit, session ownership, admin key), router/refiner/chunking/password units, friendly wording, profile-value validation, engine type-safety, non-blocking eligibility agent, RAG scheme filter, folder sync, key rotation, regex facts and keyword routing, the no-LLM eligibility path (a new amount replaces the saved one), cached rules when the DB is down, RAG failure handling (keyword fallback, `unavailable`), short summaries, the secret-message guard, and end-to-end query-pipeline regressions.
- **Caveat:** the query-pipeline and worker tests call the **real Groq API** (needs `GROQ_API_KEY`, network, and consumes the free-tier quota). They can be slow or flaky under rate limiting, and running the suite right before a live chat can throttle the chat.
- RAG verification was done by hand with all 10 PDFs (not an automated test). The Render deployment was checked by hand over HTTPS: health, register, login, wrong password, refresh, missing token, profile schema/get/patch/bad value, sessions, eligibility chat, document chat, Hindi chat, PIN refusal, other user's session (403), transcribe without a file (422), debug and admin routes locked (404/401).
- Not tested: Hindi verdict correctness, load/concurrency beyond a single event-loop check, the mobile app against the real backend, speech-to-text with real audio on Render, the admin document list on Render.

## 11. Performance & Rate Limits (measured)

| | Before optimisation | After |
|---|---|---|
| LLM calls (4 representative turns) | 18 | 9 |
| Tokens (same turns) | ≈14,800 | ≈9,100 |
| Time per turn | 4–22 s | 1.3–2.5 s (1.2–4.8 s live over HTTP) |
| Test suite time | 55–80 s | 12–18 s |

What produced it: removed the worker round-trip whose output was discarded; merged two classifiers into one; let the router decide question-vs-fact; ran independent calls concurrently; used a smaller model for routing/translation; English replies need no LLM rewrite; eligibility runs off the event loop (`/health` answered in 19 ms during a chat turn).

**On Render (measured 2026-11-16):** chat turns took 6–11 s, against 1–3 s locally. Likely causes (not yet confirmed): every database call opens a **new connection** with a TLS handshake to Supabase (a turn makes 10–20 calls), and the Render/Supabase regions may differ. A connection pool (`psycopg_pool`) is the planned fix. The first request after the free tier sleeps took ~42 s.

**The binding constraint is Groq's free tier: 8,000 tokens per minute per model** (checked from response headers). Bursts of chat plus the test suite exhaust it and each call then waits for the minute to reset (seen as 14–31 s turns). Splitting work across two models roughly doubles the headroom, and every extra key in `GROQ_API_KEYS` adds another full allowance (calls rotate round-robin); a paid/dev-tier key removes the limit.

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
| **H2** no forbidden-field guard | Chat messages with a PIN/OTP/CVV/password/card number are refused before any model sees them |
| **H4** RAG said "not found" on any failure | `unavailable` flag → "trouble looking that up"; failures logged |
| **H5** embeddings had no retry and one provider | Retries with back-off; keyword search when embeddings are unavailable |
| **H6** nothing migrated/seeded on start | `AUTO_SETUP=true` runs migrations, seeds missing rules, syncs documents; a failed setup does not stop the server |
| Facts in a question were lost ("I am a farmer, which loans…" saved nothing) | Router used to shorten the message before extraction; extraction now reads the original message, plus regex facts and extractor prompt with allowed values |
| Noisy, very long multi-scheme replies and replies to plain facts | Refiner summaries (M6 mostly fixed) |
| "Which loans and schemes…" returned "not sure" | Target resolver can answer `both` |
| Rupee amounts read as "1,000, rupees 2,000, rupees" | Fixed in `humanize` |

### Open — High
| ID | Issue | Impact / suggested fix |
|---|---|---|
| H1 | **Non-English replies skip the verdict check.** The refiner verifies the eligible/not-eligible phrase only for English; for Hindi etc. only numbers are checked | A translation could flip "not eligible". Fix: translate **templated** sentences per language instead of using the LLM, or check the verdict in each language |
| H3 | **Groq free-tier throttling** (8,000 tokens/min/model) | Latency spikes under load. Fix: dev-tier key; retries with backoff; per-user rate limits |
| H7 | **Mobile app not connected** to the (now deployed) backend | See section 13, R3 |
| H8 | **Slow replies on the cloud (6–11 s)**: a new database connection per call | Add a connection pool; check that Render and Supabase are in the same region |

### Open — Medium
| ID | Issue |
|---|---|
| M1 | Open registration and no rate limit on `/messages` or `/transcribe`: anyone can create accounts and drain the Groq quota |
| M2 | Login rate limit is keyed on `login_id` only, so anyone can lock a user out by spamming their number; no per-IP limit |
| M3 | Only the latest refresh token per customer is valid (logging in on a second phone signs out the first); two simultaneous refreshes make the second fail — the app must serialise refreshes |
| M4 | No logout/revoke endpoint, password reset, or account deletion; phone/email not validated or normalised (`+91 99999…` and `99999…` become two accounts) |
| M5 | Session ownership expires after 24 h (→ 403, the app must start a new session) but `session_context:*` has no TTL and grows forever |
| M6 | Voice UX: much improved by the summaries; the refiner can still add extras in non-English replies; "still needs" mixes unmet requirements with unknown ones |
| M7 | Partial-eligibility ("you'd qualify if…") not used in replies; engine `confidence` is a placeholder 1.0; no benefits/explanations beyond the document answers |
| M8 | Field prompts and eligibility sentences are English; other languages rely on LLM translation |
| M9 | Self-reported facts are trusted as given (no corroboration with bank records) |
| M10 | Rules are hand-coded; PDFs feed RAG only, so a document and a rule can disagree. Rule proposals + human approval (Phase 8) not built |
| M11 | No OCR: scanned PDFs end `needs_ocr` and are skipped |
| M12 | No automated tests run without live Groq; no CI |
| M13 | Logging is minimal; no PII redaction, no metrics |
| M14 | Free-tier hosts sleep when idle; the first request can take 30–60 s (and ~512 MB RAM may be tight with DSPy/LiteLLM) |
| M15 | Keyword document search is weaker than vector search and poor for non-English questions; adding a *new* PDF still needs an embedding key |
| M16 | Regex facts only know common phrasings; "I have 6000" is read as monthly income (the only money fact) |
| M17 | Key rotation is per call, not on error: a key that is already throttled still receives its turn |
| M18 | Offline mode needs the database: if Postgres is unreachable, saved facts cannot be read |

### Open — Low
- Chunk overlap can start mid-word (`ent from time to time…`); retrieval still works.
- The source line can repeat the same file for two pages.
- A changed PDF is ingested as a new document and the old one stays searchable; there is no delete or replace-in-place endpoint.
- `results[]` exposes raw ids only; the app would need friendly-name fields to show them.
- `document_ingestion/` and `offline/` are empty placeholders.

---

## 13. What Still Needs To Be Done (recommended order)

**R1 — Backend gaps still open** (small, mostly independent)
1. Verdict-safe translation for non-English replies (H1). *Done already: forbidden-field guard (H2), RAG unavailable vs not found (H4), embedding retry + keyword fallback (H5), auto migrate/seed (H6).*
2. Connection pool and region check to cut cloud latency (H8).
3. Rate limits on chat/transcribe and per-IP on auth (M1, M2) — skippable for a demo.

**R2 — Deploy** — *done for a demo* (Render + Supabase Session pooler + Upstash, `AUTO_SETUP=true`, `ENABLE_DEBUG_ROUTES=false`, PDFs baked into the image). Still to do: keep the service warm before a demo, check the admin document list, and tolerate cold starts in the app (60 s timeout, "waking up" message).

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
python -m pytest -q                          # 126 tests (some call real Groq)
python main.py                               # chat in the terminal (/lang hi-IN, /new, /reset, /quit)
```
On a fresh cloud database set `AUTO_SETUP=true` instead of running the migrate/seed/sync commands by hand.
`backend/.env` (git-ignored; template in `.env.example`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL`, `REDIS_URL` | Postgres / Redis (cloud: Neon pooled URL, Upstash `rediss://`) |
| `JWT_SECRET` | **Required**; `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GROQ_API_KEY` | LLM + speech-to-text; may hold several keys separated by commas |
| `GROQ_API_KEYS` | Optional extra Groq keys (comma separated); all keys are used round-robin |
| `AUTO_SETUP` | `true` = migrate, seed missing rules and sync `documents/` on every start |
| `EMBEDDING_API_KEY` | Gemini key for RAG embeddings (optional: without it questions use keyword search and new PDFs cannot be embedded) |
| `ADMIN_API_KEY` | Enables `/api/v1/admin/*` and `/health/deps` |
| `ENABLE_DEBUG_ROUTES` | `true` only for local development and the legacy tests |
| `WORKER_LLM_MODEL`, `FAST_LLM_MODEL`, `LLM_REASONING_EFFORT` | Model choices (defaults in `settings.py`) |
| `RAG_DOCUMENTS_DIR` | Folder read by the sync (default `documents`) |

Quick end-to-end check with `curl`: see `connect.md` section 10.

---

## 15. Risks

| Risk | Mitigation / status |
|---|---|
| Free-tier LLM and embedding limits stall the demo | Fewer calls per turn (done); several Groq keys (done); embedding retries and keyword fallback (done); dev-tier key; keep a rehearsed script |
| The free Render service is asleep when the demo starts | Open `/health` a few minutes before; consider a paid instance |
| A translated reply states the wrong verdict | Open (H1) — fix before demoing in Hindi to real users |
| Wrong answers from documents | RAG refuses below similarity 0.45 and answers only from retrieved text; spot-check each new PDF |
| Rule encoding for real schemes is slow and error-prone | Rules are hand-coded and versioned; Phase 8 review flow would help |
| Secrets in the app bundle | Fixed on the backend (`/transcribe`); the app still ships the Groq key until R3 |
| Scope creep (A2A, marketplace, kiosk hardware) | This file is the reference; deviations are recorded in section 2 |
