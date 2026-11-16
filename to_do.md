# DEMO DEPLOY (Render + Supabase + Upstash) - do this section first

Scope: call demo only, not for many users. Skip section 9 and the abuse/limit items (M1, M2, M3, M4).

**Done in code:** `AUTO_SETUP=true` runs migrations, seeds missing eligibility rules and syncs `backend/documents/` on every start. The Dockerfile uses Render's `$PORT`.

**You do:**
1. **Supabase**: create a project. Use the *Session pooler* connection string (Connect -> Session pooler, port 5432). Render has no IPv6, so the "direct" string won't work. Add `?sslmode=require`. pgvector is created by the migration; no manual step.
2. **Upstash**: create a Redis database and copy the `rediss://...` URL (with the double s).
3. **Render**: New Web Service -> connect the repo -> Root Directory `backend`, Runtime Docker. Health check path `/health`. Free tier sleeps after ~15 min, so open the app once before the demo.
4. **Environment variables on Render:**
   - `DATABASE_URL`, `REDIS_URL`
   - `GROQ_API_KEY`, and `GROQ_API_KEYS=key2,key3` for more keys (used round-robin)
   - `EMBEDDING_API_KEY` (optional, see "Gemini key" below)
   - `JWT_SECRET`, `ADMIN_API_KEY` (new random values, not your local ones)
   - `AUTO_SETUP=true`, `ENABLE_DEBUG_ROUTES=false`
5. **Check** (logs show "applied migrations" and "seeded eligibility rules"):
   - `curl https://<app>.onrender.com/health`
   - `curl -H "X-Admin-Key: <key>" https://<app>.onrender.com/health/deps` -> postgres ok, redis ok
   - Register, log in and send a message with curl.
6. **Documents**: PDFs under `backend/documents/<scheme_id>/` must be committed (they go into the image) or sent via `POST /api/v1/admin/documents/sync`.
7. **Mobile app**: section 7 below is still the biggest job (auth screens, the new API contract, STT through the backend, HTTPS URL).

**Gemini key:** the PDFs are already embedded, so the key is only used to embed each *question*. Without `EMBEDDING_API_KEY` (or if Gemini fails) the app searches the documents by keyword instead. That works best when the question names the scheme and is weaker for Hindi. Keeping the key costs one small call per document question. Note: a *new* PDF added later still needs the key to be embedded.

**Done in code (since the first version of this list):**
- [x] H2: a message containing a PIN, OTP, CVV, password or 16-digit card number is refused before any model sees it, and nothing is stored.
- [x] H4: "I am having trouble looking that up" for failures; "could not find that" only when the documents really don't say.
- [x] H5: embedding retries with waits (15/30/60/60 s) while ingesting; two quick retries for questions; keyword search as the fallback.
- [x] H6: `AUTO_SETUP=true` runs migrations, seeds missing rules and syncs `documents/` on start.
- [x] Groq key rotation (`GROQ_API_KEYS`).
- [x] Offline eligibility: cached rules, regex fact extraction and keyword routing when the LLM can't be reached.
- [x] Short replies: many-scheme answers and plain facts are summarised by the refiner.
- [x] Facts in a question ("I am a farmer, which loans...") are saved (the router used to drop them).
- [x] `python main.py` runs a terminal chat for local testing.

**Still worth fixing for a demo:** H1 (Hindi verdict check). Groq's free-tier limit (8,000 tokens/min per model, per key) can still slow replies if several people try it at once; add more keys to `GROQ_API_KEYS`.

---

# Sahayak AI — To-do before deploying

Everything that has to be done before the app can be released to real users, in the order to do it. Tick the boxes as you go.

Legend: **[you]** = needs your account, key or decision · **[code]** = a code change (ask Claude to do it) · **[both]** = you provide something, then code or config follows.

Background: `docs/banking_voice_agent_architecture.md` (status, issues, roadmap) and `connect.md` (connection plan). Issue ids like H1 / M2 refer to section 12 of the architecture doc.

---

## 0. Decide first (10 minutes, blocks everything else)

