# Connecting the Sahayak Mobile App to the Backend

This is the plan for wiring `sahayak-mobile/` (Expo / React Native) to `backend/` (FastAPI),
moving everything that currently runs on `localhost` into the cloud, and adding the three
things that don't exist yet: **JWT login**, a **RAG agent**, and the **Sahayak_AI router**.

It is based on `backend/WORKING.md`, `backend/sahayak_ai_final_architecture_and_execution_plan.md`,
`docs/mobile_voice_client_plan.md`, and a read of the actual code. Section 1 lists what is
true *today*, so the rest of the document builds on facts rather than on what the older docs hoped for.

Free-tier limits change often. Every number below is "roughly, at time of writing" -
check the provider's pricing page before depending on one.

---

## 1. Where things stand today

### What works
| Piece | State |
|---|---|
| Backend `POST /api/v1/query` | Works. Fact extraction -> turn classification -> LoanAgent/SchemeAgent -> deterministic eligibility engine -> reply. Facts persist per customer. |
| Eligibility engine, 9 hand-coded rules | Works, deterministic, no LLM. |
| Postgres (profiles, field history, rules) + Redis (session context) | Work, but only on `localhost` via docker-compose. |
| Mobile: record -> Groq Whisper STT -> API call -> `expo-speech` TTS | Works against a **mock** API (`EXPO_PUBLIC_USE_MOCK_API=true`). |

### Why they are not connected - the concrete gaps
1. **Different URLs.** The app calls `POST /api/v1/sessions`, `POST /api/v1/sessions/{id}/messages`,
   `GET /api/v1/health` (`sahayak-mobile/src/services/api.ts`). The backend has none of these. It has
   `POST /api/v1/query` and `GET /health`.
2. **Different request/response shapes.** App sends `{text, language}` and expects
   `{reply_text, language, eligible, missing_fields, session_state}`. Backend wants
   `{customer_id, session_id, text, extra_fields}` and returns `{reply_text, results[], facts_updated, turn_type}`.
3. **Nobody is logged in.** The backend takes `customer_id` from the request *body*, so any caller can
   read or write any customer's data. The app has no notion of a user.
4. **The JWT code is half-built and not live.**
   - `backend/security/auth.py` reads `settings.jwt_secret` / `settings.jwt_algorithm` - **neither exists in `settings.py`**.
   - `PyJWT` is **not in `requirements.txt`** (`import jwt` will fail on a fresh install).
   - `security/api.py` (`/auth/login`) is **never included in `main.py`**.
   - `get_current_customer_id` is **not used by any route**.
   - `/auth/login` accepts a bare `customer_id` with **no credential check** - it was designed for a kiosk with a card reader. A phone has no such hardware, so it needs real credentials (section 3).
5. **Everything is on localhost.** A phone cannot reach `localhost:5432` / `localhost:6379` / `localhost:8000`.
   iOS also blocks plain-`http://` hosts in release builds, and Android blocks cleartext in release builds - so you need HTTPS, which any cloud host gives you for free.
6. **The unauthenticated debug routes must not go to the cloud.** `/profiles/*`, `/session-context/*`, `/health/deps`
   expose every customer's data and the DB/Redis error text. Remove or protect them before the first deploy.
7. **The Groq API key is inside the app bundle** (`EXPO_PUBLIC_GROQ_API_KEY`) because the phone calls Whisper directly.
   Fine for a class demo, not for a public build (section 8).
8. **No RAG, no ingestion.** `backend/document_ingestion/` is an empty package.

---

## 2. Target architecture

