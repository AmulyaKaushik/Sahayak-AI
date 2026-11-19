# Sahayak AI — Mobile Voice Client: Implementation Report

**Component:** Mobile voice client (`sahayak-mobile/`)
**Companion docs:** [`banking_voice_agent_architecture.md`](banking_voice_agent_architecture.md) (backend, owned by teammate) · [`mobile_voice_client_plan.md`](mobile_voice_client_plan.md) (original plan for this client)
**Status:** Phases A–E implemented and tested on a physical iPhone via Expo Go. Phase G (UI/UX polish) implemented. **Phase F (real backend) implemented (2026-11-19):** login/register with JWT, secure token storage, route guards, onboarding and profile screens, and the real chat contract against the deployed backend (`https://sahayak-ai-q5ee.onrender.com`). The API layer is verified against the live server; on-device testing of Phase F is pending. Speech-to-text deliberately stays in the app (Groq directly), not the backend's `/transcribe`.

---

## 1. Purpose and Scope

The mobile client is the customer-facing voice front end of Sahayak AI. It lets a user **speak** a banking question in Hindi or English, turns the speech into text, sends that text to the Sahayak backend, and **reads the backend's reply aloud**, while showing the conversation as a chat transcript.

The client deliberately keeps a **text-in / text-out contract** with the backend:

| Responsibility | Where it lives |
|---|---|
| Microphone recording, speech-to-text (STT), text-to-speech (TTS), chat UI | **Mobile client (this document)** |
| Intent routing, worker agents, eligibility engine, session/profile stores, RAG | **Backend** (see architecture doc) |

The backend never handles audio, and the client never decides eligibility. This matches the architecture's core rule that *only the deterministic eligibility engine decides eligibility* (architecture doc §2).

> **Coordination note for the backend team:** Architecture doc §3 describes a backend "Voice / Input Layer (LangID → STT → NLU)". With STT and TTS done on the client, the backend receives **already-transcribed text plus a language tag**. The backend's input layer can therefore start at NLU; it does not need its own STT.

---

## 2. End-to-End Flow

```
 [User taps mic]
        │
        ▼
 expo-audio records a mono .m4a clip (with live level metering)
        │
        ├── silent clip? ──▶ "I didn't hear anything" (nothing uploaded)
        ▼
 Groq Whisper API (whisper-large-v3) ──▶ transcript + detected language (BCP-47)
        │
        ├── no real words (e.g. only ".")? ──▶ "I couldn't make out any words"
        ▼
 POST /api/v1/sessions/{id}/messages  { text, language }     (session created lazily)
        │
        ▼
 Backend reply { reply_text, language, eligible?, missing_fields?, session_state? }
        │
        ▼
 expo-speech reads reply_text aloud in the reply's language (on-device voice)
        │
        ▼
 Chat transcript updated; return to idle
```

### 2.1 Conversation state machine

The pipeline is modelled as an explicit state machine (not a set of loose booleans), as recommended in the plan. The mic button's look and the status text are both derived from it.

```
idle ─▶ recording ─▶ transcribing ─▶ sending ─▶ waiting ─▶ speaking ─▶ idle
                          │              │          │           │
                          └──────────────┴──── error ◀──────────┘ (TTS problems are
                                             │                     shown as a notice,
                                    Retry resumes the failed step   not an error)
```

| State | Meaning | Mic button |
|---|---|---|
| `idle` | Ready | Blue, mic icon |
| `recording` | Microphone is capturing | Red, stop icon, pulsing ring |
| `transcribing` | Audio uploaded to Whisper | Violet, spinning arc |
| `sending` | Opening the session / posting the message | Amber, spinning arc |
| `waiting` | Request sent, no reply yet after 0.8 s | Amber, hourglass, typing dots in chat |
| `speaking` | Reply being read aloud | Green, speaker icon, pulsing ring; tap to interrupt |
| `error` | A step failed | Red with shake; error card with **Retry** / **Dismiss** |

**Retry is step-aware:** if STT failed, the same audio clip is re-uploaded; if the backend call failed, the same transcript is re-sent without transcribing again.

---

## 3. Technology Stack

