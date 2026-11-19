import type {
  ApiClient,
  AuthResponse,
  Credentials,
  ProfileFieldSpec,
  ProfileResponse,
  ProfileValue,
  SendMessageRequest,
  SendMessageResponse,
} from '@/services/api';

// Fake backend used while EXPO_PUBLIC_USE_MOCK_API is not "false". It follows
// the same contract as the real one (see api.ts), with a realistic delay, so
// the whole app — login, onboarding, profile, chat — can be demoed offline.
// Nothing here is persisted: restarting the app forgets the mock profile.

const LATENCY_MS = 800;
const wait = () => new Promise((resolve) => setTimeout(resolve, LATENCY_MS));

class MockHttpError extends Error {
  // Shaped like the bits of an axios error that api.ts reads.
  response: { status: number; data: { detail: string } };
  isAxiosError = true;
  config = { url: '/auth/login' };
  constructor(status: number, detail: string) {
    super(detail);
    this.response = { status, data: { detail } };
  }
}

const SCHEMA: ProfileFieldSpec[] = [
  { field: 'monthly_income', label: 'Monthly income (Rs)', type: 'number', options: [], required: true },
  { field: 'age', label: 'Your age', type: 'number', options: [], required: true },
  { field: 'dependents', label: 'Number of dependents', type: 'number', options: [], required: false },
  {
    field: 'employment_type',
    label: 'Employment type',
    type: 'select',
    options: ['salaried', 'self_employed', 'farmer', 'government_employee'],
    required: true,
  },
  { field: 'existing_products', label: 'Bank products or accounts you already have', type: 'multiselect', options: [], required: false },
  { field: 'has_girl_child_under_10', label: 'Do you have a girl child under 10?', type: 'boolean', options: [], required: false },
];

let profile: Record<string, ProfileValue> = {};
let profileCompleted = false;

function tokens(): AuthResponse {
  return {
    access_token: `mock-access-${Date.now()}`,
    refresh_token: `mock-refresh-${Date.now()}`,
    token_type: 'bearer',
    customer_id: 'mock-customer',
    profile_completed: profileCompleted,
  };
}

function checkCredentials({ password }: Credentials) {
  if (password.length < 8) throw new MockHttpError(422, 'password: at least 8 characters');
  if (password === 'wrong-password') {
    throw new MockHttpError(401, 'Incorrect phone/email or password');
  }
}

function reply(req: SendMessageRequest): SendMessageResponse {
  const hindi = req.language.startsWith('hi');
  const lower = req.text.toLowerCase();
  const aboutLoan = lower.includes('loan') || req.text.includes('लोन');
  const base = { results: [], facts_updated: [], sources: [], turn_type: 'new_question' };

  if (aboutLoan) {
    const text = hindi
      ? 'आप अभी होम लोन के लिए पात्र नहीं हैं। कृपया अपनी मासिक आय और उम्र बताइए।'
      : 'You are not eligible for Home Loan yet. Please tell me your monthly income and your age.';
    return {
      ...base,
      reply_text: text,
      display_text: text,
      language: req.language,
      results: [
        {
          scheme_id: 'home_loan',
          eligible: false,
          satisfied: [],
          missing: ['minimum_income', 'min_age'],
          ask: ['monthly_income', 'age'],
        },
      ],
      eligible: false,
    };
  }
  const text = hindi ? `(मॉक) आपने कहा: "${req.text}"` : `(Mock) You said: "${req.text}"`;
  return { ...base, reply_text: text, display_text: text, language: req.language };
}

export const mockApi: ApiClient = {
  async register(body) {
    await wait();
    checkCredentials(body);
    profile = {};
    profileCompleted = false;
    return tokens();
  },
  async login(body) {
    await wait();
    checkCredentials(body);
    return tokens();
  },
  async createSession() {
    await wait();
    return { session_id: `mock-${Date.now()}` };
  },
  async sendMessage(_sessionId, body) {
    await wait();
    return reply(body);
  },
  async checkHealth() {
    await wait();
    return { status: 'ok (mock)' };
  },
  async getProfile(): Promise<ProfileResponse> {
    await wait();
    return { fields: { ...profile }, profile_completed: profileCompleted };
  },
  async updateProfile(updates): Promise<ProfileResponse> {
    await wait();
    profile = { ...profile, ...updates };
    for (const [k, v] of Object.entries(profile)) if (v === null) delete profile[k];
    profileCompleted = true;
    return { fields: { ...profile }, profile_completed: true };
  },
  async getProfileSchema() {
    await wait();
    return SCHEMA;
  },
};