```
 Expo app ──HTTPS + JWT──▶  FastAPI backend (cloud)
 (voice in/out)              │
                             ├─ /auth/*        register, login, refresh
                             ├─ /api/v1/me/*   profile (view / edit)
                             ├─ /api/v1/sessions, /messages  ◀── the chat entry point
                             └─ /api/v1/admin/documents       (upload PDFs)
                                        │
                                  ┌─────▼──────────────┐
                                  │   Sahayak_AI       │  router + transport + refiner
                                  │   (orchestrator)   │  no business logic of its own
                                  └──┬──────────────┬──┘
                       eligibility   │              │   RAG
                       agent         ▼              ▼   agent
                  (today's supervisor/workers   (new: retrieval + answer
                   + engine, unchanged)          over loan / scheme vectors)
                                  │                    │
                       Postgres ◀─┴──── Redis          └──▶ Postgres + pgvector
                       (profiles, rules, users)   (sessions)   (loan_chunks, scheme_chunks)
```

Rule that keeps the three AI parts independent: **Sahayak_AI only calls each agent through one
fixed function and passes data in/out. It never reaches into an agent's internals, and neither agent
imports the other.** Section 6 defines those interfaces.

---

## 3. JWT login (backend + mobile)

### 3.1 Identity model
Add a `customers` (auth) table - separate from `customer_profiles`, which stays the profile store:

```sql
-- backend/database/migrations/0004_customers_auth.sql
CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,            -- uuid4 string; this is the JWT "sub"
    login_id      TEXT UNIQUE NOT NULL,        -- phone number or email
    password_hash TEXT NOT NULL,               -- argon2 / bcrypt, never plaintext
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    profile_completed BOOLEAN NOT NULL DEFAULT false
);
```
Keep `customer_id` as the same TEXT key that `customer_profiles` already uses, so no existing table changes.
(Foreign key from `customer_profiles.customer_id` is optional; the sample seed customers `cust-001...` have no auth row.)

**Credential choice.** Simple and free: phone-or-email + password (hash with `argon2-cffi` or `passlib[bcrypt]`).
Phone-OTP is nicer for the target users but needs an SMS provider (Firebase Auth phone is free to a small daily quota -
an option later). Start with password; the JWT layer is identical either way.

### 3.2 Backend changes
1. `requirements.txt`: add `PyJWT`, `argon2-cffi` (or `passlib[bcrypt]`).
2. `settings.py`: add
   ```python
   jwt_secret: str                       # no default - app must refuse to start without it
   jwt_algorithm: str = "HS256"
   access_token_minutes: int = 30
   refresh_token_days: int = 30
   ```
   Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. `security/api.py` - replace the bare `customer_id` login with:
   - `POST /auth/register` `{login_id, password}` -> creates `customers` row (new uuid `customer_id`) -> returns tokens.
   - `POST /auth/login` `{login_id, password}` -> verifies hash -> returns tokens.
   - `POST /auth/refresh` `{refresh_token}` -> new access token (and rotate the refresh token).
   - Response: `{access_token, refresh_token, token_type:"bearer", customer_id, profile_completed}`.
   - Add a `"type": "access" | "refresh"` claim in `create_access_token` and reject a refresh token used as an access token.
4. `main.py`: `app.include_router(auth_router)`.
5. **Make `customer_id` come only from the token.** Every protected route takes
   `customer_id: str = Depends(get_current_customer_id)` and ignores any `customer_id` in the body.
   This is the line that makes "we know which customer logged in" actually true.
6. Rate-limit `/auth/login` (e.g. 5 tries/minute per `login_id`, counter in Redis) so passwords can't be brute-forced.

### 3.3 Session id (server-issued and owned)
Today the client invents `session_id`. Instead:

- `POST /api/v1/sessions` (JWT required) -> server creates a uuid, stores
  `SET session_owner:{session_id} {customer_id} EX 86400` in Redis, returns `{session_id}`.
- `POST /api/v1/sessions/{session_id}/messages` first checks that `session_owner:{session_id}` equals the
  token's `customer_id`; otherwise **403**. A leaked/guessed session id is then useless to anyone else.
- The existing `supervisor/context_store.py` keeps storing the conversation per session unchanged.

So: **JWT = who you are (`customer_id`)**, **session id = which conversation**, and the backend enforces that the second belongs to the first.

### 3.4 Mobile changes
New dependency: `npx expo install expo-secure-store` (Keychain / Keystore - never use AsyncStorage for tokens).