| Concern | Choice | Version | Notes |
|---|---|---|---|
| Framework | Expo (managed workflow) + React Native, TypeScript | Expo SDK 57, RN 0.86, React 19.2 | Runs in Expo Go; no native project files are committed |
| Navigation | `expo-router` (file-based) | 57.x | Two screens: Home, Settings |
| Recording / playback | `expo-audio` | 57.0.5 | `expo-av` is deprecated and was deliberately not used |
| Speech-to-text | Groq-hosted OpenAI Whisper (`whisper-large-v3`) | REST API | Free tier; OpenAI-compatible endpoint |
| Text-to-speech | `expo-speech` | 57.0.3 | Uses the phone's built-in voices; offline, free |
| Networking | `axios` | 1.20 | |
| State management | `zustand` | 5.0 | Three small stores |
| Persistence | `@react-native-async-storage/async-storage` | SDK-matched | Saves the language preference |
| Connectivity | `@react-native-community/netinfo` | SDK-matched | Offline banner |
| Icons | `@expo/vector-icons` (Ionicons) | SDK-matched | |

**Why Groq instead of OpenAI's Whisper API:** Groq serves the same open Whisper model family (and a newer version, large-v3, than OpenAI's `whisper-1`) through an OpenAI-compatible endpoint with a free tier (at the time of writing: 20 requests/min, 2,000 requests/day, 8 hours of audio/day). The switch changed only the URL, the key, and the model name. Bhashini (the provider named in the architecture doc) remains a possible later swap; see §9.

---

## 4. Project Structure

```
sahayak-mobile/
├── app.json                    Expo config (mic permission text, audio plugin options)
├── .env.example                Template for configuration (committed)
├── .env.local                  Real values incl. API key (git-ignored)
└── src/
    ├── app/                    Screens (expo-router: every file is a route)
    │   ├── _layout.tsx         Stack + route guards (Stack.Protected), restores login, connectivity monitor
    │   ├── (auth)/             Signed-out screens (group: not part of the URL)
    │   │   ├── _layout.tsx
    │   │   ├── login.tsx       /login
    │   │   └── register.tsx    /register
    │   ├── onboarding.tsx      First-login profile form (Save or Skip)
    │   ├── index.tsx           Home: chat transcript + mic button
    │   ├── profile.tsx         "My details": view / edit the saved profile
    │   └── settings.tsx        Account, language picker, connection status, dev info
    ├── components/
    │   ├── auth-form.tsx       Login / register form (shared)
    │   ├── profile-form.tsx    Form generated from GET /profile/schema (shared)
    │   ├── mic-button.tsx      Animated 7-state mic button
    │   ├── message-bubble.tsx  Chat bubble (+ scheme verdicts, "Needs" chips, sources) and typing indicator
    │   ├── notice-card.tsx     Inline error / warning card with actions
    │   └── offline-banner.tsx  Offline / can't reach server / waking up strip
    ├── config/env.ts           The only place that reads environment variables
    ├── constants/colors.ts     Colour palette
    ├── hooks/
    │   └── use-voice-recorder.ts   Mic permission, record/stop, level analysis, playback
    ├── services/
    │   ├── api.ts              Backend API client: the ONLY file that knows the contract (+ JWT refresh)
    │   ├── api-mock.ts         Mock backend with the same contract (incl. login/profile)
    │   ├── token-store.ts      Access/refresh tokens in expo-secure-store (Keychain / Keystore)
    │   ├── stt.ts              Speech-to-text (Groq Whisper + mock)
    │   └── tts.ts              Text-to-speech (voice selection, speak/stop)
    ├── utils/labels.ts         snake_case ids → readable labels
    └── store/
        ├── auth.ts             signedOut / signedIn, login/register/logout/restore
        ├── conversation.ts     Messages, session, pipeline state machine, retry
        ├── connectivity.ts     Device online? Backend healthy? (+ monitor hook)
        └── settings.ts         Persisted user preferences (spoken language)
```

**Layering rule:** screens → stores → services. Screens never call axios or Expo audio/speech APIs directly. Each external dependency (backend, STT provider, TTS engine) sits behind exactly one service module, so it can be replaced in one place.

---

## 5. Backend API Contract (as implemented by the client)

The contract is `connect.md` §9, served by `backend/` and deployed on Render. Only `src/services/api.ts` knows it.

### 5.1 Endpoints used

All routes except `/auth/*` and `/health` need `Authorization: Bearer <access_token>`. Errors look like `{"error": {"code", "message"}, "detail": message}`.