- [ ] **[you]** Where will the backend run? Recommended free path: Render (simplest) or Google Cloud Run (no long sleep, needs a card).
- [ ] **[you]** Which database host? Neon or Supabase (both support pgvector). Pick one.
- [ ] **[you]** Which Redis host? Upstash (free tier, TLS `rediss://` URL).
- [ ] **[you]** Is this a class demo or a real public release? A public release needs everything in sections 1–9; a demo can skip the items tagged *(public only)*.
- [ ] **[you]** Accept that free tiers sleep or throttle (see section 8) — or budget for a paid Groq key and an always-on host.

---

## 1. Backend fixes before it goes online

Do these first; they are the known gaps that are risky once real people use it.

### Must fix
- [ ] **[code] H1 — Hindi/other-language verdict check.** Today only English replies are checked for a flipped "eligible / not eligible". Translate fixed sentences from per-language templates, or verify the verdict in every language.
- [x] **H2 — Forbidden-field guard.** Done for chat messages (refused before processing). `PATCH /me/profile` only accepts the known profile fields, so a PIN can't be stored there either.
- [x] **H4 — RAG error handling.** Done (see above).
- [x] **H5 — Embedding retry + back-off.** Done; a second provider is no longer needed because keyword search is the fallback.
- [x] **H6 — Auto migrate + seed on start.** Done with `AUTO_SETUP=true`. Still **[you]** check the Render logs on the first start.
- [ ] **[code] M1 / M2 — Abuse limits.** Rate-limit `/messages` and `/transcribe` per user, and auth per IP as well as per `login_id`. Right now anyone can register unlimited accounts and drain your Groq quota, or lock a user out by spamming their number.

### Should fix
- [ ] **[code] M5** — put a TTL on `session_context:*` in Redis (it grows forever).
- [ ] **[code] M3** — allow more than one device per account (or document that logging in elsewhere signs the first phone out); add a logout endpoint that revokes the refresh token.
- [ ] **[code] M4** — validate and normalise phone/email (`+91 99999…` and `99999…` are currently different accounts).
- [ ] **[code] M13** — structured logging without personal data (no phone numbers, no message text in logs).
- [ ] **[code]** `requirements.txt` ships `pytest` and `pytest-asyncio` to production — split into a dev file.
- [ ] **[code]** Dockerfile: bind to the host's `$PORT` (Cloud Run uses 8080, Render sets `PORT`); the file currently hard-codes 8000. Consider `--workers 2`.

### Can wait until after the first release
M6–M12 (shorter voice summaries, partial-eligibility message, OCR, rule proposals from documents, fact corroboration, CI without live LLM). See the architecture doc section 13.

---

## 2. Accounts and keys to create

- [ ] **[you]** Database project (Neon/Supabase). Copy the **pooled** connection string; it must end with `?sslmode=require`.
- [ ] **[you]** Redis database (Upstash). Copy the `rediss://default:PASSWORD@HOST:PORT` URL.
- [ ] **[you]** Hosting account (Render / Cloud Run), connected to your GitHub repo.
- [ ] **[you]** Groq key for production (console.groq.com). Free tier is **8,000 tokens per minute per model**; one user can use it up. Consider the paid/dev tier for any real traffic.
- [ ] **[you]** Extra Groq keys (separate accounts) for `GROQ_API_KEYS`; each key has its own 8,000 tokens/min limit.
- [ ] **[you]** *(optional)* Gemini key for embeddings (aistudio.google.com/apikey): needed to embed new PDFs and for the best document search.
- [ ] **[you]** Expo account + EAS (for building the real app): `npx eas-cli@latest login`.
- [ ] **[you]** *(public only)* Google Play developer account ($25 once) and/or Apple Developer account ($99/year) to publish. For a demo, an Android APK shared directly is enough.

---

## 3. Secrets and environment variables

Set these in the host's dashboard — **never commit them**. `backend/.env` is git-ignored; keep it that way.

