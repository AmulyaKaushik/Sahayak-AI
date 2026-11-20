# Sahayak AI — Mobile App Test Cases

Manual test cases for the phone, plus a record of the automated tests already run.
Backend: `https://sahayak-ai-q5ee.onrender.com`. Run on a real phone in Expo Go (SDK 58).

**Before you start:** open `<backend>/health` in a browser so the free server is awake (it sleeps after ~15 idle minutes).
Use a **new** phone number/email per run for registration tests (e.g. `98765` + 5 random digits).
Passwords must be 8+ characters.

Result column: ✅ pass · ❌ fail · ➖ not applicable. Write the actual result if it differs.

---

## 1. Registration and login

| ID | Steps | Expected | Result |
|---|---|---|---|
| A1 | Fresh app (signed out) | Login screen opens, no error page | |
| A2 | Tap "Create an account", register with a new number + 8-char password + matching confirm | Lands on the "About you" onboarding form | |
| A3 | Register with passwords that don't match | "The two passwords do not match." No request sent | |
| A4 | Register with a 5-char password | "Password must be at least 8 characters." | |
| A5 | Register with an empty phone/email | "Enter your phone number or email." | |
| A6 | Register with an already-used number | "An account with this phone/email already exists" | |
| A7 | Register the same number in different case/with spaces (email) | Treated as the same account → A6 message | |
| A8 | Sign in with the right credentials | Chat (or onboarding if not completed) | |
| A9 | Sign in with a wrong password | "Incorrect phone/email or password" (same text for an unknown user) | |
| A10 | Sign in 6 times within a minute with a wrong password | Attempts 1–5: "Incorrect phone/email or password". Attempt 6+: "Too many attempts. Please wait a minute and try again." (verified on the live server) | |
| A11 | Eye icon on the password field | Toggles show/hide | |
| A12 | First sign-in after the server slept | After ~5 s: "Waking up the Sahayak server…", then succeeds; no error | |
| A13 | Switch between Sign in ↔ Create account | Works both ways, no stacked screens | |
| A14 | Keyboard open on a small phone | Fields and button stay reachable (scroll) | |

## 2. Session persistence and sign out

| ID | Steps | Expected | Result |
|---|---|---|---|
| S1 | Sign in, chat once, force-quit, reopen | Straight to chat, **previous messages still there** | |
| S2 | Reopen with airplane mode on | Opens signed in (chat visible); offline banner shows | |
| S3 | Settings → Sign out → Cancel | Nothing happens | |
| S4 | Settings → Sign out → confirm | Login screen; reopening shows login (not chat) | |
| S5 | Sign out, sign in as a **different** account | Empty chat (no messages from account 1) | |
| S6 | Sign out, sign in as the **same** account | Empty chat (sign-out clears it) but profile values are still there | |
| S7 | Onboarding screen → "Sign out" in header | Back to login | |
| S8 | Start new conversation (Settings) | Chat cleared, session shows "(none yet)" | |
| S9 | Leave the app idle > 30 min, then ask a question | Works (token refreshes silently), no login screen | |

## 3. Onboarding and "My details"

| ID | Steps | Expected | Result |
|---|---|---|---|
| P1 | New account → "Skip for now" | Goes to chat; reopening does NOT show onboarding again | |
| P2 | New account → fill age 30, income 25000, employment "Salaried" → Save and continue | Goes to chat; My details shows those values | |
| P3 | Type letters in the age field | Keypad is numeric; if pasted, "Enter a number" error on that field | |
| P4 | Age 150 or a negative number | Server message shown (e.g. "age must be between 0 and 120") | |
| P5 | Tap a select chip twice (e.g. Salaried) | Second tap clears it | |
| P6 | Yes/No field: tap Yes, then Yes again | Clears back to unanswered | |
| P7 | "Existing products" (free list) type `savings account, debit card` | Saved as two items; shown the same way on reopen | |
| P8 | My details → change income → Save changes | "Saved." appears; reopening shows the new value | |
| P9 | Save with no changes | No error; nothing breaks | |
| P10 | Say "I am 35 years old" in chat → open My details | Age = 35 (chat facts appear in the form) | |
| P11 | Change a value in My details, then ask "Am I eligible for X?" | Answer uses the new value | |
| P12 | Onboarding with airplane mode on | Clear error with Retry, no crash | |
| P13 | Android: back button on onboarding | Does not escape into the login screen | |