| Method + path | Request | Response | Used by |
|---|---|---|---|
| `GET /health` | – | `{status}` | Offline banner; first call also wakes the free server |
| `POST /auth/register` | `{login_id, password}` | `{access_token, refresh_token, customer_id, profile_completed}` | Register screen |
| `POST /auth/login` | same | same | Login screen |
| `POST /auth/refresh` | `{refresh_token}` | same (refresh token is rotated) | Automatic, on any 401 |
| `GET /api/v1/profile/schema` | – | `[{field, label, type, options, required}]` | Onboarding + profile form |
| `GET /api/v1/me/profile` | – | `{fields, profile_completed}` | Profile screen, launch check |
| `PATCH /api/v1/me/profile` | changed fields only (`null` clears) | `{fields, profile_completed}` | Save; `{}` = Skip |
| `POST /api/v1/sessions` | – | `{session_id}` | First message of a conversation |
| `POST /api/v1/sessions/{id}/messages` | `{text, language}` | `{reply_text, display_text, language, results[], facts_updated[], sources[], turn_type, eligible, missing_fields}` | Every voice turn |

### 5.2 Client behaviour

| Topic | Client behaviour |
|---|---|
| **Identity** | `customer_id` comes only from the JWT; the app never sends it. |
| **Tokens** | Stored in `expo-secure-store`, never AsyncStorage. Access tokens last 30 min. On a 401 the client refreshes **once** (concurrent 401s share one refresh, because the server rotates refresh tokens) and replays the request. If the refresh token itself is rejected, the user is signed out. A network error during refresh does *not* sign the user out. |
| **Launch** | Saved tokens → straight to the signed-in screens (works offline / while the server sleeps). In the background, `GET /me/profile` re-syncs `profile_completed`. |
| **Routing** | Signed out → login/register. Signed in + profile not completed → onboarding. Otherwise chat, profile, settings. Enforced by `Stack.Protected` in `_layout.tsx`. |
| **Sessions** | Server-issued, created lazily on the first message. On a 403 (expired after 24 h, or not this user's), a new session is created and the message re-sent once. Logout and "Start new conversation" discard it. |
| **Replies** | `display_text` is shown; `reply_text` (shorter, voice-friendly) is spoken. `results[]` → per-scheme ✓/✗ chips (first 3), `results[].ask` → "Needs: …" chips, `sources[]` → "Source: doc (p. n)". |
| **Timeouts / cold start** | 60 s per request. Render's free tier sleeps after ~15 idle minutes and takes 30–60 s to wake: the banner says "Waking up…" if the first health check is slow, the status line says the server may be waking up after 12 s without a reply, and the login button shows the same hint after 5 s. |
| **Logout** | Clears tokens, messages and session id, so the next person on the phone sees nothing of the previous chat. A reply that arrives after logout/reset is dropped. |
| **Errors** | The backend's `error.message` is shown (e.g. "Incorrect phone/email or password"); 5xx and timeouts get friendly generic text. |

### 5.3 Language tags

BCP-47 with region (`hi-IN`, `en-IN`, …). The reply's `language` picks the TTS voice.

---

## 6. Module Details

### 6.1 Recording: `hooks/use-voice-recorder.ts`
- **Permissions** are handled explicitly as four states: `undetermined`, `granted`, `denied` (can ask again), and `blocked` (the OS will not show the prompt again). The UI shows a matching message, including a button that opens the phone's Settings when blocked.
- **Format:** `RecordingPresets.HIGH_QUALITY` in mono (`.m4a`/AAC on both platforms). `LOW_QUALITY` was rejected because on Android it produces `.3gp`, which Whisper does not accept.
- **iOS audio session:** recording mode is switched on only while recording and switched off afterwards. While it is on, iOS routes playback to the quiet earpiece instead of the loudspeaker, a problem that only appears on real devices.
- **Silence detection:** metering reports the input level in dBFS every 100 ms. The first and last 300 ms are ignored (the button tap makes a loud click there). A clip counts as speech only if at least 3 readings (~300 ms) exceed −30 dB. If the phone reports no readings at all, the clip is not blocked. Each clip's peak, median and loud-sample count are logged in development to tune these constants.

### 6.2 Speech-to-text: `services/stt.ts`
- Uploads the clip as `multipart/form-data` to Groq's `/openai/v1/audio/transcriptions` with `model=whisper-large-v3` and `response_format=verbose_json`.
- **Language:** if the user picked Hindi or English in Settings, it is sent as a hint (`language=hi`), which improves accuracy for short or code-mixed sentences. Otherwise Whisper auto-detects. The detected language (a name such as "hindi" or a code such as "hi") is mapped to BCP-47. If the provider gives no language, it is inferred from the script (Devanagari → `hi-IN`, otherwise `en-IN`).
- **Hallucination guard:** Whisper invents text such as "Hello!" or "Thank you." for silence. Segments meeting Whisper's own silence rule (`no_speech_prob > 0.6` and `avg_logprob < −1`) are dropped. Transcripts containing only punctuation are rejected by the store.
- **Errors** are converted to user-readable messages (timeout, no connection, 401 bad key, 429 rate limit, other).
- A **mock** (`EXPO_PUBLIC_USE_MOCK_STT=true`) returns a fixed sentence after 1 s, so the app runs without a key.

### 6.3 Backend client: `services/api.ts`, `services/api-mock.ts`, `services/token-store.ts`
- `api.ts` holds the paths, request/response types, the axios instance (base URL, 60 s timeout), the auth interceptors (attach token; refresh-and-retry on 401) and error translation into `ApiError` (readable `message` + HTTP `status`). It exports `register`, `login`, `createSession`, `sendMessage`, `checkHealth`, `getProfile`, `updateProfile`, `getProfileSchema`.
- `api-mock.ts` implements the same interface with a 0.8 s delay, including login (any id, password ≥ 8; `wrong-password` simulates a 401) and an in-memory profile. Loan questions get a "not eligible yet, needs income and age" reply with `results[]`. The switch is `EXPO_PUBLIC_USE_MOCK_API`.
- `token-store.ts` keeps the tokens (and non-secret account info: customer id, login id, profile-completed flag) in `expo-secure-store`, which is included in Expo Go.

### 6.3a Auth: `store/auth.ts`, `app/(auth)/*`, `components/auth-form.tsx`
`status` is `loading` → `signedOut` | `signedIn`. `login`/`register` save the tokens, clear any previous chat and flip the status; the route guard does the navigation. The API client calls back into the store (via `setAuthLostHandler`, avoiding a circular import) when the refresh token is rejected.

### 6.3b Profile: `app/onboarding.tsx`, `app/profile.tsx`, `components/profile-form.tsx`
The form is generated from `GET /profile/schema`: numbers and text → text inputs, booleans → Yes/No, selects → chips (tap again to clear), multiselects without options → comma-separated text. Only changed fields are sent. Onboarding's "Skip for now" sends `PATCH {}`, which marks the profile completed. The profile screen reloads whenever it comes into view, so facts the chatbot saved ("my income is 25000") show up there.

### 6.4 Conversation store: `store/conversation.ts`
Holds the messages, session ID, pipeline status, current error, the pending step for Retry, which message is being spoken, and any TTS notice. All pipeline logic (transcribe → send → speak) lives here rather than in a screen, so it is independent of the UI.

### 6.5 Text-to-speech: `services/tts.ts`
- Picks the best installed voice for the reply language: an exact match (`hi-IN`) first, then any voice for the base language (`hi-*`), preferring "Enhanced" quality.
- Always stops current speech before speaking; `expo-speech` would otherwise queue it.
- If the phone has no voice for the language, the user sees a notice explaining how to install one.
- A token counter prevents a late "finished" callback from an older utterance from changing the state of a newer one.

### 6.6 Connectivity: `store/connectivity.ts` and `components/offline-banner.tsx`
Combines the phone's network state (NetInfo) with the backend `/health` check. The banner shows "You're offline…" or "Can't reach the Sahayak server"; tapping it re-checks immediately.

### 6.7 Settings: `store/settings.ts` and `app/settings.tsx`
- **"I will speak in": Auto / हिंदी / English**, saved on the device and restored between launches.
- Connection status with a "Check again" button, the session ID, a "Start new conversation" button, and which services are mocked.

---

## 7. Configuration

All configuration lives in `sahayak-mobile/.env.local` (git-ignored). `.env.example` is the committed template.

| Variable | Default | Meaning |
|---|---|---|
| `EXPO_PUBLIC_USE_MOCK_STT` | `true` | `false` = real Groq Whisper |
| `EXPO_PUBLIC_GROQ_API_KEY` | (empty) | Free key from console.groq.com/keys |
| `EXPO_PUBLIC_USE_MOCK_API` | `true` | `false` = real backend |
| `EXPO_PUBLIC_API_BASE_URL` | (empty) | `https://sahayak-ai-q5ee.onrender.com` (deployed), no trailing slash. Must be HTTPS for release builds. |

Expo copies `EXPO_PUBLIC_*` values into the app bundle at build time, so the dev server must be restarted after changes (`npx expo start --clear`).

> **Security note:** Because of this, the Groq key is extractable from any built copy of the app. That is acceptable for a class demo with a free-tier key, but for production the STT call should be proxied through the backend so the key never ships in the app (see §9).

---

## 8. Running the App

```bash
cd sahayak-mobile
npm install
cp .env.example .env.local        # then fill in the values
npx expo start                    # scan the QR code with Expo Go (same Wi-Fi)
npx expo start --tunnel           # if the network blocks device-to-laptop traffic
```

Quality checks (run before every commit):

```bash
npx tsc --noEmit      # typecheck
npx expo lint         # lint
npx expo-doctor       # dependency / config health
```

---

## 9. Testing Summary

All testing so far was done on a **physical iPhone via Expo Go**. Microphone, audio routing and TTS voices do not behave reliably in simulators.

| Area | Test | Result |
|---|---|---|
| Skeleton | App loads from QR code; Home ↔ Settings navigation; Fast Refresh | ✅ |
| Recording | Permission prompt, allow/deny/blocked paths; record → playback at speaker volume; silent-switch playback | ✅ |
| STT (Groq) | English sentence → correct text, `en-IN` | ✅ |
| STT (Groq) | Pure Hindi sentence → correct Devanagari text, `hi-IN` | ✅ |
| STT (Groq) | Code-mixed Hinglish ("मैं Home Loan के लिए अप्लाई करना चाहता हूँ") → correct, `hi-IN` | ✅ |
| STT errors | Airplane mode → "Could not reach…" → Retry succeeds without re-recording | ✅ |
| Hallucination | Silence produced "Hello!", "Thank you.", "." | ⚠️ "." is now rejected; the level-based silence detection is being re-tuned in Phase G |
| Mock backend | Loan intent (English and Hindi) → reply in the same language with `missing_fields` | ✅ |
| Mock backend | Unrelated sentence → echo reply; session ID reused; `/health` → ok | ✅ |
| TTS | English and Hindi replies spoken in the correct voice, loudspeaker, silent switch on | ✅ |
| TTS | Interrupt by tapping the mic; tap a reply to replay | ✅ |
| Phase G | Animated mic states, typing indicator, error cards, offline banner, language picker | ⏳ Device test pending |

**Phase F (real backend), automated:** the app's own `api.ts` + `token-store.ts` were bundled for Node (secure-store replaced by an in-memory map) and run against the deployed Render backend: register, duplicate register (409), wrong password (401), login, profile schema, invalid profile value (422), profile PATCH, session + message (reply in ~12 s, `facts_updated: ["monthly_income"]` and the fact visible in `GET /me/profile`), foreign session (403), expired access token → single refresh + replay for two parallel calls, revoked refresh token → signed out. **15/15 passed.** The app also bundles for iOS and Android (`npx expo export`).

**Still to test:** Phase F on a real phone (see the checklist in the app README), an Android device (TTS voice availability and mic behaviour differ between platforms), end-to-end latency measurement, and the full loop against the real backend.

---

## 10. Known Limitations and Future Work

1. **Password reset** does not exist (backend has no SMS/email provider), so a forgotten password means a new account.
2. **API key in the app.** STT intentionally still calls Groq from the phone (team decision). For anything beyond the demo, switch `services/stt.ts` to the backend's existing `POST /api/v1/transcribe` and remove `EXPO_PUBLIC_GROQ_API_KEY`.
3. **Silence detection thresholds** are device-dependent and are being tuned from real measurements.
4. **TTS voice availability** depends on the phone. Some Android phones need the Google TTS Hindi voice data installed. The app detects a missing voice and tells the user.
5. **Offline STT.** The architecture calls for an offline voice path (§2, principle 5). On-device recognition (`expo-speech-recognition` or `whisper.rn`) needs a custom development build rather than Expo Go and is left as a stretch goal. TTS is already fully on-device.
6. **Provider alignment.** The architecture doc names Bhashini for Indian-language STT. Swapping providers affects only `services/stt.ts`.
7. **Whisper language labelling.** Whisper sometimes labels spoken Hindi as Urdu. This was not observed in testing so far. If it happens, the Settings language picker (Hindi) forces the correct language.
