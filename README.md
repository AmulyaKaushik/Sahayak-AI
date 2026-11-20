# Sahayak AI

**A voice-first assistant that tells people which bank loans and government schemes they qualify for — in Hindi or English.**

*Sahayak (सहायक) means "helper".* You speak a question into a phone app; it works out the answer and speaks it back, while showing the conversation on screen.

> *"Am I eligible for a Kisan Credit Card?"* → *"You are not eligible yet. You already meet the age requirement. I still need to know how many acres of land you own."*

The yes/no verdict is **never** an AI guess: it comes from fixed, versioned eligibility rules. AI is used only to understand what you said, to answer questions from the official scheme PDFs (with page references), and to phrase the reply.

📖 **New here? Read [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md)** — the whole project explained in plain language.

---

## Features

- 🎤 Speak and listen: voice in, spoken reply out (Hindi and English)
- ✅ Deterministic eligibility checks for 9 schemes and loans (Sukanya Samriddhi, PM Jan Dhan, PMAY Rural Housing, Kisan Credit Card, Retail Micro Loan, Senior Citizen Savings, PM Mudra Shishu, Home Loan, Atal Pension)
- 📄 Document Q&A over 10 policy PDFs, answers cite the document and page
- 🧠 Remembers what you tell it (age, income, land…) across conversations; viewable and editable under **My details**
- 🔐 Phone/email + password login (JWT), per-user conversations, secure token storage
- 🛡️ PINs, OTPs, passwords and card numbers are refused and never stored
- 📶 Handles a sleeping server, expired logins and no-internet gracefully

## How it works

```
 Phone app (Expo / React Native)  ── HTTPS + JWT ──▶  Backend (Python / FastAPI)
   record → speech-to-text (Groq Whisper)               Router ─▶ Eligibility agent ─▶ Rules engine
   show chat · speak reply (phone voices)                     └─▶ Document (RAG) agent
                                                        Refiner ─▶ short, speakable reply
                                                        PostgreSQL + pgvector · Redis
```

Details, diagrams and every component are in [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) and [`docs/banking_voice_agent_architecture.md`](docs/banking_voice_agent_architecture.md).

## Repository layout

| Path | What it is |
|---|---|
| [`sahayak-mobile/`](sahayak-mobile/) | The mobile app (Expo SDK 58, React Native, TypeScript) |
| [`backend/`](backend/) | The API and AI pipeline (Python 3.13, FastAPI) |
| [`docs/`](docs/) | Project overview, architecture, app implementation report, test cases |
| [`connect.md`](connect.md) | Plan for connecting the app to the backend |
| [`to_do.md`](to_do.md) | Remaining work, in order |

## Quick start