## 4. Voice conversation (core loop)

| ID | Steps | Expected | Result |
|---|---|---|---|
| V1 | Tap mic, say "Am I eligible for a home loan?", tap stop | Transcript bubble (blue) → thinking → reply bubble → reply spoken | |
| V2 | Reply shows verdict chips | ✓/✗ chip per scheme (max 3, then "+N more"), "Needs: …" chips for missing fields | |
| V3 | Reply spoken text vs shown text | Spoken is short; shown may be longer — both make sense | |
| V4 | Tap an assistant bubble | Reply is read again | |
| V5 | Tap the mic while a reply is playing | Speech stops, recording starts | |
| V6 | Long reply (e.g. "Which schemes am I eligible for?") | Screen scrolls so **your question is visible at the top** and the reply starts below it | |
| V7 | Short reply | Screen scrolls to the bottom | |
| V8 | Record silence (don't speak) | "I didn't hear anything…", nothing sent | |
| V9 | Noisy room, mumbled speech | Either a sane transcript or "couldn't make out any words"; never a made-up "Thank you." sent | |
| V10 | Ask 5 questions in a row | Same session; context carries over ("what about for my daughter?") | |
| V11 | Header buttons (person, gear) | Both open their screens; header is opaque; nothing hidden under it | |
| V12 | Status line | Cycles: Listening → Understanding → Sending → thinking → Speaking | |
| V13 | Reply slower than ~12 s | Status says server may be waking up | |
| V14 | "Play my last recording" | Plays your last clip | |

## 5. Language

| ID | Steps | Expected | Result |
|---|---|---|---|
| L1 | Auto mode, say a Hindi sentence | Transcript in **Devanagari**, bubble tag `hi-IN` (never `ur-IN`) | |
| L2 | Auto mode, say an English sentence | `en-IN` | |
| L3 | Auto mode, Hinglish ("Mujhe home loan chahiye") | Sane transcript; `hi-IN` or `en-IN`; reply in a supported language | |
| L4 | Settings → हिंदी, speak Hindi | `hi-IN`; no extra delay | |
| L5 | Settings → English, speak Hindi | Transcribed as English letters (expected, forced); note result | |
| L6 | Hindi question → reply | Hindi reply, spoken with a Hindi voice | |
| L7 | Phone without a Hindi voice | Yellow notice explaining how to install one | |
| L8 | Hindi eligibility verdict vs English | Same verdict ("eligible"/"not eligible") for the same facts (backend item H1) | |
| L9 | Language setting survives restart | Still the same after force-quit | |

## 6. Eligibility, documents and safety (content)

Use a profile with age 41, income 25000, employment farmer, has girl child under 10 = Yes.

| ID | Say | Expected | Result |
|---|---|---|---|
| C1 | "Am I eligible for Kisan Credit Card?" | Verdict + what's missing (e.g. land) | |
| C2 | "I own 2 acres of land" then "Am I eligible for Kisan Credit Card?" | Fact saved (My details shows land); verdict updates | |
| C3 | "Which government schemes can I get?" | List of schemes (chips: first 3 + "+N more") | |
| C4 | "What is the minimum age for Sukanya Samriddhi?" | Answer from the document + "Source: … (p. N)" line | |
| C5 | A question the documents don't cover ("Who won the cricket match?") | Polite "I don't have that" style answer, no invented facts | |
| C6 | "My ATM PIN is 1234, can I get a loan?" | Refusal to take PIN/OTP/card; **PIN not shown back and not saved** | |
| C7 | A question with a verdict the opposite of what you expect | Verify by hand against the rules in `backend/` (eligibility is deterministic) | |
| C8 | Tell a fact that changes the answer ("I am 70 years old") | Verdict changes accordingly | |

## 7. Failure and recovery

| ID | Steps | Expected | Result |
|---|---|---|---|
| F1 | Airplane mode **before** speaking | Offline banner; speaking gives a clear error + Retry | |
| F2 | Airplane mode **while** waiting for a reply | Error card with Retry; turn network on → Retry works, no duplicate question bubble | |
| F3 | Airplane mode during transcription | Error → Retry re-sends the **same** recording | |
| F4 | Server asleep (wait 20 min, then ask) | "Waking up…" feedback; eventually answers or shows a Retry error | |
| F5 | Kill the app mid-reply, reopen | Opens signed in; no crash; chat as saved | |
| F6 | Dismiss an error | Card disappears, mic usable | |
| F7 | Deny microphone permission | Yellow notice; tapping mic asks again | |
| F8 | Block microphone in phone settings | Notice with "Open phone settings" button | |
| F9 | Receive a phone call / switch apps while recording | No crash; app recovers on return | |
| F10 | Backend down (stop it) | "Can't reach the Sahayak server. Tap to retry." banner; recovers when it's back | |
| F11 | Revoke login (sign in on a second phone, 30+ days, or change nothing) | Not testable quickly; covered by automated tests (see §9) | |
| F12 | Rotate screen / background and return mid-reply | Reply still shown/spoken once | |

## 8. Platform and device

| ID | Steps | Expected | Result |
|---|---|---|---|
| D1 | iPhone with silent switch on | Replies still audible | |
| D2 | Android phone | Whole loop works; Hindi voice present or the notice appears | |
| D3 | Small screen (e.g. iPhone SE) | Nothing cut off; mic button visible | |
| D4 | Dark mode | Text readable everywhere (note any white-on-white) | |
| D5 | Large system font size | Layout doesn't break | |
| D6 | Bluetooth headset connected | Audio routes sensibly | |
| D7 | Time a full turn on the cloud host | Record seconds: ______ (expected 5–15 s; >20 s = Groq limit or cold start) | |

## 9. Automated tests already run (2026-11-19)

These ran from a scratch folder (not part of the repo): the app's real `api.ts`, `token-store.ts`, `auth.ts`, `conversation.ts` and `stt.ts` code, bundled for Node, with only the phone-specific parts (secure storage, speech, microphone) replaced by in-memory fakes.

| Suite | What it covers | Result |
|---|---|---|
| Live API, happy path (against the deployed backend) | register, login, schema, profile PATCH, session, chat, 403 for a foreign session, expired access token → single refresh + retry (two parallel calls), revoked refresh → signed out | 15 / 15 |
| Live API, edge cases | validation (short id/password, 422 on bad profile values, empty/oversized message), case-insensitive ids, 401 without a token, **two-user isolation** (B cannot use A's session, B starts empty), Skip (`PATCH {}`), null clears a field, Hindi reply in Devanagari, document question returns sources, **PIN refused and not stored**, chat facts appear in the profile | 35 / 35 |
| App logic (fake API) | `display_text` shown / `reply_text` spoken; session reused; silence and punctuation-only rejected; STT retry; send retry without duplicating the question; **403 → new session and resend**; chat saved with owner; **different account clears chat**; **late reply after logout is dropped**; logout clears saved chat; refresh rejected → signed out; `restore()` re-syncs onboarding state | 24 / 24 |
| Static | `tsc --noEmit`, `expo lint`, `expo-doctor` (20/20), iOS + Android bundle export | all clean |
| Secrets scan | Groq key not present anywhere in tracked files | clean |

**Not covered by automation** (hence the manual cases above): real microphone and speech-to-text accuracy, TTS voices, screen layout and scrolling, navigation guards on a device, the Urdu→Hindi retry in `stt.ts` (needs Groq), password rate limiting (A10), and Android.
