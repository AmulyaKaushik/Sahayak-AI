import { create } from 'zustand';

import type { FinishedRecording } from '@/hooks/use-voice-recorder';
import { createSession, sendMessage, SendMessageResponse } from '@/services/api';
import { transcribe } from '@/services/stt';

// Global conversation state (Zustand). Any component can read it with
// useConversation((s) => s.someField) and re-renders only when that field
// changes. Actions live in the store too, so the pipeline logic is not tied to
// any one screen.

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  language: string;
  // Extra backend fields on assistant replies (eligible, missing_fields, ...).
  meta?: Omit<SendMessageResponse, 'reply_text' | 'language'>;
};

// Pipeline stage after the recording has stopped. (Recording itself is
// tracked by the useVoiceRecorder hook.) 'speaking' is added in Phase E.
export type PipelineStatus = 'idle' | 'transcribing' | 'sending' | 'error';

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

  processRecording: (recording: FinishedRecording) => Promise<void>;
  retry: () => Promise<void>;
  clearError: () => void;
  resetConversation: () => void;
};

let nextId = 0;
const newId = () => `${Date.now()}-${nextId++}`;

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
    let transcript;
    try {
      transcript = await transcribe(uri);
    } catch (e) {
      return fail(e, { step: 'transcribe', uri });
    }
    if (!transcript.text) {
      return fail(new Error("I couldn't make out any words. Please try again."), null);
    }
    set((s) => ({
      messages: [
        ...s.messages,
        { id: newId(), role: 'user', text: transcript.text, language: transcript.language },
      ],
    }));
    await runSend(transcript.text, transcript.language);
  }

  async function runSend(text: string, language: string) {
    set({ status: 'sending', error: null, pending: null });
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
      set((s) => ({
        status: 'idle',
        messages: [
          ...s.messages,
          { id: newId(), role: 'assistant', text: reply_text, language: replyLanguage, meta },
        ],
      }));
    } catch (e) {
      fail(e, { step: 'send', text, language });
    }
  }

  return {
    messages: [],
    sessionId: null,
    status: 'idle',
    error: null,
    pending: null,

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

    resetConversation: () =>
      set({ messages: [], sessionId: null, status: 'idle', error: null, pending: null }),
  };
});
