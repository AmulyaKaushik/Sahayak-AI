import axios, { isAxiosError } from 'axios';

import { env } from '@/config/env';

// Speech-to-text. Everything provider-specific (Groq-hosted Whisper today)
// stays in this file, so swapping to another provider (e.g. Bhashini) means
// rewriting only transcribeGroq().

export type Transcript = {
  text: string;
  // BCP-47 tag such as "hi-IN" or "en-IN", ready to pass to the backend.
  language: string;
};

// Groq exposes an OpenAI-compatible endpoint and a free tier.
const GROQ_URL = 'https://api.groq.com/openai/v1/audio/transcriptions';
// large-v3 (not -turbo) for the best Hindi/Hinglish accuracy; both are free.
const GROQ_MODEL = 'whisper-large-v3';
const TIMEOUT_MS = 30_000;

// Whisper reports the detected language either as an English name ("hindi")
// or an ISO code ("hi") depending on the host. Map both to BCP-47 tags.
const LANGUAGE_TO_BCP47: Record<string, string> = {
  hindi: 'hi-IN', hi: 'hi-IN',
  english: 'en-IN', en: 'en-IN',
  bengali: 'bn-IN', bn: 'bn-IN',
  marathi: 'mr-IN', mr: 'mr-IN',
  tamil: 'ta-IN', ta: 'ta-IN',
  telugu: 'te-IN', te: 'te-IN',
  gujarati: 'gu-IN', gu: 'gu-IN',
  kannada: 'kn-IN', kn: 'kn-IN',
  malayalam: 'ml-IN', ml: 'ml-IN',
  punjabi: 'pa-IN', pa: 'pa-IN',
  urdu: 'ur-IN', ur: 'ur-IN',
};
const DEVANAGARI = /[ऀ-ॿ]/;

export async function transcribe(audioUri: string): Promise<Transcript> {
  return env.useMockStt ? transcribeMock() : transcribeGroq(audioUri);
}

async function transcribeMock(): Promise<Transcript> {
  await new Promise((resolve) => setTimeout(resolve, 1000));
  return { text: 'मुझे होम लोन के बारे में जानकारी चाहिए', language: 'hi-IN' };
}

async function transcribeGroq(audioUri: string): Promise<Transcript> {
  if (!env.groqApiKey) {
    throw new Error('EXPO_PUBLIC_GROQ_API_KEY is not set in .env.local');
  }

  // React Native's FormData accepts a { uri, name, type } object and streams
  // the file from disk. (Web browsers need a Blob instead; not relevant here.)
  const form = new FormData();
  form.append('file', {
    uri: audioUri,
    name: 'speech.m4a',
    type: 'audio/m4a',
  } as unknown as Blob);
  form.append('model', GROQ_MODEL);
  // verbose_json includes the detected language, which plain json does not.
  form.append('response_format', 'verbose_json');

  try {
    const { data } = await axios.post<{ text: string; language?: string }>(GROQ_URL, form, {
      headers: { Authorization: `Bearer ${env.groqApiKey}` },
      timeout: TIMEOUT_MS,
    });
    const text = data.text.trim();
    return { text, language: resolveLanguage(data.language, text) };
  } catch (e) {
    throw new Error(describeError(e));
  }
}

function resolveLanguage(detected: string | undefined, text: string): string {
  const mapped = LANGUAGE_TO_BCP47[detected?.toLowerCase() ?? ''];
  if (mapped) return mapped;
  // No (or unknown) language from the provider: guess from the script.
  return DEVANAGARI.test(text) ? 'hi-IN' : 'en-IN';
}

function describeError(e: unknown): string {
  if (!isAxiosError(e)) return String(e);
  if (e.code === 'ECONNABORTED') return 'Speech-to-text timed out. Check your connection.';
  if (!e.response) return 'Could not reach the speech-to-text service. Check your connection.';
  const status = e.response.status;
  if (status === 401) return 'Groq rejected the API key (401). Check EXPO_PUBLIC_GROQ_API_KEY.';
  if (status === 429) return 'Groq free-tier rate limit reached (429). Wait a minute and retry.';
  const message = (e.response.data as { error?: { message?: string } })?.error?.message;
  return `Speech-to-text failed (${status})${message ? `: ${message}` : ''}`;
}