- [ ] **[you]** `DATABASE_URL` — pooled cloud URL (`?sslmode=require`)
- [ ] **[you]** `REDIS_URL` — `rediss://…`
- [ ] **[you]** `JWT_SECRET` — generate a **new** one for production: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Do not reuse your local one. Changing it later logs everyone out.
- [ ] **[you]** `ADMIN_API_KEY` — new, long and random (it protects document upload and `/health/deps`)
- [ ] **[you]** `GROQ_API_KEY`, optional `GROQ_API_KEYS` (comma separated), optional `EMBEDDING_API_KEY`
- [ ] **[you]** `AUTO_SETUP=true`
- [ ] **[you]** `ENABLE_DEBUG_ROUTES=false` — **critical**. When true, `/profiles/*`, `/session-context/*` and `/api/v1/query` expose every customer's data with no login.
- [ ] **[you]** Optional: `WORKER_LLM_MODEL`, `FAST_LLM_MODEL`, `LLM_REASONING_EFFORT`, `RAG_DOCUMENTS_DIR`
- [ ] **[you]** Confirm `git status` shows no `.env` and that no key was ever pasted into a committed file. If one was, **rotate it**.

---

## 4. Database and data

- [ ] **[both]** Run the migrations against the cloud database: `python -m database.migrate` (with `DATABASE_URL` pointing at the cloud DB). All six apply; 0005 needs `CREATE EXTENSION vector` — Neon and Supabase allow it. If the chunk tables are skipped, run `python -m rag.setup`.
- [ ] **[both]** Seed the eligibility rules **without the demo customers**: `python -c "from eligibility_engine.seed import seed_all; print(seed_all())"`. (`python -m scripts.seed_sample_data` also creates fake customers `cust-001…`; do not use it in production.) Expect 9 scheme ids back.
- [ ] **[you]** Review the 9 rules against the real scheme rules. They are hand-coded from the design doc; a wrong threshold is a wrong answer for every customer.
- [ ] **[you]** Check backups are on (Neon/Supabase keep point-in-time history on paid tiers; on free tiers export manually before big changes).

---

## 5. Documents for RAG

- [ ] **[you]** Collect the official PDFs (text PDFs only; scans are skipped as `needs_ocr`).
- [ ] **[you]** Put each in `backend/documents/<scheme_id>/` (valid folder names are in `backend/documents/README.md`).
- [ ] **[you]** Decide how they get to the server: bake the folder into the Docker image, **or** call `POST /api/v1/admin/documents/sync` after deploy (header `X-Admin-Key`). The folder is not excluded from the image.
- [ ] **[you]** After the sync, check `GET /api/v1/admin/documents`: every file should be `active`. Resolve any `needs_review` with `POST …/{doc_id}/review`.
- [ ] **[you]** Ask 3–5 real questions per document and compare with the PDF. Wrong or missing answers → fix the document or the question set before launch.
- [ ] **[you]** *(public only)* Confirm you are allowed to use and redistribute each PDF's content.

---

## 6. Deploy the backend

- [ ] **[you]** Create the web service from the `backend/` folder using the existing Dockerfile; set the env vars from section 3.
- [ ] **[you]** Health check path: `/health`. Confirm the HTTPS URL answers `{"status":"ok"}`.
- [ ] **[you]** Run the quick connection test from `connect.md` section 10 (register → create session → send a message) against the **cloud URL** with `curl`. If curl works, the app will.
- [ ] **[you]** `GET /health/deps` with the admin key: Postgres and Redis must both be `ok`.
- [ ] **[you]** Confirm these are **blocked**: `GET /profiles/cust-001` (404/405, not data), `/api/v1/query`, `/session-context/…`, and the admin routes without the key (401/403).
- [ ] **[you]** Confirm a message to someone else's session returns 403, and a request with no token returns 401.
- [ ] **[you]** Free hosts sleep (Render ~15 min idle, 30–60 s to wake). Either accept it, add an uptime pinger, or pay for an always-on instance.
- [ ] **[you]** Put the host's region near your database and Redis region (every turn makes several round trips).

---

## 7. Connect the mobile app (it is not connected today)

Detailed steps: `connect.md` sections 3.4 and 8, and architecture doc section 13 (R3).

