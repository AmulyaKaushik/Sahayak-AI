import type {
  ApiClient,
  CreateSessionResponse,
  HealthResponse,
  SendMessageRequest,
  SendMessageResponse,
} from '@/services/api';

// Fake backend used while EXPO_PUBLIC_USE_MOCK_API is not "false". It follows
// the same contract as the real one (see api.ts), with a realistic delay, so
// the rest of the app cannot tell the difference.

const LATENCY_MS = 800;
const wait = () => new Promise((resolve) => setTimeout(resolve, LATENCY_MS));

function reply(req: SendMessageRequest): SendMessageResponse {
  const hindi = req.language.startsWith('hi');
  const lower = req.text.toLowerCase();
  const aboutLoan = lower.includes('loan') || req.text.includes('लोन');

  if (aboutLoan) {
    return {
      reply_text: hindi
        ? 'ज़रूर, मैं होम लोन में आपकी मदद कर सकता हूँ। कृपया अपनी मासिक आय और उम्र बताइए।'
        : 'Sure, I can help with a home loan. Please tell me your monthly income and your age.',
      language: req.language,
      missing_fields: ['monthly_income', 'age'],
      session_state: 'collecting_details',
    };
  }
  return {
    reply_text: hindi ? `(मॉक) आपने कहा: "${req.text}"` : `(Mock) You said: "${req.text}"`,
    language: req.language,
    session_state: 'idle',
  };
}

export const mockApi: ApiClient = {
  async createSession(): Promise<CreateSessionResponse> {
    await wait();
    return { session_id: `mock-${Date.now()}` };
  },
  async sendMessage(_sessionId, body): Promise<SendMessageResponse> {
    await wait();
    return reply(body);
  },
  async checkHealth(): Promise<HealthResponse> {
    await wait();
    return { status: 'ok (mock)' };
  },
};
