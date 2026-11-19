import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import type { FinishedRecording } from '@/hooks/use-voice-recorder';
import { ApiError, createSession, sendMessage, SendMessageResponse } from '@/services/api';
import { transcribe } from '@/services/stt';
import * as tts from '@/services/tts';
import { useConnectivity } from '@/store/connectivity';
import { useSettings } from '@/store/settings';

// Global conversation state (Zustand). Any component can read it with
// useConversation((s) => s.someField) and re-renders only when that field
// changes. Actions live in the store too, so the pipeline logic is not tied to
// any one screen.

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  // What is shown on screen (the backend's display_text for replies).
  text: string;
  // Assistant replies only: the shorter, voice-friendly reply_text that is
  // read aloud. Falls back to `text` when absent.
  speechText?: string;
  language: string;
  createdAt: number; // ms since epoch
  // Extra backend fields on assistant replies (results, sources, ...).
  meta?: Omit<SendMessageResponse, 'reply_text' | 'display_text' | 'language'>;
};

// Pipeline stage after the recording has stopped. (Recording itself is
// tracked by the useVoiceRecorder hook.) 'sending' covers opening the session
// and posting the message; if no reply has arrived after WAITING_AFTER_MS it
// becomes 'waiting' so the UI can say the backend is still working.
export type PipelineStatus =
  | 'idle'
  | 'transcribing'
  | 'sending'
  | 'waiting'
  | 'speaking'
  | 'error';

const WAITING_AFTER_MS = 800;
// The free server sleeps when idle and needs up to a minute to wake. After
// this long without a reply, `slow` is set so the UI can explain the wait.
const SLOW_AFTER_MS = 12_000;

// What to redo when the user taps Retry.
type PendingStep =
  | { step: 'transcribe'; uri: string }
  | { step: 'send'; text: string; language: string };

type ConversationState = {
  messages: ChatMessage[];
  sessionId: string | null;
  // customer_id of the account this chat belongs to. The chat is saved on the
  // phone between launches; this stops one account from ever seeing another's.
  ownerId: string | null;
  status: PipelineStatus;
  // true while a reply is taking unusually long (server waking up).
  slow: boolean;
  error: string | null;
  pending: PendingStep | null;
  // Which assistant message is being read aloud, if any.
  speakingId: string | null;
  // Non-blocking TTS problem, e.g. no Hindi voice installed.
  ttsNotice: string | null;

  processRecording: (recording: FinishedRecording) => Promise<void>;
  retry: () => Promise<void>;
  clearError: () => void;
  speakMessage: (id: string) => Promise<void>;
  stopSpeaking: () => Promise<void>;
  dismissTtsNotice: () => void;
  resetConversation: () => void;
  // Called after sign-in / on launch: keeps the saved chat only if it belongs
  // to this account, otherwise starts empty.
  claimFor: (customerId: string) => void;
};

// Only this many recent messages are kept on the phone.
const MAX_SAVED_MESSAGES = 100;

const LANGUAGE_NAMES: Record<string, string> = {
  hi: 'Hindi', en: 'English', bn: 'Bengali', mr: 'Marathi', ta: 'Tamil', te: 'Telugu',
  gu: 'Gujarati', kn: 'Kannada', ml: 'Malayalam', pa: 'Punjabi', ur: 'Urdu',
};

