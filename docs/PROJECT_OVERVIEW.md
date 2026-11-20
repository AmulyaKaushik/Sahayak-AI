# Sahayak AI — The Whole Project, Explained Simply

*Status as of 2026-11-20. Read this first. It explains what Sahayak AI is, how it works from the moment someone speaks to the moment they hear an answer, what every part of the code does, and what is still unfinished. No technical background is needed for sections 1–4; later sections get gradually more technical.*

---

## Contents

1. [What is Sahayak AI?](#1-what-is-sahayak-ai)
2. [A conversation, start to finish](#2-a-conversation-start-to-finish)
3. [The big picture](#3-the-big-picture)
4. [The golden rules (what makes it trustworthy)](#4-the-golden-rules-what-makes-it-trustworthy)
5. [The mobile app](#5-the-mobile-app)
6. [The backend (the "brain")](#6-the-backend-the-brain)
7. [The nine schemes and loans it knows](#7-the-nine-schemes-and-loans-it-knows)
8. [Where the data lives](#8-where-the-data-lives)
9. [Security and privacy](#9-security-and-privacy)
10. [What happens when something breaks](#10-what-happens-when-something-breaks)
11. [Where it runs (deployment)](#11-where-it-runs-deployment)
12. [Technology list](#12-technology-list)
13. [Folder map](#13-folder-map)
14. [How it was tested](#14-how-it-was-tested)
15. [How the project evolved](#15-how-the-project-evolved)
16. [Known limitations and future work](#16-known-limitations-and-future-work)
17. [Glossary](#17-glossary)
18. [Where to find more](#18-where-to-find-more)

---

## 1. What is Sahayak AI?

**Sahayak** (सहायक) means *helper* in Hindi.

Many people in rural India don't know which bank loans or government schemes they could get. Asking a bank clerk isn't always possible, and reading official documents is hard, especially in a language that isn't your own.

**Sahayak AI is a phone app you can talk to.** You ask, in Hindi or English, things like:

- *"Am I eligible for a Kisan Credit Card?"*
- *"Which government schemes can I get?"*
- *"What is the minimum age for Sukanya Samriddhi?"*

It listens, works out the answer, and **speaks the answer back** while also showing it on screen.

It does two kinds of work:

| Kind of question | What Sahayak does | Example |
|---|---|---|
| **"Do I qualify?"** (eligibility) | Looks at the facts you've told it (age, income, job…) and checks them against fixed rules. Asks for anything missing. | "Am I eligible for a home loan?" |
| **"What does the document say?"** | Searches the official scheme PDFs and answers from them, naming the document and page. | "What is the minimum age for Sukanya Samriddhi?" |

### The most important promise

> **The "yes, you are eligible / no, you are not" answer is never decided by an AI's opinion.**

AI models can sound confident and be wrong. In banking, a wrong "yes" or "no" is serious. So Sahayak uses AI only to *understand* what you said and to *phrase* the reply. The actual verdict comes from plain, fixed rules that a human wrote down and that give the same answer every time.

This is a college major project built by two people: one built the **mobile app** (the part you talk to) and the other built the **backend** (the "brain" in the cloud).

---

## 2. A conversation, start to finish

Here is one real exchange, and what happens behind the scenes.

**You tap the mic and say (in Hindi):** *"क्या मुझे किसान क्रेडिट कार्ड मिल सकता है?"* ("Can I get a Kisan Credit Card?")

| Step | Where | What happens |
|---|---|---|
| 1 | Phone | The app records your voice. |
| 2 | Phone → Groq | The recording is sent to a speech-to-text service (Whisper, run by Groq). It returns the words as text and the language (Hindi). |
| 3 | Phone → Backend | The app sends the text to the Sahayak backend over the internet, with your login token. |
| 4 | Backend | **Safety check:** if the message contains a PIN, OTP, password or card number, it is refused immediately and nothing is stored. |
| 5 | Backend | **Router:** a small AI decides what kind of question this is → "eligibility, about the Kisan Credit Card". |
| 6 | Backend | **Eligibility agent:** pulls out any facts in your sentence, loads the facts it already knows about you (age 41, farmer…), saves new ones, then runs the **rules** for the Kisan Credit Card. |
| 7 | Backend | The rules say: *age OK, farmer OK, **land ownership unknown***. The verdict is "not yet, one thing missing". |
| 8 | Backend | **Refiner:** turns that into a short, friendly, speakable sentence in Hindi, and makes sure the numbers and the verdict weren't changed in translation. |
| 9 | Backend → Phone | The reply comes back: a short version to speak, a fuller version to show, and the details (which schemes, what's missing). |
| 10 | Phone | The app shows a reply bubble with a red ✗ chip ("Kisan credit card") and a yellow chip ("Needs: Land holding acres"), and **reads the reply aloud** in Hindi. |

**You say:** *"I own 2 acres of land."* Now the backend saves *land = 2 acres*, re-checks the scheme it was discussing, and answers *"You are eligible."* You didn't have to repeat anything.

Those facts are also saved to your profile, so tomorrow it still knows them.

---

## 3. The big picture

```
┌──────────────────────┐        HTTPS + login token         ┌──────────────────────────────┐
│     MOBILE APP       │ ─────────────────────────────────▶ │          BACKEND             │
│  (Expo / React       │                                    │   (Python / FastAPI, cloud)  │
│   Native)            │ ◀───────────────────────────────── │                              │
│                      │      reply text + details          │  ┌─────────┐   ┌──────────┐  │
│ • records your voice │                                    │  │ Router  │──▶│Eligibility│ │
│ • speech → text      │                                    │  └─────────┘   │  agent    │ │
│ • shows chat         │                                    │       │        └────┬──────┘ │
│ • speaks the reply   │                                    │       │        ┌────▼──────┐ │
│ • login, profile     │                                    │       └───────▶│ Rules     │ │
└──────────┬───────────┘                                    │       ┌───────▶│ engine    │ │
           │ audio                                          │  ┌────┴────┐   └───────────┘ │
           ▼                                                │  │ RAG     │  ┌───────────┐  │
   ┌───────────────┐                                        │  │ agent   │  │ Refiner   │  │
   │ Groq Whisper  │                                        │  └─────────┘  └───────────┘  │
   │ (speech→text) │                                        └──────┬───────────────┬───────┘
   └───────────────┘                                               │               │
                                                          ┌────────▼───┐    ┌──────▼──────┐
                                                          │ PostgreSQL │    │   Redis     │
                                                          │ users,     │    │ sessions,   │
                                                          │ profiles,  │    │ login       │
                                                          │ rules,     │    │ tokens,     │
                                                          │ documents  │    │ rate limits │
                                                          └────────────┘    └─────────────┘
```

**Three layers:**

1. **The app** — everything you see and hear. It does *not* make decisions.
2. **The backend** — understands the question, applies the rules, searches documents, writes the reply.
3. **The data stores** — a database for things that must last (users, facts about you, rules, documents) and a fast memory store for short-lived things (conversations, login tokens).

**Outside services used:**

| Service | Used for | Cost |
|---|---|---|
| **Groq** | Runs the AI language models (understanding, rephrasing, answering from documents) and Whisper speech-to-text | Free tier |
| **Google Gemini** | Turns text into numbers ("embeddings") so documents can be searched by meaning | Free tier, optional |
| **Supabase** | Hosts the PostgreSQL database | Free tier |
| **Upstash** | Hosts Redis | Free tier |
| **Render** | Runs the backend on the internet | Free tier |

---

## 4. The golden rules (what makes it trustworthy)

1. **Rules decide, AI doesn't.** Eligibility is calculated by a deterministic rules engine. Same facts in → same answer out, always. Each rule is a versioned record, so any decision can be traced to the exact rule version.
2. **Answers come from documents, or not at all.** When answering "what does the document say", the AI may only use passages that were found. If nothing relevant is found, it says so instead of inventing something.
3. **Never ask for or keep secrets.** PINs, OTPs, passwords, CVVs and card numbers are refused before any AI sees them and are never stored.
4. **Your data is yours.** Who you are comes only from your login token, never from what the app claims. One user can never read or use another user's chat or profile.
5. **Fail gently.** If the AI service is down, simple eligibility checks still work. If document search by meaning is down, it falls back to keyword search. A failure is reported as "I'm having trouble looking that up", never as a wrong answer or a silent "not found".
6. **One thing at a time.** Every part has one job and talks to the others through a small, fixed interface. The router doesn't peek inside the eligibility agent; the app never talks to the database.

---

## 5. The mobile app

Folder: `sahayak-mobile/`. Built with **Expo / React Native**, which means one codebase for iPhone and Android, tested through the **Expo Go** app. Currently Expo **SDK 58**.

### 5.1 What you see

| Screen | What it does |
|---|---|
| **Login / Register** | Sign in with a phone number or email + a password (8+ characters). The app never asks for your bank PIN, and says so. |
| **Onboarding ("About you")** | Shown once after registering: age, income, job type, and so on. Everything is optional; **Skip for now** works. |
| **Chat (home)** | The main screen: a big mic button, the conversation as chat bubbles, and a status line ("Listening… / Understanding… / Sahayak is thinking… / Speaking…"). |
| **My details** | See and edit your saved profile. Anything you told the chatbot by voice shows up here too. |
| **Settings** | Language choice (Auto / हिंदी / English), connection status, sign out, start a new conversation. |

### 5.2 What the mic button shows

The button changes colour and animation for each stage: **idle** (blue) → **recording** (red, pulsing) → **transcribing** (purple, spinning) → **sending / waiting** (orange, spinning) → **speaking** (green, pulsing). If anything fails it shakes and shows a red error card with **Retry**.

### 5.3 What a reply bubble shows

- The reply text.
- A **✓ or ✗ chip per scheme** (first three, then "+N more").
- **"Needs: …" chips** for facts Sahayak still wants from you.
- A **"Source: document (page)"** line for document answers.
- Tap a reply to hear it again. Tap the mic during speech to interrupt it.

### 5.4 Behaviour worth knowing

- **Languages:** Hindi and English only. Speech-to-text sometimes mislabels Hindi as Urdu; the app detects this and re-asks with Hindi forced.
- **Speak vs show:** the spoken reply is short; the on-screen reply can be longer.
- **Staying signed in:** login tokens are kept in the phone's secure storage (Keychain on iPhone, Keystore on Android). Close and reopen the app and you're still in.
- **The chat is remembered** on the phone (last 100 messages) and **belongs to your account**. Signing out, or signing in as someone else, clears it.
- **Expired logins fix themselves:** a login lasts 30 minutes, then the app quietly gets a new one. If that fails (for example after 30 days), you're sent to the login screen.
- **Expired conversations fix themselves:** conversation sessions last 24 hours; if one expires the app opens a new one and re-sends your message.
- **The free server sleeps.** After ~15 idle minutes it takes up to a minute to wake. The app shows *"Waking up the Sahayak server…"* instead of an error.
- **Offline banner:** a red strip appears when the phone is offline or the server can't be reached; tapping it re-checks.
- **Demo mode:** with `EXPO_PUBLIC_USE_MOCK_API=true`, the app runs against a built-in fake backend (fake login, profile and replies), so it can be demonstrated with no internet.

### 5.5 How the app's code is organised

```
screens  →  stores  →  services
```

- **Screens** (`src/app/`) show things and react to taps. They contain no network code.
- **Stores** (`src/store/`, using Zustand) hold the app's state and the logic: `auth` (who is signed in), `conversation` (messages and the speak→send→reply pipeline), `settings`, `connectivity`.
- **Services** (`src/services/`) each talk to *one* outside thing: `api.ts` (the backend; the only file that knows its URLs), `stt.ts` (speech-to-text), `tts.ts` (text-to-speech), `token-store.ts` (secure storage).

Because each outside thing is behind one file, swapping a provider later means editing one file.

---

## 6. The backend (the "brain")

Folder: `backend/`. Written in **Python** with **FastAPI**.

### 6.1 The API (what the app can ask for)

| Route | Purpose |
|---|---|
| `POST /auth/register`, `/auth/login`, `/auth/refresh` | Create an account, sign in, get a fresh token |
| `GET /api/v1/me/profile`, `PATCH /api/v1/me/profile` | Read / update your saved details |
| `GET /api/v1/profile/schema` | The list of profile questions (so the app's form builds itself) |
| `POST /api/v1/sessions` | Start a conversation (the server issues and owns the id) |
| `POST /api/v1/sessions/{id}/messages` | **Send a message, get the reply** — the main route |
| `POST /api/v1/transcribe` | Speech-to-text through the server (built, but the app calls Groq directly for now) |
| `GET /health` | "Is the server awake?" |
| `/api/v1/admin/documents*` | Staff-only: upload/list/sync policy PDFs (needs a secret admin key) |

### 6.2 Sahayak_AI: the coordinator (`sahayak_ai/`)

A thin layer with three jobs and no business logic of its own:

1. **Router** (`router.py`) — a small, fast AI reads your message and splits it into 1–3 sub-tasks, each marked *eligibility* or *document question*. It rewrites each as a standalone question (so "why only till then?" becomes a full question), decides whether you asked something or merely stated a fact, and works out which scheme "this loan" refers to. If the AI fails, a simple keyword method takes over.
2. **Orchestrator** (`orchestrator.py`) — runs the sub-tasks (at the same time where safe), guards against forbidden secrets, and catches crashes so you never see a raw error.
3. **Refiner** (`refiner.py`) — makes the answer short and speakable: "Rs 25,000" → "25,000 rupees", no bullet points, plain scheme names, **one** clear thing to ask next. For Hindi it translates, then checks that no number changed. Long multi-scheme results are summarised ("You're eligible for A and B; close on C, which needs X").

### 6.3 The eligibility agent (`eligibility_agent/`, `supervisor/`, `eligibility_engine/`)

1. **Extract facts** from your original message ("I am a 29 year old farmer" → age 29, job farmer). An AI does this, with plain pattern matching as a backup.
2. **Save** new facts against your account (history is kept).
3. **Run the rules engine** — the deterministic heart (`eligibility_engine/`). Rules are data (e.g. "age ≥ 18 AND age ≤ 75"), including AND/OR groups. For each scheme it returns *eligible or not*, *which requirements are met*, and *which are missing*.
4. **Build the reply** from the result with templates (not free-form AI), so the verdict is guaranteed.

If it's missing a fact, it asks for it. When you then give the fact, it automatically re-checks the scheme you were discussing.

### 6.4 The document agent / RAG (`rag/`)

"RAG" means *Retrieval-Augmented Generation*: **find the relevant passages first, then answer only from them.**

- **Loading documents:** PDFs are placed in `backend/documents/` (a folder per scheme). A sync step extracts the text page by page, **classifies** each as a loan or a scheme document, **chunks** it into passages (~500–800 words, keeping page numbers), turns each chunk into an **embedding** (a list of numbers capturing its meaning, via Gemini), and stores them in the database. Currently **10 PDFs** are loaded.
- **Answering:** the question is also turned into numbers; the database finds the passages with the closest meaning; only if they're similar enough does an AI write an answer **using only those passages**. Otherwise: "I couldn't find that".
- **If embeddings are unavailable**, it searches by keywords instead.
- Scanned (image-only) PDFs aren't supported yet — they'd need OCR.

### 6.5 Speech (`speech/`)

`POST /api/v1/transcribe` forwards audio to Groq Whisper using a key kept on the server, so the key never has to live in the app. *(Today the app still calls Groq directly, by the team's decision; switching is a small change in `stt.ts`.)*

### 6.6 Keys and limits (`workers/keys.py`)

Groq's free tier allows ~8,000 tokens per minute per model. The backend rotates between several Groq keys (`GROQ_API_KEYS`) to get more room.

### 6.7 Terminal mode

`python main.py` lets you chat with the brain in a terminal with no phone, which is handy for development.

---

## 7. The nine schemes and loans it knows

These are the rules baked into the engine. (The numbers come from `eligibility_engine/rules_seed.py`; every rule has a version and an approver.)

| Scheme / loan | You're eligible if… |
|---|---|
| **Sukanya Samriddhi Yojana** (girl-child savings) | You have a girl child under 10, and you are 18+ |
| **PM Jan Dhan Yojana** (basic bank account) | You're 10+, and you don't already have a Jan Dhan account |
| **PMAY Rural Housing Subsidy** | Monthly income ≤ ₹25,000, you don't own a pucca (permanent) house, and it's your first home purchase |
| **Kisan Credit Card** | You're a farmer, own some land, and are aged 18–75 |
| **Retail Micro Loan** | Salaried or self-employed, income ≥ ₹15,000/month, aged 21–60, at most 6 dependents |
| **Senior Citizen Savings Scheme** | You're 60 or older |
| **PM Mudra Yojana (Shishu)** | Self-employed, aged 18–65, with a business plan |
| **Home Loan** | Salaried or self-employed, income ≥ ₹30,000/month, aged 21–65, property papers ready |
| **Atal Pension Yojana** | Aged 18–40, not a government employee, no existing Atal Pension account |

Each has a policy PDF in `backend/documents/` for the "what does the document say" questions.

> **Note:** these rules are sample/demo rules for a college project. For real use, they must be checked against current official documents.

---

## 8. Where the data lives

**PostgreSQL** (permanent):

| Data | Details |
|---|---|
| Customers (login) | A unique id, phone/email, a **hashed** password (never the password itself), whether onboarding is done |
| Customer profiles | Core details (age, income, dependents, job type, products you hold, language) with **version history** |
| Extra facts | Anything else you've told it (land held, girl child under 10, business plan…), per customer |
| Eligibility rules | The nine rules above, versioned |
| Documents and chunks | The PDFs' text split into passages with their embeddings (stored with the `pgvector` extension; loans and schemes in separate tables so they can't be mixed up) |

**Redis** (short-lived and fast):

| Data | Details |
|---|---|
| Session owner | Which customer a conversation belongs to (24 hours) |
| Session context | What's been discussed (the active scheme, earlier results) |
| Refresh tokens | Only the most recent one per user is valid |
| Login attempt counters | For rate limiting |

**On the phone:**

| Data | Where |
|---|---|
| Login tokens | Secure storage (Keychain / Keystore) |
| Chat history (last 100 messages), language choice | Ordinary app storage on the phone |

---

## 9. Security and privacy

| Protection | How |
|---|---|
| Passwords | Hashed with salted **scrypt** (a deliberately slow, memory-hungry method) — never stored or logged in plain text |
| Login | Short-lived **access token** (30 min) + longer **refresh token** (30 days, rotated each use) |
| Identity | The user id comes only from the signed token — the app cannot claim to be someone else |
| Conversation ownership | Each session is tied to its owner; another user gets **403 Forbidden** |
| Brute force | Max 5 wrong logins per minute per account, then **429** |
| Secrets in chat | PIN/OTP/CVV/password/card numbers refused before any AI sees them; never stored |
| Profile input | Validated: ages must be whole numbers 0–120, choices must be valid options, etc. |
| Secrets in code | API keys live in `.env` files that are git-ignored; the repo contains only `.env.example` templates |
| Admin routes | Need a secret admin key; debug routes that expose all data are switched off in the cloud |
| Transport | Everything goes over HTTPS |

Known gaps (see §16): anyone can register (no rate limit on that yet), no password reset, no account deletion, chat history on the phone is not encrypted, and the Groq key is currently inside the app bundle.

---

## 10. What happens when something breaks

| Problem | What the user sees / what happens |
|---|---|
| No internet | Red banner; Retry button on the failed step |
| Server asleep | "Waking up the Sahayak server…"; request waits up to 60 s |
| Login expired | Silently renewed; only if impossible, back to the login screen |
| Conversation expired | A new one is opened and the message re-sent |
| You said nothing | "I didn't hear anything…" — nothing is sent |
| Noise only | "I couldn't make out any words" |
| Speech-to-text fails | Error with Retry that re-sends the same recording |
| AI service down (backend) | Eligibility still answered from simple pattern-matching + cached rules |
| Embedding service down | Documents searched by keyword |
| Document lookup fails | "I'm having trouble looking that up" (never a false "not found") |
| No Hindi voice on the phone | A notice explaining how to install one |
| You sign out while a reply is on its way | The late reply is discarded so the next person never sees it |

---

## 11. Where it runs (deployment)

| Piece | Where | Notes |
|---|---|---|
| Backend | **Render** (Docker, free tier) | `https://sahayak-ai-q5ee.onrender.com`; sleeps after ~15 idle minutes (first request then takes 30–60 s) |
| Database | **Supabase** (PostgreSQL + pgvector) | Use the *Session pooler* connection string (Render has no IPv6) |
| Redis | **Upstash** | `rediss://` (TLS) URL |
| AI models | **Groq** | Free tier; several keys supported |
| Embeddings | **Google Gemini** | Optional; keyword search is the fallback |
| App | **Expo Go** on a phone (or an EAS build) | Must reach the backend over HTTPS |

With `AUTO_SETUP=true` the backend, on every start, creates/updates the database tables, adds any missing rules, and loads any new PDFs.

Typical reply time: **1–3 seconds locally, 6–15 seconds on the free cloud** (every database call opens a fresh connection; a connection pool is the planned fix) — plus occasional extra waits from Groq's free-tier limit.

---

## 12. Technology list

**Mobile app:** Expo SDK 58 · React Native 0.88 · React 19 · TypeScript · Expo Router (screens and navigation) · Zustand (state) · Axios (networking) · `expo-audio` (recording) · `expo-speech` (text-to-speech) · `expo-secure-store` (tokens) · AsyncStorage (preferences, chat) · NetInfo (connectivity).

**Backend:** Python 3.13 · FastAPI + Uvicorn · Pydantic · DSPy (structured AI calls) · Groq models (`gpt-oss-120b` main, `gpt-oss-20b` fast) · PostgreSQL 16 + pgvector · Redis 7 · PyJWT (login tokens) · pypdf (PDF text) · Docker.

**Speech:** Groq-hosted Whisper `large-v3` (speech-to-text) · the phone's built-in voices (text-to-speech).

---

## 13. Folder map

```
Sahayak-AI/
├── README.md                    Start here: quick-start
├── connect.md                   The plan for wiring the app to the backend
├── to_do.md                     What's left to do, in order
├── docs/
│   ├── PROJECT_OVERVIEW.md      This file
│   ├── banking_voice_agent_architecture.md   Detailed design, status, known issues
│   ├── mobile_voice_client_plan.md           Original plan for the app
│   ├── mobile_client_implementation.md       How the app was built
│   └── mobile_test_cases.md                  Manual test cases + automated test record
│
├── sahayak-mobile/              THE APP
│   ├── .env.example             Settings template (copy to .env.local)
│   └── src/
│       ├── app/                 Screens: (auth)/login, register · onboarding · index (chat) · profile · settings · +not-found
│       ├── components/          Mic button, chat bubble, forms, error cards, offline banner
│       ├── hooks/               Voice recorder
│       ├── services/            api, api-mock, stt, tts, token-store
│       ├── store/               auth, conversation, connectivity, settings
│       ├── utils/ , constants/ , config/
│
└── backend/                     THE BRAIN
    ├── main.py                  App entry point (also: terminal chat via `python main.py`)
    ├── settings.py              All configuration
    ├── sahayak_ai/              Router · orchestrator · refiner · chat API
    ├── eligibility_agent/       Wraps the eligibility pipeline
    ├── supervisor/              The pipeline itself: facts → rules → reply, session memory
    ├── eligibility_engine/      The deterministic rules engine + the nine rules
    ├── rag/                     Document ingestion, search and answering
    ├── workers/                 AI helper code: signatures, key rotation, guards, friendly names
    ├── speech/                  Speech-to-text proxy
    ├── security/                Register/login/refresh, tokens, sessions, rate limits, admin key
    ├── db_manager/              Profile storage and the profile API
    ├── database/                Connection, migrations (SQL files)
    ├── schemas/                 Data shapes, required-fields list, profile form schema
    ├── documents/               The 10 policy PDFs
    ├── scripts/                 Seed data, demo scripts
    ├── tests/                   126 automated tests
    ├── Dockerfile, docker-compose.yml, requirements.txt
    └── .env.example             Settings template
```

---

## 14. How it was tested

| What | Result |
|---|---|
| Backend automated tests (`pytest`) | **126 passing** (some call live Groq) |
| App ↔ live backend, main flow (register, login, profile, chat, refresh, session ownership) | 15 / 15 |
| App ↔ live backend, edge cases (validation, isolation between two users, Hindi, documents, PIN guard) | 35 / 35 |
| App logic with the phone-only parts faked (retries, expired session, late reply after logout, per-account chat) | 24 / 24 |
| Login rate limit on the live server | 5 wrong tries → 401, the 6th → 429 |
| Type-check, lint, `expo-doctor` (20 checks), iOS + Android bundle | All clean |
| Secrets scan | No API key in any tracked file |
| Real phone (iPhone, Expo Go) | Voice loop, login, onboarding, persistence, Hindi, scrolling — checked by hand |

The checklist for manual testing is in `docs/mobile_test_cases.md`.

---

## 15. How the project evolved

The project was first designed as a **branch kiosk** (a screen at a bank branch, using a card reader for identity). It became a **phone app** instead, which changed several things:

| Originally | Now | Why |
|---|---|---|
| Kiosk with card-reader identity | Phone app with phone/email + password login and tokens | A phone has no card reader |
| A "supervisor" with separate worker agents using MCP tool calls | A thin router → two agents → refiner pipeline calling the engine directly | Simpler and much faster (2 AI calls per turn instead of 5–7) |
| AI narrates each result | Replies built from templates around the rules result | Guarantees the verdict cannot be changed by the AI |
| Speech handled by the backend | Speech-to-text in the app (via Groq); text-to-speech on the phone | Keeps the backend text-only and simple |
| Anthropic models | Groq models | Free tier |

**Build order of the app (phases):** A skeleton → B recording → C speech-to-text → D mock backend → E text-to-speech → G polish (animations, offline banner, language picker) → **F real backend** (login, profile, real contract, SDK 58 upgrade, persistence, fixes).

---

## 16. Known limitations and future work

**Worth doing next**

- **Speed on the cloud:** add a database connection pool (replies take 6–15 s).
- **Hindi verdict check:** the refiner checks the eligible/not-eligible wording only for English replies; Hindi replies only have their numbers checked.
- **Free-tier limits:** Groq's per-minute token cap slows things when many people use it at once.
- **Keep the server awake** before a demo (it sleeps when idle).

**Not built yet**

- Password reset, account deletion/export, logout-everywhere.
- Rate limits on registration and chat (a public release needs these).
- Moving speech-to-text fully behind the backend (removes the Groq key from the app).
- A privacy policy and in-app consent (needed for a public release).
- OCR for scanned PDFs.
- Rules proposed automatically from PDFs with human approval (today rules are hand-written, so a PDF and a rule could disagree).
- On-device offline speech recognition.
- Languages beyond Hindi and English.
- A real EAS build with a proper app name, icon and bundle id (today it runs in Expo Go).

**Important honesty note:** the rules and PDFs are demo content for a college project. The answers are *guidance*, not a bank's decision.

---

## 17. Glossary

| Term | Meaning |
|---|---|
| **Agent** | A piece of code that handles one kind of task (here: eligibility, or document questions) |
| **API** | The list of requests an app can send to a server and the replies it gets |
| **Backend** | The program on a server that does the real work |
| **Deterministic** | Same input always gives the same output (no guessing) |
| **Embedding** | A list of numbers that represents the *meaning* of a piece of text, used for searching by meaning |
| **Eligibility** | Whether you meet the conditions for a loan or scheme |
| **Expo / Expo Go** | A toolkit and a phone app that make it easy to build and run React Native apps |
| **FastAPI** | The Python tool the backend is built with |
| **Groq** | A service that runs AI models quickly, with a free tier |
| **JWT** | A signed digital "pass" proving who you are, sent with each request |
| **LLM** | Large Language Model — the kind of AI that reads and writes text |
| **pgvector** | A PostgreSQL add-on that stores embeddings and finds the closest matches |
| **RAG** | Find relevant passages first, then answer only from them |
| **Redis** | A very fast, short-term memory database |
| **Refresh token** | A longer-lived pass used only to get a new short-lived one |
| **Router** | The part that decides which agent should handle your message |
| **Session** | One conversation. The server creates it and remembers who owns it |
| **STT / TTS** | Speech-to-text (voice → words) / Text-to-speech (words → voice) |
| **Whisper** | An AI model that turns speech into text |
| **Zustand** | A small library the app uses to keep track of its state |

---

## 18. Where to find more

| Question | Read |
|---|---|
| How do I run it? | `README.md` |
| Detailed design, status table, every known issue | `docs/banking_voice_agent_architecture.md` |
| How the backend works day to day | `backend/WORKING.md` |
| How the app was built, module by module | `docs/mobile_client_implementation.md` |
| How do I test it? | `docs/mobile_test_cases.md` |
| What's left to do? | `to_do.md` |
| How were app and backend wired together? | `connect.md` |
| Where do I add policy PDFs? | `backend/documents/README.md` |