You need: **Node 20+**, a phone with **Expo Go** (SDK 58), and a free [Groq API key](https://console.groq.com/keys) for speech-to-text. The backend is already deployed, so you do **not** need to run it to try the app.

### 1. Run the mobile app (against the deployed backend)

```bash
cd sahayak-mobile
npm install
cp .env.example .env.local
```

Edit `.env.local`:

```
EXPO_PUBLIC_USE_MOCK_API=false
EXPO_PUBLIC_API_BASE_URL=https://sahayak-ai-q5ee.onrender.com
EXPO_PUBLIC_USE_MOCK_STT=false
EXPO_PUBLIC_GROQ_API_KEY=<your Groq key>
```

Then:

```bash
npx expo start --clear      # scan the QR code with Expo Go (same Wi-Fi), or add --tunnel
```

> ⏳ The free Render server sleeps after ~15 idle minutes and takes up to a minute to wake. Open
> `https://sahayak-ai-q5ee.onrender.com/health` in a browser first.
>
> Environment values are baked in when the app bundles, so **restart** `expo start` after editing `.env.local`.

**Just want to look around with no backend or keys?** Leave both `USE_MOCK` values as `true`. The app runs on a built-in fake backend (any phone/email and an 8+ character password signs in).

Register an account in the app, fill in or skip the "About you" form, then tap the mic.

### 2. Run the backend locally (optional)

Requires Python 3.13, Docker, and a Groq key.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then fill it in (see below)

docker compose up -d postgres redis                   # Postgres (+pgvector) and Redis
python -m database.migrate                            # create tables (safe to re-run)
python -m scripts.seed_sample_data                    # load the 9 eligibility rules (+ demo profiles)
python -m rag.folder_sync                             # load the PDFs in documents/ (needs EMBEDDING_API_KEY)

python -m uvicorn main:app --reload --reload-exclude .venv    # API on http://localhost:8000 (docs at /docs)
python main.py                                        # …or chat in the terminal with no phone
```

Minimum `.env`:

```
GROQ_API_KEY=<your Groq key>
JWT_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
ADMIN_API_KEY=<any random string>
ENABLE_DEBUG_ROUTES=true      # local only — must be false when deployed
EMBEDDING_API_KEY=<Gemini key, optional — keyword search is used without it>
```

To point the phone at your local backend, use your computer's LAN address, e.g.
`EXPO_PUBLIC_API_BASE_URL=http://192.168.1.20:8000` (start the backend with `--host 0.0.0.0` so the phone can reach it; release builds require HTTPS, so use a tunnel such as cloudflared/ngrok for those).

## Configuration reference

**Mobile app** (`sahayak-mobile/.env.local`)

| Variable | Meaning |
|---|---|
| `EXPO_PUBLIC_USE_MOCK_API` | `true` = built-in fake backend, `false` = real backend |
| `EXPO_PUBLIC_API_BASE_URL` | Backend root, no trailing slash (HTTPS for release builds) |
| `EXPO_PUBLIC_USE_MOCK_STT` | `true` = fake transcript, `false` = real Groq Whisper |
| `EXPO_PUBLIC_GROQ_API_KEY` | Groq key for speech-to-text (visible inside the built app — fine for a demo; see below) |

**Backend** (`backend/.env`): `DATABASE_URL`, `REDIS_URL`, `GROQ_API_KEY` (or several in `GROQ_API_KEYS`, used round-robin), `JWT_SECRET`, `ADMIN_API_KEY`, `EMBEDDING_API_KEY`, `AUTO_SETUP`, `ENABLE_DEBUG_ROUTES`. See `backend/.env.example`.

## Testing

```bash
# App
cd sahayak-mobile
npx tsc --noEmit && npx expo lint && npx expo-doctor

# Backend (needs Postgres, Redis and a Groq key; some tests call live Groq)
cd backend
python -m pytest -q          # 126 tests
```

Manual test cases for a real phone (login, voice loop, languages, failure recovery, devices) and the record of the automated runs are in [`docs/mobile_test_cases.md`](docs/mobile_test_cases.md).

## Deployment

The demo backend runs on **Render** (Docker) with **Supabase** (PostgreSQL + pgvector) and **Upstash** (Redis). Set `AUTO_SETUP=true` and `ENABLE_DEBUG_ROUTES=false` there, and the backend creates its tables, seeds missing rules and loads the PDFs by itself on start. Step-by-step instructions are at the top of [`to_do.md`](to_do.md).

## Security notes

- Never commit `.env` / `.env.local` (they are git-ignored). Only `.env.example` templates are tracked.
- Anything prefixed `EXPO_PUBLIC_` is readable by anyone holding the built app. The Groq key there is acceptable for a class demo only; for a public release, route speech-to-text through the backend's existing `POST /api/v1/transcribe`.
- Debug routes expose all users' data; keep `ENABLE_DEBUG_ROUTES=false` on any deployed server.

## Known limitations

- Replies take about 6–15 s on the free cloud tier (a database connection pool is the planned fix); the server sleeps when idle.
- The Hindi verdict wording is not yet independently checked (English is).
- No password reset, account deletion or registration rate limit yet.
- Scanned (image-only) PDFs are not supported; rules are hand-written, not generated from PDFs.
- Hindi and English only. Tested on iPhone with Expo Go; Android not yet verified.

Full lists are in [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md#16-known-limitations-and-future-work) and `to_do.md`.

## Disclaimer

Sahayak AI is a college project. Its rules and documents are sample content. Answers are **guidance, not a bank's decision** — a bank always makes the final call. Never share a PIN, OTP, password or card number with any app, including this one.

## Documentation index

| Document | Contents |
|---|---|
| [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) | The whole project explained simply |
| [`docs/banking_voice_agent_architecture.md`](docs/banking_voice_agent_architecture.md) | Detailed design, status, known issues, roadmap |
| [`docs/mobile_client_implementation.md`](docs/mobile_client_implementation.md) | How the mobile app is built |
| [`docs/mobile_test_cases.md`](docs/mobile_test_cases.md) | Manual test cases and automated test record |
| [`docs/mobile_voice_client_plan.md`](docs/mobile_voice_client_plan.md) | Original plan for the app |
| [`backend/WORKING.md`](backend/WORKING.md) | Backend day-to-day guide |
| [`connect.md`](connect.md) | Connecting app ↔ backend |
| [`to_do.md`](to_do.md) | What's left |
