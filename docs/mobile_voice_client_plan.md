# Sahayak AI — Mobile Voice Client (My Part)

**Scope:** This document covers only the piece you own — the mobile app. Your teammate owns everything in `banking_voice_agent_architecture.md` (supervisor, worker agents, eligibility engine, DB, RAG). This doc treats that file as the frozen source of truth for what the backend *is*, and defines the client that talks to it.

**Note on the earlier docs:** the multi-bank "agentic marketplace" (A2A, Bank A/B devices) discussion from before is superseded — `banking_voice_agent_architecture.md` is explicitly the frozen final architecture (single kiosk-style backend, Supervisor + MCP workers, no A2A). Everything below assumes that doc, not the marketplace one.

---

## 1. Is Your Approach Right? (Analysis)

**React Native + Expo — good choice.** For a first mobile app with a hard deadline, Expo removes almost all the native-build pain (no Xcode/Android Studio wrangling to get *something* running), gives you `expo-speech` for text-to-speech for free, and lets you test instantly on your own phone via the Expo Go app or a QR code. Don't second-guess this choice.

**Client-side STT + TTS, text-only API to backend — good choice, and better than it might seem.** Three reasons this is actually the *right* split, not just the easy one:

1. It keeps the contract with your teammate dead simple: `text in → text out`. They never have to touch audio, you never have to touch the eligibility engine.
2. It matches a real design principle already in the parent doc (Section 4.10 / 4.8): voice providers are supposed to be swappable and there's meant to be an offline-capable "floor" for voice. If voice lives entirely in your app, you're free to swap STT/TTS providers or add an on-device fallback later without ever touching the backend.
3. It avoids putting STT/TTS API keys inside backend request paths that were designed for text.

**One thing to fix in your plan, and one thing to flag with your teammate:**

- **Fix:** "Expo Go" (the sandbox app you install from the Play/App Store) can only run officially-supported Expo modules. True on-device speech recognition (e.g. `expo-speech-recognition`, which wraps iOS's `SFSpeechRecognizer` and Android's `SpeechRecognizer`) needs a **custom dev client** (built with `expo-dev-client` + EAS Build) — it will not run inside plain Expo Go. This isn't a big deal, but it means "record audio → send it to a cloud Speech-to-Text API" is the realistic MVP path, not on-device recognition, unless you deliberately build a dev client later. Text-to-speech via `expo-speech` *does* work fine in plain Expo Go — no issue there.
- **Flag with your teammate:** `banking_voice_agent_architecture.md` Section 3 and Phase 9 describe a `LangID → STT → NLU` **Voice/Input Layer as backend work**. If you're doing STT/TTS entirely in the app, that backend phase either becomes unnecessary or needs to be redefined as just "accept already-transcribed text, detect language from the text itself if needed." Get this agreed explicitly so nobody builds it twice or waits on the other person unnecessarily.

