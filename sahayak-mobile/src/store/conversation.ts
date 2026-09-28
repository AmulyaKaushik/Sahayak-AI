import { create } from 'zustand';

import type { FinishedRecording } from '@/hooks/use-voice-recorder';
import { createSession, sendMessage, SendMessageResponse } from '@/services/api';
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
  text: string;
  language: string;
  createdAt: number; // ms since epoch
  // Extra backend fields on assistant replies (eligible, missing_fields, ...).
  meta?: Omit<SendMessageResponse, 'reply_text' | 'language'>;
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

// What to redo when the user taps Retry.
type PendingStep =
  | { step: 'transcribe'; uri: string }
  | { step: 'send'; text: string; language: string };

type ConversationState = {
  messages: ChatMessage[];
  sessionId: string | null;
  status: PipelineStatus;
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
};

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

export const useConversation = create<ConversationState>()((set, get) => {
  function fail(error: unknown, pending: PendingStep | null) {
    set({
      status: 'error',
      error: error instanceof Error ? error.message : String(error),
      pending,
    });
  }

  async function runTranscribe(uri: string) {
    set({ status: 'transcribing', error: null, pending: null });
    const { spokenLanguage } = useSettings.getState();
    let transcript;
    try {
      transcript = await transcribe(uri, spokenLanguage === 'auto' ? undefined : spokenLanguage);
    } catch (e) {
      return fail(e, { step: 'transcribe', uri });
    }
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
    set({ status: 'sending', error: null, pending: null });
    const waitingTimer = setTimeout(() => {
      if (get().status === 'sending') set({ status: 'waiting' });
    }, WAITING_AFTER_MS);
    let reply: ChatMessage;
    try {
      // Sessions are created lazily on the first message and then reused.
      let sessionId = get().sessionId;
      if (!sessionId) {
        sessionId = (await createSession()).session_id;
        set({ sessionId });
      }
      const { reply_text, language: replyLanguage, ...meta } = await sendMessage(sessionId, {
        text,
        language,
      });
      reply = {
        id: newId(),
        role: 'assistant',
        text: reply_text,
        language: replyLanguage,
        createdAt: Date.now(),
        meta,
      };
    } catch (e) {
      // Let the offline banner find out whether the backend itself is down.
      useConnectivity.getState().checkBackend();
      return fail(e, { step: 'send', text, language });
    } finally {
      clearTimeout(waitingTimer);
    }
    set((s) => ({ messages: [...s.messages, reply] }));
    await speakReply(reply);
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

    await tts.speak(message.text, message.language, (error) => {
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
    status: 'idle',
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

    resetConversation: () => {
      speechToken++;
      tts.stopSpeaking();
      set({
        messages: [],
        sessionId: null,
        status: 'idle',
        error: null,
        pending: null,
        speakingId: null,
        ttsNotice: null,
      });
    },
  };
});
