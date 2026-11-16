import NetInfo from '@react-native-community/netinfo';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { create } from 'zustand';

import { checkHealth } from '@/services/api';

// Is the phone online, and is the backend healthy? Drives the offline banner.
// null = not known yet (don't show a banner before the first check finishes).
type ConnectivityState = {
  deviceOnline: boolean | null;
  backendOk: boolean | null;
  checking: boolean;
  checkBackend: () => Promise<void>;
};

export const useConnectivity = create<ConnectivityState>()((set, get) => ({
  deviceOnline: null,
  backendOk: null,
  checking: false,
  async checkBackend() {
    if (get().checking) return;
    set({ checking: true });
    try {
      await checkHealth();
      set({ backendOk: true });
    } catch {
      set({ backendOk: false });
    } finally {
      set({ checking: false });
    }
  },
}));

const RECHECK_WHILE_DOWN_MS = 30_000;

// Mount once (in the root layout). Watches the phone's network state, checks
// the backend on start and whenever the app returns to the foreground, and
// keeps re-checking every 30 s while the backend is down.
export function useConnectivityMonitor() {
  const backendOk = useConnectivity((s) => s.backendOk);

  useEffect(() => {
    const { checkBackend } = useConnectivity.getState();
    checkBackend();

    const unsubscribeNet = NetInfo.addEventListener((state) => {
      const online = state.isConnected !== false;
      const wasOnline = useConnectivity.getState().deviceOnline;
      useConnectivity.setState({ deviceOnline: online });
      if (online && wasOnline === false) checkBackend(); // just reconnected
    });
    const appStateSub = AppState.addEventListener('change', (s) => {
      if (s === 'active') checkBackend();
    });
    return () => {
      unsubscribeNet();
      appStateSub.remove();
    };
  }, []);

  useEffect(() => {
    if (backendOk !== false) return;
    const timer = setInterval(() => useConnectivity.getState().checkBackend(), RECHECK_WHILE_DOWN_MS);
    return () => clearInterval(timer);
  }, [backendOk]);
}
