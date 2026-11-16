import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/constants/colors';
import { env } from '@/config/env';
import { useConnectivity } from '@/store/connectivity';
import { useConversation } from '@/store/conversation';
import { LANGUAGE_OPTIONS, useSettings } from '@/store/settings';

// Settings screen (route "/settings"): spoken-language preference plus
// developer info (which services are mocked, backend health, session).
export default function SettingsScreen() {
  const spokenLanguage = useSettings((s) => s.spokenLanguage);
  const setSpokenLanguage = useSettings((s) => s.setSpokenLanguage);
  const sessionId = useConversation((s) => s.sessionId);
  const resetConversation = useConversation((s) => s.resetConversation);
  const deviceOnline = useConnectivity((s) => s.deviceOnline);
  const backendOk = useConnectivity((s) => s.backendOk);
  const checking = useConnectivity((s) => s.checking);
  const checkBackend = useConnectivity((s) => s.checkBackend);

  const backendStatus =
    backendOk === null ? 'Not checked yet' : backendOk ? 'Reachable' : 'Unreachable';

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.heading}>I will speak in</Text>
      <View style={styles.segmented} accessibilityRole="radiogroup">
        {LANGUAGE_OPTIONS.map((o) => {
          const selected = o.value === spokenLanguage;
          return (
            <Pressable
              key={o.value}
              onPress={() => setSpokenLanguage(o.value)}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              style={[styles.segment, selected && styles.segmentSelected]}>
              <Text style={[styles.segmentText, selected && styles.segmentTextSelected]}>
                {o.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={styles.hint}>
        Auto detects the language each time. Picking one improves accuracy for short or mixed
        Hindi-English sentences. Replies are spoken in whatever language Sahayak answers in.
      </Text>

      <Text style={styles.heading}>Connection</Text>
      <Row label="Internet" value={deviceOnline === false ? 'Offline' : 'Online'} />
      <Row label="Sahayak server" value={backendStatus} />
      <Pressable onPress={checkBackend} disabled={checking} style={styles.button}>
        {checking ? (
          <ActivityIndicator color={colors.primary} />
        ) : (
          <Text style={styles.buttonText}>Check again</Text>
        )}
      </Pressable>

      <Text style={styles.heading}>Conversation</Text>
      <Row label="Session" value={sessionId ?? '(none yet)'} />
      <Pressable onPress={resetConversation} style={styles.button}>
        <Text style={styles.buttonText}>Start new conversation</Text>
      </Pressable>

      <Text style={styles.heading}>Developer</Text>
      <Row label="Speech-to-text" value={env.useMockStt ? 'Mock' : 'Groq Whisper'} />
      <Row label="Backend" value={env.useMockApi ? 'Mock' : env.apiBaseUrl || '(URL not set)'} />
      <Text style={styles.hint}>Change these in .env.local, then restart `npx expo start`.</Text>
    </ScrollView>
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
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: 20, paddingBottom: 48 },
  heading: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: 24,
    marginBottom: 8,
  },
  segmented: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: 10,
    padding: 3,
  },
  segment: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  segmentSelected: {
    backgroundColor: colors.background,
    shadowColor: '#000',
    shadowOpacity: 0.1,
    shadowRadius: 3,
    shadowOffset: { width: 0, height: 1 },
    elevation: 2,
  },
  segmentText: { fontSize: 16, color: colors.textMuted },
  segmentTextSelected: { color: colors.text, fontWeight: '700' },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    gap: 16,
  },
  label: { fontSize: 16, color: colors.text },
  value: { fontSize: 16, color: colors.textMuted, flexShrink: 1 },
  hint: { fontSize: 13, color: colors.textFaint, marginTop: 8, lineHeight: 18 },
  button: {
    paddingVertical: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.primary,
    alignItems: 'center',
    marginTop: 12,
  },
  buttonText: { color: colors.primary, fontSize: 16, fontWeight: '600' },
});
