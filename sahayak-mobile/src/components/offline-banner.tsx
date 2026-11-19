import Ionicons from '@expo/vector-icons/Ionicons';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { colors } from '@/constants/colors';
import { useConnectivity } from '@/store/connectivity';

// After this long without an answer to the very first health check, assume
// the free server is asleep and say so (it takes up to a minute to wake).
const WAKING_AFTER_MS = 4000;

// Persistent strip at the top of Home when the phone is offline, the backend's
// /health check fails, or the server is still waking up. Tapping it re-checks.
export function OfflineBanner() {
  const deviceOnline = useConnectivity((s) => s.deviceOnline);
  const backendOk = useConnectivity((s) => s.backendOk);
  const checking = useConnectivity((s) => s.checking);
  const checkBackend = useConnectivity((s) => s.checkBackend);
  const [slowCheck, setSlowCheck] = useState(false);

  const firstCheckPending = backendOk === null && checking;
  useEffect(() => {
    if (!firstCheckPending) return;
    const timer = setTimeout(() => setSlowCheck(true), WAKING_AFTER_MS);
    return () => {
      clearTimeout(timer);
      setSlowCheck(false);
    };
  }, [firstCheckPending]);

  let message: string | null = null;
  let waking = false;
  if (deviceOnline === false) message = "You're offline. Connect to the internet to talk to Sahayak.";
  else if (backendOk === false) message = "Can't reach the Sahayak server. Tap to retry.";
  else if (firstCheckPending && slowCheck) {
    message = 'Waking up the Sahayak server… this can take up to a minute.';
    waking = true;
  }
  if (!message) return null;

  return (
    <Pressable
      onPress={checkBackend}
      disabled={waking}
      style={[styles.banner, waking && styles.waking]}
      accessibilityRole="alert">
      <Ionicons name={waking ? 'cloud-outline' : 'cloud-offline-outline'} size={18} color="#fff" />
      <Text style={styles.text}>{message}</Text>
      {checking && <ActivityIndicator size="small" color="#fff" />}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: colors.danger,
  },
  waking: { backgroundColor: colors.sending },
  text: { flex: 1, color: '#fff', fontSize: 14, fontWeight: '600' },
});
