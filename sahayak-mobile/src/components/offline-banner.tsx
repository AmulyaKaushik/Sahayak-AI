import Ionicons from '@expo/vector-icons/Ionicons';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { colors } from '@/constants/colors';
import { useConnectivity } from '@/store/connectivity';

// Persistent strip at the top of Home when the phone is offline or the
// backend's /health check fails. Tapping it re-checks immediately.
export function OfflineBanner() {
  const deviceOnline = useConnectivity((s) => s.deviceOnline);
  const backendOk = useConnectivity((s) => s.backendOk);
  const checking = useConnectivity((s) => s.checking);
  const checkBackend = useConnectivity((s) => s.checkBackend);

  let message: string | null = null;
  if (deviceOnline === false) message = "You're offline. Connect to the internet to talk to Sahayak.";
  else if (backendOk === false) message = "Can't reach the Sahayak server. Tap to retry.";
  if (!message) return null;

  return (
    <Pressable onPress={checkBackend} style={styles.banner} accessibilityRole="alert">
      <Ionicons name="cloud-offline-outline" size={18} color="#fff" />
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
  text: { flex: 1, color: '#fff', fontSize: 14, fontWeight: '600' },
});
