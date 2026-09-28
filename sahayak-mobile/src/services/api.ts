import { create as createAxios, isAxiosError } from 'axios';

import { env } from '@/config/env';
import { mockApi } from '@/services/api-mock';

// Backend API client. This is the ONLY file that knows the backend's URLs and
// request/response shapes. Screens and the store call createSession(),
// sendMessage() and checkHealth() and never touch axios directly, so when the
// real contract changes, this file is the only one to edit.

// ---- Contract (planned; confirm with the backend team) ----------------------

export const API_PATHS = {
  sessions: '/api/v1/sessions',
  messages: (sessionId: string) => `/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`,
  health: '/api/v1/health',
};

export type CreateSessionResponse = { session_id: string };

export type SendMessageRequest = {
  text: string;
  language: string; // BCP-47, e.g. "hi-IN"
};

export type SendMessageResponse = {
  reply_text: string;
  language: string;
  eligible?: boolean;
  missing_fields?: string[];
  session_state?: string;
};

export type HealthResponse = { status: string };

// ---- Client -----------------------------------------------------------------

const TIMEOUT_MS = 20_000;

const http = createAxios({
  baseURL: env.apiBaseUrl,
  timeout: TIMEOUT_MS,
  headers: { 'Content-Type': 'application/json' },
});

const realApi = {
  async createSession(): Promise<CreateSessionResponse> {
    const { data } = await http.post<CreateSessionResponse>(API_PATHS.sessions);
    return data;
  },
  async sendMessage(sessionId: string, body: SendMessageRequest): Promise<SendMessageResponse> {
    const { data } = await http.post<SendMessageResponse>(API_PATHS.messages(sessionId), body);
    return data;
  },
  async checkHealth(): Promise<HealthResponse> {
    const { data } = await http.get<HealthResponse>(API_PATHS.health);
    return data;
  },
};

export type ApiClient = typeof realApi;

const client: ApiClient = env.useMockApi ? mockApi : realApi;

// Public functions: same signatures for mock and real; errors are rethrown as
// plain Errors with a message that is safe to show to the user.
export async function createSession() {
  return withReadableErrors(() => client.createSession());
}
export async function sendMessage(sessionId: string, body: SendMessageRequest) {
  return withReadableErrors(() => client.sendMessage(sessionId, body));
}
export async function checkHealth() {
  return withReadableErrors(() => client.checkHealth());
}

async function withReadableErrors<T>(call: () => Promise<T>): Promise<T> {
  if (!env.useMockApi && !env.apiBaseUrl) {
    throw new Error('EXPO_PUBLIC_API_BASE_URL is not set in .env.local');
  }
  try {
    return await call();
  } catch (e) {
    throw new Error(describeError(e));
  }
}

function describeError(e: unknown): string {
  if (!isAxiosError(e)) return e instanceof Error ? e.message : String(e);
  if (e.code === 'ECONNABORTED') return 'The assistant took too long to reply. Please try again.';
  if (!e.response) return 'Could not reach the Sahayak server. Check your connection.';
  const status = e.response.status;
  const detail = (e.response.data as { detail?: unknown })?.detail; // FastAPI's error field
  return `Server error (${status})${typeof detail === 'string' ? `: ${detail}` : ''}`;
}
