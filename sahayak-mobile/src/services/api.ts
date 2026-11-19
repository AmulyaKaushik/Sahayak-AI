import {
  create as createAxios,
  isAxiosError,
  type AxiosError,
  type InternalAxiosRequestConfig,
} from 'axios';

import { env } from '@/config/env';
import { mockApi } from '@/services/api-mock';
import { clearTokens, getTokens, saveTokens } from '@/services/token-store';

// Backend API client. This is the ONLY file that knows the backend's URLs and
// request/response shapes. Screens and stores call the exported functions
// below and never touch axios directly.
//
// Contract: connect.md section 9, implemented by backend/ (FastAPI).
// Every route except /auth/* and /health needs "Authorization: Bearer <access token>".

// ---- Contract ---------------------------------------------------------------

export const API_PATHS = {
  register: '/auth/register',
  login: '/auth/login',
  refresh: '/auth/refresh',
  health: '/health',
  sessions: '/api/v1/sessions',
  messages: (sessionId: string) => `/api/v1/sessions/${encodeURIComponent(sessionId)}/messages`,
  profile: '/api/v1/me/profile',
  profileSchema: '/api/v1/profile/schema',
};

export type Credentials = { login_id: string; password: string };

export type AuthResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  customer_id: string;
  profile_completed: boolean;
};

export type CreateSessionResponse = { session_id: string };

export type SendMessageRequest = {
  text: string;
  language: string; // BCP-47, e.g. "hi-IN"
};

// One scheme/loan the eligibility engine evaluated this turn.
export type SchemeResult = {
  scheme_id: string;
  eligible: boolean;
  satisfied: string[]; // rule names that passed
  missing: string[]; // rule names not met yet
  ask: string[]; // profile fields the user still has to give
};

// A document passage the RAG agent answered from.
export type RagSource = { doc: string; page: number | null };

export type SendMessageResponse = {
  reply_text: string; // short, voice-friendly: this is what gets spoken
  display_text: string; // may hold more detail: this is what is shown
  language: string;
  results: SchemeResult[];
  facts_updated: string[]; // profile fields the backend saved from this message
  sources: RagSource[];
  turn_type: string;
  eligible?: boolean | null;
  missing_fields?: string[];
};

export type HealthResponse = { status: string };

export type ProfileFieldType = 'number' | 'text' | 'boolean' | 'select' | 'multiselect';

export type ProfileFieldSpec = {
  field: string;
  label: string;
  type: ProfileFieldType;
  options: string[];
  required: boolean;
};

export type ProfileValue = string | number | boolean | string[] | null;

export type ProfileResponse = {
  fields: Record<string, ProfileValue>;
  profile_completed: boolean;
};

// ---- Errors -----------------------------------------------------------------

// Thrown by every exported function. `message` is safe to show to the user;
// `status` is the HTTP status (undefined for network errors / timeouts).
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// ---- Real client ------------------------------------------------------------

// Free hosting (Render) sleeps after ~15 idle minutes and takes 30-60 s to
// wake, and a chat turn itself takes 5-15 s, so allow a full minute.
const TIMEOUT_MS = 60_000;

const http = createAxios({
  baseURL: env.apiBaseUrl,
  timeout: TIMEOUT_MS,
  headers: { 'Content-Type': 'application/json' },
});

// Separate instance with no interceptors, used only for the refresh call (so
// a failing refresh can't trigger another refresh).
const bare = createAxios({ baseURL: env.apiBaseUrl, timeout: TIMEOUT_MS });

const isAuthPath = (url?: string) => !!url && url.startsWith('/auth/');

// The auth store registers a callback here, so this file doesn't import the
// store (that would be a circular import). Called when the refresh token is
// rejected: the user has to sign in again.
let onAuthLost: () => void = () => {};
export function setAuthLostHandler(handler: () => void) {
  onAuthLost = handler;
}

// Request interceptor: runs before every request and attaches the token.
http.interceptors.request.use(async (config) => {
  if (!isAuthPath(config.url)) {
    const tokens = await getTokens();
    if (tokens) config.headers.Authorization = `Bearer ${tokens.accessToken}`;
  }
  return config;
});

// Access tokens live 30 minutes. When one expires the server answers 401; we
// then swap the refresh token for a new pair and replay the request once.
// `refreshing` makes concurrent 401s share ONE refresh call: the server
// rotates refresh tokens, so a second parallel refresh would use an
// already-replaced token and log the user out.
let refreshing: Promise<string | null> | null = null;

