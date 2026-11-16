import Ionicons from '@expo/vector-icons/Ionicons';
import { useEffect, useState } from 'react';
import { Animated, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/constants/colors';
import type { ChatMessage } from '@/store/conversation';

function formatTime(timestamp: number) {
  const d = new Date(timestamp);
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// Turns backend field names like "monthly_income" into "Monthly income".
function humanize(field: string) {
  const s = field.replace(/_/g, ' ');
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function MessageBubble({
  message,
  isSpeaking,
  onPress,
}: {
  message: ChatMessage;
  isSpeaking: boolean;
  // Assistant bubbles only: tap to hear the reply again.
  onPress?: () => void;
}) {
  const isUser = message.role === 'user';
  const { eligible, missing_fields } = message.meta ?? {};

  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      accessibilityHint={onPress ? 'Plays this reply aloud' : undefined}
      style={({ pressed }) => [
        styles.bubble,
        isUser ? styles.user : styles.assistant,
        isSpeaking && styles.speaking,
        pressed && styles.pressed,
      ]}>
      <Text style={[styles.text, isUser && styles.userText]}>{message.text}</Text>

      {(eligible !== undefined || !!missing_fields?.length) && (
        <View style={styles.chips}>
          {eligible !== undefined && (
            <Text style={[styles.chip, eligible ? styles.chipYes : styles.chipNo]}>
              {eligible ? 'Eligible' : 'Not eligible'}
            </Text>
          )}
          {missing_fields?.map((f) => (
            <Text key={f} style={[styles.chip, styles.chipNeed]}>
              Needs: {humanize(f)}
            </Text>
          ))}
        </View>
      )}

      <View style={styles.footer}>
        {!isUser && (
          <Ionicons
            name={isSpeaking ? 'volume-high' : 'volume-medium-outline'}
            size={14}
            color={isSpeaking ? colors.speaking : colors.textFaint}
          />
        )}
        <Text style={[styles.meta, isUser && styles.userMeta]}>
          {formatTime(message.createdAt)} · {message.language}
        </Text>
      </View>
    </Pressable>
  );
}

// Three bouncing dots in an assistant-style bubble while waiting for a reply.
export function TypingIndicator() {
  const [dots] = useState(() => [0, 1, 2].map(() => new Animated.Value(0)));

  useEffect(() => {
    const loop = Animated.loop(
      Animated.stagger(
        150,
        dots.map((d) =>
          Animated.sequence([
            Animated.timing(d, { toValue: 1, duration: 300, useNativeDriver: true }),
            Animated.timing(d, { toValue: 0, duration: 300, useNativeDriver: true }),
          ]),
        ),
      ),
    );
    loop.start();
    return () => loop.stop();
  }, [dots]);

  return (
    <View
      style={[styles.bubble, styles.assistant, styles.typing]}
      accessibilityLabel="Sahayak is typing">
      {dots.map((d, i) => (
        <Animated.View
          key={i}
          style={[
            styles.dot,
            {
              opacity: d.interpolate({ inputRange: [0, 1], outputRange: [0.35, 1] }),
              transform: [{ translateY: d.interpolate({ inputRange: [0, 1], outputRange: [0, -4] }) }],
            },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: { maxWidth: '85%', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 18 },
  user: { alignSelf: 'flex-end', backgroundColor: colors.primary, borderBottomRightRadius: 4 },
  assistant: {
    alignSelf: 'flex-start',
    backgroundColor: colors.surface,
    borderBottomLeftRadius: 4,
    borderWidth: 2,
    borderColor: colors.surface,
  },
  speaking: { borderColor: colors.speaking },
  pressed: { opacity: 0.8 },
  text: { fontSize: 17, lineHeight: 24, color: colors.text },
  userText: { color: '#fff' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 },
  chip: {
    fontSize: 12,
    fontWeight: '600',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
    overflow: 'hidden',
  },
  chipYes: { color: colors.success, backgroundColor: colors.successSoft },
  chipNo: { color: colors.danger, backgroundColor: colors.dangerSoft },
  chipNeed: { color: colors.warning, backgroundColor: colors.warningSoft },
  footer: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 },
  meta: { fontSize: 11, color: colors.textMuted },
  userMeta: { color: colors.primarySoft },
  typing: { flexDirection: 'row', gap: 5, paddingVertical: 16 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.textMuted },
});