**Recommendation for the MVP:** record audio with `expo-audio`, send it to a cloud speech-to-text API (OpenAI Whisper API is the simplest single-key option and handles Hindi/Hinglish reasonably well; swap for Bhashini later if you want to match the backend's stated provider), and speak the reply with `expo-speech` (on-device, free, no extra API key). Treat true on-device STT as a stretch goal, not a blocker.

---

## 2. Mobile App Architecture

```
 [Mic button pressed]
        │
        ▼
 expo-audio: record → local audio file (.m4a)
        │
        ▼
 Upload audio → Cloud STT API (e.g. Whisper) ──▶ transcribed text + detected language
        │
        ▼
 POST to Backend Chat API  { session_id, text, language }
        │
        ▼
 Backend (teammate's Supervisor/Worker pipeline) ──▶ { reply_text, language, ...metadata }
        │
        ▼
 expo-speech: speak(reply_text, language) ──▶ played out loud
        │
        ▼
 UI: append both messages to the transcript, return to idle
```

State machine for the mic button / conversation screen:

```
idle → recording → transcribing → sending → waiting_for_reply → speaking → idle
                                                     │
                                                     └─(any step fails)→ error → idle (with retry)
```

Keep this state machine explicit in code (a simple enum + reducer/zustand store) rather than a pile of booleans — you'll thank yourself when adding loading spinners and error banners.

---

## 3. API Contract — Propose This, Then Confirm With Your Teammate

Nothing in the shared architecture doc pins down actual REST routes for a chat turn, so **you need to agree this with your teammate before hardcoding it.** Here's a clean proposal to bring to that conversation:

```
POST /api/v1/sessions
  → { "session_id": "uuid" }                # call once when the app opens/resumes

POST /api/v1/sessions/{session_id}/messages
  body:  { "text": "...", "language": "hi-IN" }
  reply: {
    "reply_text": "...",
    "language": "hi-IN",
    "eligible": true,               # optional, present when a scheme/loan was evaluated
    "missing_fields": [],           # optional
    "session_state": "..."          # optional, for debugging
  }

GET /api/v1/health
  → { "status": "ok" }              # useful for your own "backend unreachable" banner
```

Design your API client (Section 5 below) around **constants for these paths and the base URL**, so when the real contract comes back slightly different, you change one file, not every screen.

**While waiting on the real backend:** don't block on it. Stand up a 10-line mock (a local JSON server, or literally a `setTimeout` that echoes back `"You said: " + text"`) behind a `USE_MOCK_API` flag, and build your whole app against that first.

---

## 4. Tech Stack

| Piece | Choice | Why |
|---|---|---|
| Framework | Expo (managed workflow), TypeScript template | Fastest path to a running app, type safety catches mistakes early |
| Audio recording/playback | `expo-audio` | Current supported module — `expo-av` is deprecated and being removed; don't start a new project on it |
| Speech-to-text | Cloud API call (e.g. OpenAI Whisper) from the audio file | Works inside plain Expo Go, good multilingual/Hinglish accuracy |
| Text-to-speech | `expo-speech` | Built into Expo, works offline, no extra API key, decent Hindi voice support on most modern phones |
| Networking | `fetch` or `axios` | Either is fine; `axios` gives nicer error handling for a beginner |
| State management | Zustand | Much less boilerplate than Redux for a project this size |
| Navigation | `expo-router` | File-based routing, the current Expo-recommended default |
| Config/env | `EXPO_PUBLIC_*` env vars (native Expo support) | Swap backend URL between dev/mock/prod without code changes |
| Styling | Plain `StyleSheet` (or NativeWind if you want Tailwind-style classes) | Keep it simple; visuals aren't graded here, reliability is |

Install once the project exists:
```
npx create-expo-app sahayak-mobile --template default@latest
cd sahayak-mobile
npx expo install expo-audio expo-speech expo-router expo-constants
npm install axios zustand
```

---

## 5. Screens & UX States

1. **Language / Onboarding screen** — pick preferred spoken language (Hindi / English / auto-detect). Store in Zustand + persist locally.
2. **Main conversation screen** — the core screen:
   - Large mic button, visually distinct states for idle / recording / thinking / speaking.
   - Scrolling transcript: user turns and assistant turns as chat bubbles.
   - A subtle status line ("Listening…", "Thinking…", "Speaking…").
   - Error banner with a "Retry" button if any step fails (network, STT, or backend).
3. **Settings screen** (dev-only, can be hidden/removed before final demo) — toggle mock vs. real backend URL, playback speed, clear session.
4. **Offline banner** — if `GET /health` fails or a request times out, show a persistent small banner rather than crashing or silently failing.

---

## 6. Phased Build Plan (Your Part Only)

Go in this order — each phase produces something you can actually show, and each phase de-risks the next one.

### Phase A — Project Skeleton (few days)
- `create-expo-app`, get it running via Expo Go on your **physical phone** (not just a simulator — you need a real mic).
- Basic `expo-router` navigation between a Home screen and a Settings screen.
- **Done when:** app opens on your phone from a QR code scan.

### Phase B — Record & Playback (learn the audio API)
- Add a mic button that records a short clip with `expo-audio` and plays it back immediately.
- Handle mic permission requests explicitly (don't assume the OS grants it silently).
- **Done when:** you can record your own voice and hear it played back on the same screen.

### Phase C — Speech-to-Text
- Send the recorded clip to a cloud STT API, display the returned transcript as text on screen.
- Test with a Hindi/Hinglish sentence, not just English — this is where you'll find real accuracy issues early.
- **Done when:** speaking a mixed Hindi-English sentence shows a reasonably correct transcript.

### Phase D — Mock Backend Integration
- Stand up the `USE_MOCK_API` stub from Section 3. Wire the transcript from Phase C into a POST call, display whatever comes back.
- Build your API client module now, with the contract from Section 3 as constants.
- **Done when:** speak → transcript → (mock) reply text appears, all in one flow.

### Phase E — Text-to-Speech
- Feed the (mock) reply text into `expo-speech`, have it read aloud.
- Test Hindi voice output specifically — voice availability varies by phone/OS, so check on the actual device you'll demo with.
- **Done when:** the full loop — speak, see transcript, see reply, hear reply — works end to end against the mock.

### Phase F — Real Backend Integration
- Swap the mock for your teammate's actual endpoint once it exists. This is why Section 3's contract conversation matters — do it early, not at this phase.
- Add session creation/reuse (`POST /sessions` on app open).
- **Done when:** the same full loop works against the real backend, not the mock.

### Phase G — UI/UX Polish
- Chat-bubble transcript styling, mic button animation (pulsing while recording), loading states for each stage of the pipeline.
- Language picker actually changes STT language hint and TTS voice.
- **Done when:** a stranger could pick up the phone and use it without you explaining anything.

### Phase H — Resilience (stretch, but valuable for your report)
- Retry logic for transient network failures.
- Graceful "backend unreachable" state using the `/health` check.
- *Optional stretch:* explore `expo-speech-recognition` with a real dev client (EAS build) for a true on-device fallback — this directly supports the parent architecture's offline-first story, and is a good "future work" or bonus demo if time allows.
- **Done when:** turning on airplane mode mid-conversation shows a clean error state instead of a frozen UI.

### Phase I — Device Testing & Demo Rehearsal
- Test on both an Android and iOS device if you can borrow one — TTS voice availability and mic behavior differ meaningfully between them.
- Rehearse the actual demo script (including a deliberately induced failure, if your team wants to show resilience live, matching the parent doc's Phase 14 demo philosophy).

---

## 7. Gotchas Specific to This Stack

- **Simulators often can't test the mic properly** (especially iOS Simulator) — budget time to test on a real device early, not the week of the demo.
- **`expo-av` is deprecated and being removed** — if any tutorial or Stack Overflow answer you find uses it, mentally translate to `expo-audio`.
- **Hindi TTS voice availability is device-dependent.** Some Android phones need the Hindi Google TTS voice pack downloaded separately. Check this on your actual demo device well before presentation day.
- **`expo-speech-recognition`-style native STT packages need a dev client**, not Expo Go — don't discover this the night before the demo.
- **Never hardcode API keys for cloud STT in the shipped app** if you can avoid it — for a class demo it's low-risk, but if you want to do this properly, route the STT call through your own backend teammate's API instead of calling the cloud STT provider directly from the phone (worth a quick conversation with them if time allows).

---

## 8. Testing Checklist

- [ ] Record → playback round-trip works on a real device
- [ ] STT returns a sane transcript for a pure-Hindi sentence
- [ ] STT returns a sane transcript for a code-switched Hindi-English sentence
- [ ] Mock backend round trip works end-to-end
- [ ] Real backend round trip works end-to-end
- [ ] TTS actually speaks Hindi output audibly on the demo device
- [ ] Killing the network mid-flow shows an error state, not a crash
- [ ] Full loop timed — know your actual end-to-end latency before demo day

---

## 9. Claude Code Prompt

Paste this as your first message to Claude Code in a fresh project folder. It's written to work through the phases above one at a time and pause for your review rather than build everything at once.

```
I'm building the mobile client for a college major project called "Sahayak AI" — a
multilingual, voice-first banking assistant. My teammate is building the backend
(a Python/FastAPI service with a Supervisor + worker-agent pipeline, a deterministic
eligibility engine, Postgres/Redis, etc. — I am NOT touching any of that).

MY PART ONLY: a React Native + Expo mobile app that:
1. Records the user's voice
2. Converts it to text (speech-to-text)
3. Sends the text to my teammate's backend over a REST API
4. Receives a text reply from the backend
5. Converts that reply to speech and plays it out loud
6. Shows a simple chat-style transcript UI while this happens

Constraints and decisions already made (please follow these, don't re-litigate them):
- Expo managed workflow, TypeScript template, expo-router for navigation.
- Use `expo-audio` for recording/playback — NOT `expo-av` (it's deprecated and being
  removed from Expo SDK).
- Use `expo-speech` for text-to-speech (on-device, no API key needed).
- For speech-to-text, call a cloud STT API (assume OpenAI's Whisper API for now —
  I'll swap providers later if needed) by uploading the recorded audio file.
- The backend is NOT ready yet. Build against a mock API first, behind a
  `USE_MOCK_API` flag/env var, with this exact planned contract (may change slightly
  later, so keep it isolated in one API-client module):
    POST /api/v1/sessions -> { session_id }
    POST /api/v1/sessions/{session_id}/messages
      body: { text, language }
      reply: { reply_text, language, eligible?, missing_fields?, session_state? }
    GET /api/v1/health -> { status }
- State management: Zustand (not Redux).
- Networking: axios.
- I have never built a mobile app before — explain any non-obvious Expo/React Native
  concept briefly as you introduce it, and call out anything that will only show up
  correctly on a real physical device (not a simulator), such as microphone behavior.

WORK IN THIS ORDER, and after each phase, stop and tell me what to test on my own
phone before you continue to the next phase:

Phase A — Project skeleton: create-expo-app with TypeScript + expo-router, two
  screens (Home, Settings), confirm it runs via Expo Go on my phone.

Phase B — Recording: mic button using expo-audio that records a clip and plays it
  back immediately on the same screen. Handle mic permissions explicitly.

Phase C — Speech-to-text: send the recorded clip to a (stubbed, then real) Whisper
  API call, display the transcript. Use an environment variable for the API key,
  never hardcode it.

Phase D — Mock backend integration: build the API client module against the mock
  contract above, wire the transcript into a POST call, display the mock reply.

Phase E — Text-to-speech: speak the reply text aloud using expo-speech, with a
  language parameter driven by the language returned from the backend.

Phase F — Leave a clearly marked TODO and a short README section explaining exactly
  what to change when the real backend URL and contract are ready (I'll do this
  step myself once my teammate's API exists).

Phase G — UI polish: chat-bubble transcript, animated mic button states
  (idle/recording/transcribing/sending/waiting/speaking/error), loading and error
  states for every network call.

Start with Phase A now. Ask me before assuming anything not specified above.
```