function refreshAccessToken(): Promise<string | null> {
  refreshing ??= (async () => {
    try {
      const tokens = await getTokens();
      if (!tokens) return null;
      const { data } = await bare.post<AuthResponse>(API_PATHS.refresh, {
        refresh_token: tokens.refreshToken,
      });
      await saveTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
      return data.access_token;
    } catch (e) {
      // 401 = refresh token expired or revoked: sign out. A network error
      // (offline, server asleep) is NOT a reason to throw the user out.
      if (isAxiosError(e) && e.response?.status === 401) {
        await clearTokens();
        onAuthLost();
      }
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

http.interceptors.response.use(undefined, async (error: AxiosError) => {
  const config = error.config as RetriableConfig | undefined;
  if (
    error.response?.status !== 401 ||
    !config ||
    config._retried ||
    isAuthPath(config.url)
  ) {
    throw error;
  }
  config._retried = true;
  const accessToken = await refreshAccessToken();
  if (!accessToken) throw error;
  config.headers.Authorization = `Bearer ${accessToken}`;
  return http(config);
});

const realApi = {
  async register(body: Credentials): Promise<AuthResponse> {
    return (await http.post<AuthResponse>(API_PATHS.register, body)).data;
  },
  async login(body: Credentials): Promise<AuthResponse> {
    return (await http.post<AuthResponse>(API_PATHS.login, body)).data;
  },
  async createSession(): Promise<CreateSessionResponse> {
    return (await http.post<CreateSessionResponse>(API_PATHS.sessions)).data;
  },
  async sendMessage(sessionId: string, body: SendMessageRequest): Promise<SendMessageResponse> {
    return (await http.post<SendMessageResponse>(API_PATHS.messages(sessionId), body)).data;
  },
  async checkHealth(): Promise<HealthResponse> {
    return (await http.get<HealthResponse>(API_PATHS.health)).data;
  },
  async getProfile(): Promise<ProfileResponse> {
    return (await http.get<ProfileResponse>(API_PATHS.profile)).data;
  },
  // Partial update: send only the changed fields. null clears a field. An
  // empty object is how onboarding's "Skip" marks the profile as done.
  async updateProfile(updates: Record<string, ProfileValue>): Promise<ProfileResponse> {
    return (await http.patch<ProfileResponse>(API_PATHS.profile, updates)).data;
  },
  async getProfileSchema(): Promise<ProfileFieldSpec[]> {
    return (await http.get<ProfileFieldSpec[]>(API_PATHS.profileSchema)).data;
  },
};

export type ApiClient = typeof realApi;

const client: ApiClient = env.useMockApi ? mockApi : realApi;

// ---- Public functions (same for mock and real) ------------------------------

export async function register(body: Credentials) {
  return withReadableErrors(() => client.register(body));
}
export async function login(body: Credentials) {
  return withReadableErrors(() => client.login(body));
}
export async function createSession() {
  return withReadableErrors(() => client.createSession());
}
export async function sendMessage(sessionId: string, body: SendMessageRequest) {
  return withReadableErrors(() => client.sendMessage(sessionId, body));
}
export async function checkHealth() {
  return withReadableErrors(() => client.checkHealth());
}
export async function getProfile() {
  return withReadableErrors(() => client.getProfile());
}
export async function updateProfile(updates: Record<string, ProfileValue>) {
  return withReadableErrors(() => client.updateProfile(updates));
}
export async function getProfileSchema() {
  return withReadableErrors(() => client.getProfileSchema());
}

async function withReadableErrors<T>(call: () => Promise<T>): Promise<T> {
  if (!env.useMockApi && !env.apiBaseUrl) {
    throw new ApiError('EXPO_PUBLIC_API_BASE_URL is not set in .env.local');
  }
  try {
    return await call();
  } catch (e) {
    throw toApiError(e);
  }
}

function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  if (!isAxiosError(e)) return new ApiError(e instanceof Error ? e.message : String(e));
  if (e.code === 'ECONNABORTED') {
    return new ApiError('The assistant took too long to reply. Please try again.');
  }
  if (!e.response) return new ApiError('Could not reach the Sahayak server. Check your connection.');

  const status = e.response.status;
  // Backend error shape: {"error": {"code", "message"}, "detail": message}.
  const body = e.response.data as { error?: { message?: unknown }; detail?: unknown } | undefined;
  const serverMessage =
    typeof body?.error?.message === 'string'
      ? body.error.message
      : typeof body?.detail === 'string'
        ? body.detail
        : undefined;

  const isLogin = isAuthPath(e.config?.url);
  if (status === 401 && !isLogin) {
    return new ApiError('Your login has expired. Please sign in again.', status);
  }
  if (status === 429) {
    return new ApiError(serverMessage ?? 'Too many attempts. Please wait a minute and try again.', status);
  }
  if (status >= 500) {
    return new ApiError(
      `The Sahayak server had a problem (${status}). Please try again in a moment.`,
      status,
    );
  }
  return new ApiError(serverMessage ?? `Server error (${status})`, status);
}