| New file | Purpose |
|---|---|
| `src/services/token-store.ts` | `getTokens / saveTokens / clearTokens` over `expo-secure-store` |
| `src/store/auth.ts` (Zustand) | `{customerId, profileCompleted, status: 'loading'\|'signedOut'\|'signedIn'}`, `login()`, `register()`, `logout()`, `restore()` |
| `src/app/(auth)/login.tsx`, `register.tsx` | The two screens |

Changes to existing files:
- `src/services/api.ts`
  - Add an axios **request interceptor**: `Authorization: Bearer <access_token>`.
  - Add a **response interceptor**: on `401`, call `/auth/refresh` once, retry the original request; if refresh fails -> `logout()`.
  - Replace the paths and types with the real contract in section 9.
  - Raise `TIMEOUT_MS` from 20s to ~60s for the first call (free hosts cold-start, section 4.3), and ping `/health` when the app opens to wake the server early.
- `src/app/_layout.tsx` - guard routes with Expo Router's `Stack.Protected`:
  ```tsx
  <Stack>
    <Stack.Protected guard={status === 'signedOut'}>
      <Stack.Screen name="(auth)" options={{ headerShown: false }} />
    </Stack.Protected>
    <Stack.Protected guard={status === 'signedIn' && !profileCompleted}>
      <Stack.Screen name="onboarding" />
    </Stack.Protected>
    <Stack.Protected guard={status === 'signedIn' && profileCompleted}>
      <Stack.Screen name="index" />
      <Stack.Screen name="profile" />
      <Stack.Screen name="settings" />
    </Stack.Protected>
  </Stack>
  ```
  On launch `restore()` reads the token store, so users stay logged in.
