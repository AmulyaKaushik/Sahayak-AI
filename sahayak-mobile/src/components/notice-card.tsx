import Ionicons from '@expo/vector-icons/Ionicons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/constants/colors';

type Action = { label: string; onPress: () => void };

// Inline card for errors ("danger") and non-blocking warnings ("warning"),
// with optional action buttons such as Retry / Dismiss.
export function NoticeCard({
  tone,
  message,
  actions = [],
}: {
  tone: 'danger' | 'warning';
  message: string;
  actions?: Action[];
}) {
  const danger = tone === 'danger';
  const fg = danger ? colors.danger : colors.warning;
  return (
    <View
      style={[styles.card, { backgroundColor: danger ? colors.dangerSoft : colors.warningSoft }]}
      accessibilityRole="alert">
      <View style={styles.row}>
        <Ionicons name={danger ? 'alert-circle' : 'information-circle'} size={20} color={fg} />
        <Text style={[styles.message, { color: fg }]}>{message}</Text>
      </View>
      {actions.length > 0 && (
        <View style={styles.actions}>
          {actions.map((a) => (
            <Pressable key={a.label} onPress={a.onPress} hitSlop={8}>
              <Text style={[styles.action, { color: fg }]}>{a.label}</Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { alignSelf: 'stretch', borderRadius: 12, padding: 12, marginBottom: 8 },
  row: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  message: { flex: 1, fontSize: 14, lineHeight: 20 },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 20, marginTop: 8 },
  action: { fontSize: 15, fontWeight: '700' },
});