- [ ] **[code]** Add `expo-secure-store`; token store; auth store (`signedOut` / `signedIn`).
- [ ] **[code]** Login and register screens; route guard with `Stack.Protected`; on launch restore the saved session.
- [ ] **[code]** Onboarding + profile screens built from `GET /api/v1/profile/schema`, saving with `PATCH /api/v1/me/profile` (Skip must still work).
- [ ] **[code]** `src/services/api.ts`: real paths and types; `Authorization` header; on 401 refresh **once at a time** and retry; on 403 create a new session; 60 s timeout; ping `/health` when the app opens.
- [ ] **[code]** `src/services/stt.ts`: call `POST /api/v1/transcribe` and **remove `EXPO_PUBLIC_GROQ_API_KEY` from the app** (anything `EXPO_PUBLIC_*` is readable by anyone who has the app).
- [ ] **[code]** Show `display_text` on screen, speak `reply_text`, show sources; "waking up the assistant…" message for cold starts.
- [ ] **[code]** Clear messages and session on logout (otherwise user B sees user A's chat on a shared phone).
- [ ] **[code]** Keep the mock API working for demos (`EXPO_PUBLIC_USE_MOCK_API=true`).
- [ ] **[you]** Set `EXPO_PUBLIC_USE_MOCK_API=false`, `EXPO_PUBLIC_USE_MOCK_STT=false` and `EXPO_PUBLIC_API_BASE_URL=https://<your-host>` in `.env.local` (no trailing slash).
- [ ] **[you]** The URL must be **HTTPS** — iOS and Android release builds block plain `http://`.
- [ ] **[you]** Build a real app (not Expo Go) for testing: `npx eas-cli@latest build --profile preview --platform android`.
- [ ] **[you]** `app.json`: app name, unique `android.package` / `ios.bundleIdentifier`, icon, version, and the **microphone permission text**.

---

## 8. Test before release

- [ ] **[you]** Run the backend suite against local Docker: `python -m pytest -q` → expect 109 passed. (Some tests call real Groq; wait a minute between this and a manual chat to avoid rate limits.)
- [ ] **[you]** On a **real phone**, full loop: register → onboarding → speak a question → see transcript → hear the answer. Test English **and Hindi**.
- [ ] **[you]** Check TTS voices on every phone model you will demo on (Hindi voice packs differ).
- [ ] **[you]** Try the failure cases: airplane mode mid-question, wrong password, expired session, silent recording, noisy room.
- [ ] **[you]** Time a few turns on the cloud host. Expected 1–5 s; 15–30 s means Groq rate-limiting (free tier) or a cold start.
- [ ] **[you]** Test with 2–3 people at once to see the token limit in practice.
- [ ] **[you]** Hand-check eligibility answers for every scheme with a known-eligible and a known-ineligible person.
- [ ] **[you]** Check what the app says when the backend is down.

---

## 9. Safety, privacy and compliance *(public only)*

- [ ] **[you]** Privacy policy and in-app consent: you store phone/email, age, income, family and land details.
- [ ] **[code]** Account deletion and data export (India's DPDP Act and Play Store rules expect them).
- [ ] **[you]** Add a clear disclaimer: answers are guidance, not a bank decision; the bank decides.
- [ ] **[you]** Say in the app that the assistant never needs a PIN, OTP or password.
- [ ] **[you]** Decide who can be an admin and who holds `ADMIN_API_KEY`.
- [ ] **[code]** Password reset (needs an SMS/email/OTP provider) — otherwise a forgotten password means a lost account.

---

## 10. After launch

- [ ] **[you]** Watch the host logs for the first days (the RAG, router, refiner and orchestrator now log a warning when an LLM call fails).
- [ ] **[you]** Set an alert or check daily: Groq/Gemini usage, database size (free tiers are ~0.5 GB), Redis commands.
- [ ] **[you]** Keep a rollback: tag the release in git and know how to redeploy the previous version.
- [ ] **[you]** Re-run the document sync whenever a PDF changes (changed files are added as **new** documents; the old one stays searchable until removed from the database).
- [ ] **[you]** Write down what you would do if a rule was wrong: fix the rule row (new version), redeploy, tell users.

---

## Suggested order, if you only have a short time (demo)

1. Section 1: H1 only if you demo in Hindi (H2, H4, H5, H6 are done; M1 can be skipped for a demo).
2. Sections 2–4: create accounts, set secrets (**debug routes off**), migrate, seed rules.
3. Section 5: add PDFs and sync.
4. Section 6: deploy, then test with `curl`.
5. Section 7: connect the app.
6. Section 8: test on a real phone, then rehearse the demo.