- `src/store/conversation.ts` - `resetConversation()` and `logout()` must clear `sessionId` and `messages`
  (otherwise user B inherits user A's chat on a shared phone).
- `src/services/api-mock.ts` - add mock `login/register/profile` so `USE_MOCK_API=true` still demos end to end.

---

## 4. What to move from local to the cloud (and free options)

| Local today | Cloud replacement | Free option (verify limits) | Notes |
|---|---|---|---|
| Postgres (docker `postgres:16`) | Managed Postgres | **Neon** (~0.5 GB, scales to zero) or **Supabase** (~500 MB, pauses after ~1 week idle) | Both support the `pgvector` extension, so they also cover the vector DB (section 5.3). |
| Redis (docker `redis:7`) | Managed Redis | **Upstash Redis** (free tier: ~256 MB, ~500K commands/month) | Use the `rediss://` (TLS) URL. A chat turn costs only a handful of commands. Redis Cloud's 30 MB free tier is the alternative. |
| FastAPI (`uvicorn` on your PC) | Container host with HTTPS | **Render** free web service (sleeps after ~15 min idle) - simplest; **Google Cloud Run** (generous free quota, needs a card) - no long sleep problem; **Hugging Face Spaces (Docker)** also works | Backend already has a `Dockerfile`. All give an `https://...` URL. |
| (none) PDF storage | Object storage | **Cloudflare R2** (~10 GB free) or **Supabase Storage** (~1 GB) | Keep original PDFs so a document can be re-ingested. Optional for v1: you can store only extracted text. |
| Groq (already cloud) | - | Groq free tier | Keep. Shared key lives **only** on the backend. |
| Embeddings (new) | API-based embeddings | **Google Gemini embeddings** or **Cohere embed-multilingual** free/trial keys | Don't run a local embedding model on a 512 MB free host. Choose a *multilingual* model - users speak Hindi etc. |
| Dev tunnel (before deploying) | - | **cloudflared** / **ngrok** | Expose `localhost:8000` over HTTPS so a real phone can test while DB/Redis are still local. |

### 4.1 Environment variables the backend needs in the cloud
```
DATABASE_URL=postgresql://USER:PASS@HOST/DB?sslmode=require   # Neon/Supabase give this; use the pooled string
REDIS_URL=rediss://default:PASSWORD@HOST:PORT                   # Upstash
GROQ_API_KEY=...
JWT_SECRET=...                                                  # new, 48+ random chars
EMBEDDING_API_KEY=...                                           # new, for RAG
ADMIN_API_KEY=...                                               # new, protects document upload
```
Set them in the host's dashboard - never commit them (`backend/.env` is already git-ignored).

### 4.2 Move the data
```
# once, from your PC, with DATABASE_URL pointing at the cloud DB
python -m database.migrate
python -m scripts.seed_sample_data      # rules (and demo profiles - skip the demo profiles in a real deployment)
```
`database/migrate.py` is idempotent, so re-running is safe. Add `CREATE EXTENSION IF NOT EXISTS vector;` as a migration for pgvector.

### 4.3 Free-tier behaviour the app must tolerate
- **Cold start**: Render's free instance takes ~30-60 s to wake. The app should show "Waking up the assistant..." instead of an error, and retry once.
- **Neon scale-to-zero**: first query after idle adds ~1 s. `database/db.py` opens a new connection per call; that is fine with the pooled URL.
- Keep local `docker-compose.yml` for offline development; just point `.env` at the cloud for integration tests.

---

## 5. RAG agent (documents -> classification -> separate vectors -> chatbot)

New package `backend/rag/` (use the empty `document_ingestion/` for step A).

### 5.1 Ingestion pipeline (admin uploads a PDF)
`POST /api/v1/admin/documents` (header `X-Admin-Key`, multipart PDF, optional `scheme_id`):

1. **Extract text** per page (`pymupdf` or `pypdf`; if a page has no text it is a scan -> flag for OCR, don't silently ingest nothing).
2. **Classify `loan` vs `scheme`.** One LLM call (a DSPy signature like the existing `ClassifyDomain`) over the title + first ~2 pages
   returning `{doc_type: "loan"|"scheme"|"unclear", confidence, suggested_name}`.
   - `confidence` below a threshold or `unclear` -> status `needs_review`, **not embedded** until a human picks the type.
     This matches the architecture doc's "human approval before anything goes live" principle.
3. **Chunk** by headings/paragraphs, ~500-800 tokens with ~100 overlap; keep `page` and section title with each chunk
   (eligibility criteria are usually one section - don't slice through it).
4. **Embed** each chunk with the multilingual embedding model.
5. **Store in the vector table for that type** (separate, as required):
   ```sql
   CREATE TABLE documents (
       doc_id UUID PRIMARY KEY, filename TEXT, doc_type TEXT CHECK (doc_type IN ('loan','scheme')),
       scheme_id TEXT,                 -- links to eligibility_rules.scheme_id when known
       status TEXT, uploaded_at TIMESTAMPTZ DEFAULT now()
   );
   CREATE TABLE loan_chunks (
       chunk_id BIGSERIAL PRIMARY KEY, doc_id UUID REFERENCES documents,
       scheme_id TEXT, page INT, section TEXT, content TEXT, embedding vector(768)
   );
   CREATE TABLE scheme_chunks (LIKE loan_chunks INCLUDING ALL);  -- same shape, separate table
   CREATE INDEX ON loan_chunks   USING hnsw (embedding vector_cosine_ops);
   CREATE INDEX ON scheme_chunks USING hnsw (embedding vector_cosine_ops);
   ```
   Two physical tables = two independent vector spaces: a "PM loan" question can never retrieve scheme text by accident.
   The vector size (768 here) must equal your embedding model's output size - changing the model later means re-embedding.
   *Alternative:* a hosted vector DB (Qdrant Cloud free ~1 GB, Pinecone free) with two collections. pgvector is recommended because it adds no new service or credentials.

### 5.2 Chatbot (query time)
`rag.agent.answer(question, domain=None, scheme_id=None) -> RagAnswer`
1. Embed the question.
2. Search `loan_chunks` / `scheme_chunks` (both if `domain` unknown), **filtered by `scheme_id` when the conversation already knows it** (so "PM loan" doesn't mix with another loan), top-k ~5.
3. If the best similarity is below a threshold -> return `{answer: None, confidence: low}` ("I don't have that in the documents") - never let the LLM guess.
4. LLM (Groq) answers **only from the retrieved chunks** and returns the answer plus the chunk ids it used.
5. Returns `{answer, sources:[{doc, page}], confidence}`.

Example: after uploading the "PM loan" PDF, "What is the eligibility criteria for the PM loan?" retrieves the eligibility section and answers from it.

### 5.3 Optional but valuable: documents -> rules
The same ingestion can propose `eligibility_rules` rows (field/op/value) from the PDF, saved with `is_active=false`
for a human to approve (this is Phases 7-8 in the architecture plan). Until then the 9 hand-coded rules and the RAG text can disagree -
keep `documents.scheme_id` aligned with `eligibility_rules.scheme_id` so you can tell.

---

## 6. Sahayak_AI - the router/orchestrator

Today `supervisor/agent.py` does everything in one function. Split it so **Sahayak_AI is a thin layer**:

```
backend/sahayak_ai/
    router.py      classify the message into sub-tasks
    orchestrator.py  run sub-tasks, collect results, call refiner
    refiner.py     make the final text voice-friendly
backend/eligibility_agent/   (today's run_query_pipeline, wrapped - behaviour unchanged)
backend/rag/                 (section 5)
```

### 6.1 The two fixed agent interfaces (the only thing Sahayak_AI knows about them)
```python
# eligibility agent - wraps the existing run_query_pipeline
async def check(customer_id, session_id, text, scheme_id=None) -> EligibilityOutput
#   -> {results:[{scheme_id, eligible, satisfied, missing}], facts_updated:[...], reply_text}

# rag agent
async def answer(question, domain=None, scheme_id=None) -> RagAnswer
#   -> {answer|None, sources:[...], confidence}
```
The orchestrator treats outputs as opaque data. It does not edit the eligibility rules, prompts, or retrieval -
that is what "only a transport" means.

### 6.2 Router
One DSPy call (same style as `ClassifyTurnIntent`) returns an **ordered list of sub-tasks**, so one sentence can produce several:

```python
class SubTask(BaseModel):
    agent: Literal["eligibility", "rag"]
    text: str                        # the part of the message this agent should handle
    scheme_id: str | None = None     # resolved from message or from session's active scheme

class RoutePlan(BaseModel):
    subtasks: list[SubTask]          # 1..n, in the order they should run
```

| User says | Plan |
|---|---|
| "Am I eligible for the PM loan?" | `[eligibility("Am I eligible for the PM loan?")]` |
| "What is the minimum age of the daughter?" | `[rag(...)]` |
| "I have a daughter who is 17" (a fact, no question) | `[eligibility(...)]` - the existing pipeline extracts + stores the fact and re-checks the pending scheme |
| "What is the minimum age for this loan **and why**" | `[eligibility("What is the minimum age for this loan?"), rag("Why is there a minimum age for this loan?")]` |

Implementation notes:
- **Resolve "this loan / this scheme"** from the session: write `active_scheme_id` into the session context (the supervisor is already the single writer of `ContextEntry`) and pass it into each sub-task.
- Few-shot examples in the router signature are essential here - include the four rows above.
- If the router is unsure, default to `[rag]` for questions and `[eligibility]` for statements; never raise a 422 at a voice user.
- Run independent sub-tasks concurrently (`asyncio.gather`); run in order only if a later one needs an earlier result.

### 6.3 The walkthrough from the requirements
1. *"Am I eligible for the PM loan yojana?"* -> eligibility agent -> `eligible:false, missing:["has_daughter"]` -> refiner says "You are not eligible yet. I need to know whether you have a daughter."
2. *"What should be the minimum age of the daughter?"* -> RAG agent -> "The daughter should be at least 8 years old." (from the PDF).
3. *"I have a daughter, she is 17."* -> eligibility agent: extracts `daughter_age=17`, **stores it**, re-checks, answers eligible / not eligible.

### 6.4 Updating the DB with the new fact
The existing pipeline already persists extracted facts per customer (`upsert_extra_facts`, EAV table) and reloads them every turn,
so step 3 above works for the next session with no new code. Two recommendations:
- **Persist the fact whether or not it makes them eligible.** The requirement text says "if it meets the requirement, update the db" - but a fact such as "my daughter is 17" is true about the user either way, and other schemes may need it. Store always; let eligibility be recomputed from stored facts.
- **Store raw facts (`daughter_age: 17`), not pre-digested booleans** (`has_girl_child_under_10`). Once rules come from PDFs the thresholds change (8, 10, 18...) and a stored boolean silently goes stale.

### 6.5 Refiner (voice-friendly output)
`refiner.refine(outputs: list[AgentOutput], language: str) -> {speech_text, display_text}`
- Input: structured results from the agents (eligible flag, missing fields, RAG answer).
- Output rules: short sentences, max ~3, no markdown/bullets/symbols, numbers as words where TTS reads them badly, "Rs" -> "rupees", one clear next step ("Please tell me your age"), reply in the user's language.
- `speech_text` goes to TTS; `display_text` (can keep bullets/figures) goes on screen.
- **Guard it like `workers/narration_guard.py` already does:** after the LLM rewrites, check that the eligible/not-eligible verdict and every number from the agent output still appear; if not, fall back to a deterministic template. The refiner may reword, never change a fact.

---

## 7. Profile entry after login, editable later

Flow: **register/login -> (if `profile_completed` is false) Onboarding form -> Chat.** Profile screen reachable any time from the header.

Backend:
- `GET /api/v1/me/profile` -> merges `customer_profiles` (6 fixed fields) with persisted extra facts (`get_known_fields`; the `/profiles/{id}` route does **not** show these today).
- `PATCH /api/v1/me/profile` `{field: value, ...}` -> partial update (the existing `PUT /profiles/{id}` needs *all* fields and a `customer_id`, which is wrong for a form). Core fields go through `upsert_profile` (versioned history kept), extras through `upsert_extra_facts`, source = `"user_form"`. On first successful save set `customers.profile_completed = true`.
- `GET /api/v1/profile/schema` -> list of `{field, label, type, options, required}` built from `schemas/required_fields_seed.py` + `FIELD_PROMPTS`.
  Because the form is driven by this, when a new scheme/loan document needs a new field, it appears in the app without an app release.
- A fact told to the chatbot ("I have a daughter of 17") and a value typed in the form write to the same store, so both stay in sync and the profile screen always shows the latest.

Mobile:
- `src/app/onboarding.tsx` and `src/app/profile.tsx` share one `ProfileForm` component rendered from the schema endpoint. Onboarding blocks the chat until saved; profile screen edits afterward.
- Add a "My details" link to the chat screen header and to Settings. Re-fetch the profile after any chat turn that returns non-empty `facts_updated`.
- Also allow *Skip* on onboarding for fields the user doesn't want to share - the chatbot can collect them later.

---

## 8. Moving speech-to-text behind the backend (recommended)

The app currently ships the Groq key to every phone (`EXPO_PUBLIC_*` values are visible in the bundle).
Add `POST /api/v1/transcribe` (JWT, multipart audio) that forwards to Groq Whisper with the server-side key, and have `src/services/stt.ts` call that instead.
Same for any future TTS service. Doing it now costs ~30 lines and removes the only secret from the client.

---

## 9. The API contract to implement

All routes except `/auth/*` and `/health` require `Authorization: Bearer <access_token>`. Errors: `{"error": {"code", "message"}}`.

| Method + path | Request | Response |
|---|---|---|
| `GET /health` | - | `{status}` (public; `/health/deps` becomes admin-only) |
| `POST /auth/register` | `{login_id, password}` | `{access_token, refresh_token, customer_id, profile_completed}` |
| `POST /auth/login` | `{login_id, password}` | same |
| `POST /auth/refresh` | `{refresh_token}` | same |
| `GET /api/v1/me/profile` | - | `{fields:{...}, profile_completed}` |
| `PATCH /api/v1/me/profile` | `{field: value, ...}` | updated profile |
| `GET /api/v1/profile/schema` | - | `[{field,label,type,options,required}]` |
| `POST /api/v1/sessions` | - | `{session_id}` |
| `POST /api/v1/sessions/{id}/messages` | `{text, language}` | `{reply_text, display_text, language, results[], facts_updated[], sources[], turn_type}` |
| `POST /api/v1/transcribe` | audio file | `{text, language}` |
| `POST /api/v1/admin/documents` | PDF + `X-Admin-Key` | `{doc_id, doc_type, status}` |
| `GET /api/v1/admin/documents` | `X-Admin-Key` | list, including `needs_review` ones |

`messages` is the one the app already calls - it just needs to call Sahayak_AI (`router -> agents -> refiner`) instead of `run_query_pipeline` directly.
`reply_text` is what gets spoken; map the app's existing `meta` to `results[]`/`facts_updated`.

---

## 10. Suggested order of work (each step is testable on its own)

1. **Make the existing parts boot.** Add `jwt_secret` to settings, `PyJWT` to requirements, mount the auth router, delete or guard `/profiles`, `/session-context`, `/health/deps`.
2. **Cloud infra.** Create Neon (or Supabase) DB + Upstash Redis, run migrations, point your local backend at them. `curl /health/deps` is green.
3. **Real login.** `customers` migration, register/login/refresh, `Depends(get_current_customer_id)`, server-issued sessions with ownership check. Tests: wrong password -> 401; token A can't use session of B -> 403.
4. **Wire the app to the real chat (no RAG yet).** Add `/sessions` and `/sessions/{id}/messages` as thin wrappers over `run_query_pipeline`; set `EXPO_PUBLIC_USE_MOCK_API=false`; deploy to Render/Cloud Run; use the cloud URL as `EXPO_PUBLIC_API_BASE_URL`. **This is the milestone where "connected" is true.**
5. **App auth + profile.** Login/register screens, token store, interceptors, route guard, onboarding + profile screens, profile endpoints.
6. **RAG.** pgvector migration, ingestion + classification, `rag.answer`, upload endpoint; test with one real PDF.
7. **Sahayak_AI.** Router, orchestrator, refiner; switch `/messages` to it. Add router tests for the four example sentences in 6.2.
8. **Hardening.** Move STT behind the backend, login rate-limit, admin review queue, cold-start UX.

### Quick connection test once step 4 is done
```
# 1. register
curl -X POST https://<your-host>/auth/register -H "Content-Type: application/json" -d '{"login_id":"9999999999","password":"test-pass-123"}'
# 2. use the returned access_token
curl -X POST https://<your-host>/api/v1/sessions -H "Authorization: Bearer <token>"
curl -X POST https://<your-host>/api/v1/sessions/<sid>/messages -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" -d '{"text":"Can I get a retail micro loan?","language":"en-IN"}'
```
If that works with `curl`, the app will work as soon as `api.ts` points at the same URLs.

---

## 11. Things I noticed that you may want to decide on

- **Example in the requirements**: "minimum daughter age is 8" and "I have a 17-year-old daughter" would mean *not* eligible if 8 is a *maximum*, or eligible if it is a *minimum* - make sure the rule's operator comes from the document, not from an assumption. (This is why section 6.4 stores raw facts.)
- **Hindi/regional input**: the 9 hand-coded rules and `FIELD_PROMPTS` are English. The refiner is where translation happens; the router and RAG embeddings need to be multilingual.
- **Both repos' docs disagree on auth**: the architecture doc says "JWT-gated profile store, kiosk hardware verifies identity". For a phone app that assumption no longer holds - section 3 replaces it.