// Whisper sometimes returns only punctuation (".") for noise.
const hasWords = (text: string) => text.replace(/[\s.,!?;:'"()…।॥-]/g, '').length > 0;

let nextId = 0;
const newId = () => `${Date.now()}-${nextId++}`;
// Incremented on every speak/stop so a late callback from an older utterance
// can't flip the status of a newer one.
let speechToken = 0;
// Incremented by resetConversation (also called on logout). A reply that
// arrives after a reset belongs to the old conversation and is dropped.
let generation = 0;

export const useConversation = create<ConversationState>()(
  persist((set, get) => {
  function fail(error: unknown, pending: PendingStep | null) {
    set({
      status: 'error',
      error: error instanceof Error ? error.message : String(error),
      pending,
    });
  }

  async function runTranscribe(uri: string) {
    const gen = generation;
    set({ status: 'transcribing', error: null, pending: null });
    const { spokenLanguage } = useSettings.getState();
    let transcript;
    try {
      transcript = await transcribe(uri, spokenLanguage === 'auto' ? undefined : spokenLanguage);
    } catch (e) {
      if (gen !== generation) return;
      return fail(e, { step: 'transcribe', uri });
    }
    if (gen !== generation) return;
    if (!hasWords(transcript.text)) {
      return fail(new Error("I couldn't make out any words. Please try again."), null);
    }
    set((s) => ({
      messages: [
        ...s.messages,
        {
          id: newId(),
          role: 'user',
          text: transcript.text,
          language: transcript.language,
          createdAt: Date.now(),
        },
      ],
    }));
    await runSend(transcript.text, transcript.language);
  }

  async function runSend(text: string, language: string) {
    const gen = generation;
    set({ status: 'sending', slow: false, error: null, pending: null });
    const waitingTimer = setTimeout(() => {
      if (get().status === 'sending') set({ status: 'waiting' });
    }, WAITING_AFTER_MS);
    const slowTimer = setTimeout(() => {
      if (gen === generation) set({ slow: true });
    }, SLOW_AFTER_MS);
    let reply: ChatMessage;
    try {
      const response = await sendInSession(text, language, gen);
      const { reply_text, display_text, language: replyLanguage, ...meta } = response;
      reply = {
        id: newId(),
        role: 'assistant',
        text: display_text || reply_text,
        speechText: reply_text,
        language: replyLanguage,
        createdAt: Date.now(),
        meta,
      };
      useConnectivity.setState({ backendOk: true });
    } catch (e) {
      if (gen !== generation) return;
      // Let the offline banner find out whether the backend itself is down.
      useConnectivity.getState().checkBackend();
      return fail(e, { step: 'send', text, language });
    } finally {
      clearTimeout(waitingTimer);
      clearTimeout(slowTimer);
      if (gen === generation) set({ slow: false });
    }
    if (gen !== generation) return;
    set((s) => ({ messages: [...s.messages, reply] }));
    await speakReply(reply);
  }

  // Sessions are server-issued: created on the first message, then reused.
  // They expire after 24 h (and belong to one user), and the server answers
  // 403 for an expired/unknown one. In that case open a new session and send
  // the message again, once.
  async function sendInSession(text: string, language: string, gen: number) {
    let sessionId = get().sessionId;
    if (sessionId) {
      try {
        return await sendMessage(sessionId, { text, language });
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 403)) throw e;
        if (gen === generation) set({ sessionId: null });
      }
    }
    sessionId = (await createSession()).session_id;
    if (gen === generation) set({ sessionId });
    return sendMessage(sessionId, { text, language });
  }

  async function speakReply(message: ChatMessage) {
    const token = ++speechToken;
    set({ status: 'speaking', speakingId: message.id, ttsNotice: null });

    if ((await tts.hasVoiceFor(message.language)) === false) {
      const name = LANGUAGE_NAMES[message.language.split('-')[0]] ?? message.language;
      set({
        ttsNotice: `No ${name} voice is installed on this phone, so replies may sound wrong. Add one in the phone's text-to-speech / Spoken Content settings.`,
      });
    }

    await tts.speak(message.speechText ?? message.text, message.language, (error) => {
      if (token !== speechToken) return; // a newer utterance took over
      set({
        status: 'idle',
        speakingId: null,
        ...(error && { ttsNotice: `Could not read the reply aloud: ${error.message}` }),
      });
    });
  }

  return {
    messages: [],
    sessionId: null,
    ownerId: null,
    status: 'idle',
    slow: false,
    error: null,
    pending: null,
    speakingId: null,
    ttsNotice: null,

    async processRecording({ uri, isSilent }) {
      if (isSilent) {
        // Don't upload silence: Whisper would invent words for it.
        return fail(new Error("I didn't hear anything. Tap the mic and speak a little louder."), null);
      }
      await runTranscribe(uri);
    },

    async retry() {
      const pending = get().pending;
      if (!pending) return;
      if (pending.step === 'transcribe') await runTranscribe(pending.uri);
      else await runSend(pending.text, pending.language);
    },

    clearError: () => set({ status: 'idle', error: null, pending: null }),

    async speakMessage(id) {
      const message = get().messages.find((m) => m.id === id);
      if (message) await speakReply(message);
    },

    async stopSpeaking() {
      speechToken++;
      set({ speakingId: null, ...(get().status === 'speaking' && { status: 'idle' }) });
      await tts.stopSpeaking();
    },

    dismissTtsNotice: () => set({ ttsNotice: null }),

    claimFor: (customerId) => {
      if (get().ownerId === customerId) return;
      get().resetConversation();
      set({ ownerId: customerId });
    },

    resetConversation: () => {
      speechToken++;
      generation++;
      tts.stopSpeaking();
      set({
        messages: [],
        sessionId: null,
        ownerId: null,
        status: 'idle',
        slow: false,
        error: null,
        pending: null,
        speakingId: null,
        ttsNotice: null,
      });
    },
  };
},
    {
      name: 'sahayak-conversation',
      storage: createJSONStorage(() => AsyncStorage),
      // Save only the chat itself, not transient state (status, errors, ...).
      partialize: (s) => ({
        messages: s.messages.slice(-MAX_SAVED_MESSAGES),
        sessionId: s.sessionId,
        ownerId: s.ownerId,
      }),
    },
  ),
);

// Resolves once the saved chat has been read from the phone's storage.
export function whenConversationLoaded(): Promise<void> {
  if (useConversation.persist.hasHydrated()) return Promise.resolve();
  return new Promise((resolve) => {
    const off = useConversation.persist.onFinishHydration(() => {
      off();
      resolve();
    });
  });
}
