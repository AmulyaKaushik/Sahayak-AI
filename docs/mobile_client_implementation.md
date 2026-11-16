# Sahayak AI — Mobile Voice Client: Implementation Report

**Component:** Mobile voice client (`sahayak-mobile/`)
**Companion docs:** [`banking_voice_agent_architecture.md`](banking_voice_agent_architecture.md) (backend, owned by teammate) · [`mobile_voice_client_plan.md`](mobile_voice_client_plan.md) (original plan for this client)
**Status:** Phases A–E implemented and tested on a physical iPhone via Expo Go. Phase G (UI/UX polish) implemented; device testing in progress. Phase F (real-backend switch-over) deferred until the backend API is available.

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
    │   ├── _layout.tsx         Stack navigator, header, starts connectivity monitor
    │   ├── index.tsx           Home: chat transcript + mic button
    │   └── settings.tsx        Language picker, connection status, dev info
    ├── components/
    │   ├── mic-button.tsx      Animated 7-state mic button
    │   ├── message-bubble.tsx  Chat bubble (+ eligibility chips) and typing indicator
    │   ├── notice-card.tsx     Inline error / warning card with actions
    │   └── offline-banner.tsx  "You're offline" / "Can't reach server" strip
    ├── config/env.ts           The only place that reads environment variables
    ├── constants/colors.ts     Colour palette
    ├── hooks/
    │   └── use-voice-recorder.ts   Mic permission, record/stop, level analysis, playback
    ├── services/
    │   ├── api.ts              Backend API client: the ONLY file that knows the contract
    │   ├── api-mock.ts         Mock backend with the same contract
    │   ├── stt.ts              Speech-to-text (Groq Whisper + mock)
    │   └── tts.ts              Text-to-speech (voice selection, speak/stop)
    └── store/
        ├── conversation.ts     Messages, session, pipeline state machine, retry
        ├── connectivity.ts     Device online? Backend healthy? (+ monitor hook)
        └── settings.ts         Persisted user preferences (spoken language)
```

**Layering rule:** screens → stores → services. Screens never call axios or Expo audio/speech APIs directly. Each external dependency (backend, STT provider, TTS engine) sits behind exactly one service module, so it can be replaced in one place.

---

## 5. Backend API Contract (as implemented by the client)

The client is built against this contract, currently served by the built-in mock. **Backend team: please confirm or send changes.** Only `src/services/api.ts` needs to change if it differs.

### 5.1 Endpoints

```
GET  /api/v1/health
  → 200 { "status": "ok" }

POST /api/v1/sessions
  (no body)
  → 200 { "session_id": "<string>" }

POST /api/v1/sessions/{session_id}/messages
  body:  { "text": "मुझे होम लोन के लिए अप्लाई करना है", "language": "hi-IN" }
  → 200 {
      "reply_text": "...",          // required: shown and spoken
      "language": "hi-IN",          // required: selects the TTS voice
      "eligible": true,             // optional: shown as an Eligible / Not eligible chip
      "missing_fields": ["age"],    // optional: shown as "Needs: Age" chips
      "session_state": "..."        // optional: kept but not displayed
    }
```

### 5.2 What the client assumes

| Topic | Client behaviour |
|---|---|
| **Language tags** | BCP-47 with region, e.g. `hi-IN`, `en-IN` (also `bn-IN`, `mr-IN`, `ta-IN`, `te-IN`, `gu-IN`, `kn-IN`, `ml-IN`, `pa-IN`, `ur-IN`). The reply's `language` picks the voice, so the backend should return the language it actually replied in. |
| **Sessions** | Created lazily on the first message, then reused for the whole conversation. "Start new conversation" in Settings discards it. |
| **Timeouts** | 20 s per backend request (Whisper: 30 s). |
| **Errors** | Any non-2xx is shown as "Server error (status)". If the body is FastAPI-style `{ "detail": "..." }` with a string, that text is appended. |
| **Health** | `/health` is called on app start, when the app returns to the foreground, after any failed message, and every 30 s while it is failing. It drives the offline banner. |
| **Field names** | `missing_fields` values are displayed after converting `snake_case` to words ("monthly_income" → "Monthly income"). |

### 5.3 Deployment note for the backend

A phone cannot reach `localhost` on a laptop. During development the backend must listen on the LAN (e.g. `uvicorn main:app --host 0.0.0.0 --port 8000`) and the client is pointed at `http://<laptop-LAN-IP>:8000`. CORS is not needed, because this is a native app, not a browser.

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

### 6.3 Backend client: `services/api.ts` and `services/api-mock.ts`
- `api.ts` holds the paths, request/response types, the axios instance (base URL, 20 s timeout) and error translation. It exports `createSession()`, `sendMessage()` and `checkHealth()`.
- `api-mock.ts` implements the same interface with a 0.8 s delay. It replies in the language it was spoken to. Messages about a loan get a reply asking for income and age with `missing_fields: ["monthly_income", "age"]`; anything else is echoed back. The switch is `EXPO_PUBLIC_USE_MOCK_API`.

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
| `EXPO_PUBLIC_API_BASE_URL` | (empty) | e.g. `http://192.168.1.20:8000`, with no trailing slash |

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

**Still to test:** an Android device (TTS voice availability and mic behaviour differ between platforms), end-to-end latency measurement, and the full loop against the real backend.

---

## 10. Known Limitations and Future Work

1. **Real backend integration (Phase F).** Blocked on the backend API. Expected work: set the two `API` env variables, reconcile any contract differences in `api.ts`, and handle an expired session (e.g. recreate it on a 404 and retry once).
2. **API key in the app.** Proxy STT through the backend for anything beyond the demo.
3. **Silence detection thresholds** are device-dependent and are being tuned from real measurements.
4. **TTS voice availability** depends on the phone. Some Android phones need the Google TTS Hindi voice data installed. The app detects a missing voice and tells the user.
5. **Offline STT.** The architecture calls for an offline voice path (§2, principle 5). On-device recognition (`expo-speech-recognition` or `whisper.rn`) needs a custom development build rather than Expo Go and is left as a stretch goal. TTS is already fully on-device.
6. **Provider alignment.** The architecture doc names Bhashini for Indian-language STT. Swapping providers affects only `services/stt.ts`.
7. **Whisper language labelling.** Whisper sometimes labels spoken Hindi as Urdu. This was not observed in testing so far. If it happens, the Settings language picker (Hindi) forces the correct language.
