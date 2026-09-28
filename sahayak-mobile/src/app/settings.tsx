import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { env } from '@/config/env';
import { checkHealth } from '@/services/api';
import { useConversation } from '@/store/conversation';

// Settings screen (route "/settings"). Developer info for now; the language
// picker and other user settings come in Phase G.
export default function SettingsScreen() {
  const sessionId = useConversation((s) => s.sessionId);
  const resetConversation = useConversation((s) => s.resetConversation);
  const [health, setHealth] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function onCheckHealth() {
    setChecking(true);
    setHealth(null);
    try {
      setHealth(`✓ ${(await checkHealth()).status}`);
    } catch (e) {
      setHealth(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setChecking(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Configuration</Text>
      <Row label="Speech-to-text" value={env.useMockStt ? 'Mock' : 'Groq Whisper'} />
      <Row label="Backend" value={env.useMockApi ? 'Mock' : env.apiBaseUrl || '(URL not set)'} />
      <Row label="Session" value={sessionId ?? '(none yet)'} />
      <Text style={styles.hint}>Change these in .env.local, then restart `npx expo start`.</Text>

      <Pressable onPress={onCheckHealth} disabled={checking} style={styles.button}>
        <Text style={styles.buttonText}>Check backend</Text>
      </Pressable>
      {checking && <ActivityIndicator style={styles.result} />}
      {health && <Text style={styles.result}>{health}</Text>}

      <Pressable onPress={resetConversation} style={styles.button}>
        <Text style={styles.buttonText}>Start new conversation</Text>
      </Pressable>
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 24, backgroundColor: '#fff' },
  heading: { fontSize: 13, fontWeight: '700', color: '#64748B', marginBottom: 8 },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E2E8F0',
    gap: 16,
  },
  label: { fontSize: 16, color: '#0F172A' },
  value: { fontSize: 16, color: '#64748B', flexShrink: 1 },
  hint: { fontSize: 13, color: '#94A3B8', marginTop: 8, marginBottom: 24 },
  button: {
    paddingVertical: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#208AEF',
    alignItems: 'center',
    marginTop: 12,
  },
  buttonText: { color: '#208AEF', fontSize: 16, fontWeight: '600' },
  result: { marginTop: 8, textAlign: 'center', color: '#334155' },
});
