import { create } from 'zustand';

import * as api from '@/services/api';
import {
  clearTokens,
  getAccount,
  getTokens,
  saveAccount,
  saveTokens,
} from '@/services/token-store';
import { useConversation, whenConversationLoaded } from '@/store/conversation';

// Who is signed in. The root layout (_layout.tsx) reads `status` and
// `profileCompleted` to decide which screens exist:
//   loading   -> splash spinner while the saved login is read on launch
//   signedOut -> login / register
//   signedIn, profile not completed -> onboarding form
//   signedIn, profile completed     -> chat, profile, settings
export type AuthStatus = 'loading' | 'signedOut' | 'signedIn';

type AuthState = {
  status: AuthStatus;
  customerId: string | null;
  loginId: string | null;
  profileCompleted: boolean;

  restore: () => Promise<void>;
  login: (loginId: string, password: string) => Promise<void>;
  register: (loginId: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  markProfileCompleted: () => Promise<void>;
};

const signedOutState = {
  status: 'signedOut' as const,
  customerId: null,
  loginId: null,
  profileCompleted: false,
};

export const useAuth = create<AuthState>()((set, get) => {
  async function signIn(response: api.AuthResponse, loginId: string) {
    await saveTokens({
      accessToken: response.access_token,
      refreshToken: response.refresh_token,
    });
    await saveAccount({
      customerId: response.customer_id,
      loginId,
      profileCompleted: response.profile_completed,
    });
    // A fresh login never inherits a previous user's chat (switching account
    // clears it; signing back in as the same account keeps it).
    await whenConversationLoaded();
    useConversation.getState().claimFor(response.customer_id);
    set({
      status: 'signedIn',
      customerId: response.customer_id,
      loginId,
      profileCompleted: response.profile_completed,
    });
  }

  return {
    status: 'loading',
    customerId: null,
    loginId: null,
    profileCompleted: false,

    // On launch: if tokens are saved, go straight to the signed-in screens
    // using the saved account info (works even while the server is asleep or
    // the phone is offline). The first API call refreshes the token if needed.
    async restore() {
      try {
        const [tokens, account] = await Promise.all([getTokens(), getAccount()]);
        if (!tokens || !account) {
          set(signedOutState);
          return;
        }
        // Bring back the saved chat, unless it belongs to someone else.
        await whenConversationLoaded();
        useConversation.getState().claimFor(account.customerId);
        set({ status: 'signedIn', ...account });
      } catch {
        set(signedOutState);
        return;
      }
      // In the background, check the server still agrees about onboarding
      // (e.g. it was completed on another phone). Errors are ignored here.
      api
        .getProfile()
        .then((p) => {
          if (get().status === 'signedIn' && p.profile_completed !== get().profileCompleted) {
            set({ profileCompleted: p.profile_completed });
            return persist();
          }
        })
        .catch(() => {});
    },

    async login(loginId, password) {
      const id = loginId.trim();
      await signIn(await api.login({ login_id: id, password }), id);
    },

    async register(loginId, password) {
      const id = loginId.trim();
      await signIn(await api.register({ login_id: id, password }), id);
    },

    async logout() {
      // Clear the chat too, otherwise the next person on this phone would
      // see it (and could keep using the old session id).
      useConversation.getState().resetConversation();
      set(signedOutState);
      await clearTokens().catch(() => {});
    },

    async markProfileCompleted() {
      set({ profileCompleted: true });
      await persist();
    },
  };

  async function persist() {
    const { customerId, loginId, profileCompleted } = get();
    if (customerId && loginId) await saveAccount({ customerId, loginId, profileCompleted });
  }
});

// The API client calls this when the refresh token is rejected (expired after
// 30 days, or revoked): the only way forward is to sign in again.
api.setAuthLostHandler(() => {
  if (useAuth.getState().status === 'signedIn') useAuth.getState().logout();
});
