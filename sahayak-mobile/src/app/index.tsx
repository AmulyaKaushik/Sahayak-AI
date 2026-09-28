import { Link } from 'expo-router';
import { useRef } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { env } from '@/config/env';
import { useVoiceRecorder } from '@/hooks/use-voice-recorder';
import { ChatMessage, useConversation } from '@/store/conversation';

function formatDuration(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// Home screen (route "/"). Phase D: speak → transcript → (mock) backend reply.
export default function HomeScreen() {
  const voice = useVoiceRecorder();
  const messages = useConversation((s) => s.messages);
  const status = useConversation((s) => s.status);
  const error = useConversation((s) => s.error);
  const canRetry = useConversation((s) => s.pending !== null);
  const speakingId = useConversation((s) => s.speakingId);
  const ttsNotice = useConversation((s) => s.ttsNotice);
  const { processRecording, retry, clearError, speakMessage, stopSpeaking } =
    useConversation.getState();
  const scrollRef = useRef<ScrollView>(null);

  const busy = status === 'transcribing' || status === 'sending';

  async function onMicPress() {
    if (voice.isRecording) {
      const recording = await voice.stopRecording();
      if (recording) await processRecording(recording);
    } else {
      // Tapping the mic while a reply is being read aloud interrupts it.
      await stopSpeaking();
      clearError();
      await voice.startRecording();
    }
  }

  const statusText = voice.isRecording
    ? `Listening… ${formatDuration(voice.durationMillis)}`
    : status === 'transcribing'
      ? 'Transcribing…'
      : status === 'sending'
        ? 'Thinking…'
        : status === 'speaking'
          ? 'Speaking… (tap the mic to interrupt)'
          : voice.isPlaying
            ? 'Playing your recording…'
            : 'Tap the mic and speak';

  return (
    <View style={styles.container}>
      {(env.useMockStt || env.useMockApi) && (
        <Text style={styles.mockBadge}>
          MOCK: {[env.useMockStt && 'speech-to-text', env.useMockApi && 'backend']
            .filter(Boolean)
            .join(' + ')}
        </Text>
      )}

      <ScrollView
        ref={scrollRef}
        style={styles.messages}
        contentContainerStyle={styles.messagesContent}
        // Keep the newest message in view.
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}>
        {messages.length === 0 && (
          <Text style={styles.empty}>Ask about loans, accounts or schemes in Hindi or English.</Text>
        )}
        {messages.map((m) => (
          <MessageRow
            key={m.id}
            message={m}
            isSpeaking={m.id === speakingId}
            onPress={
              m.role === 'assistant' && !busy && !voice.isRecording
                ? () => speakMessage(m.id)
                : undefined
            }
          />
        ))}
      </ScrollView>

      <View style={styles.controls}>
        <Text style={styles.status}>{statusText}</Text>

        {error && (
          <View style={styles.errorRow}>
            <Text style={styles.error}>{error}</Text>
            {canRetry && (
              <Pressable onPress={retry} style={styles.smallButton}>
                <Text style={styles.smallButtonText}>Retry</Text>
              </Pressable>
            )}
          </View>
        )}

        <Pressable
          onPress={onMicPress}
          disabled={busy}
          style={({ pressed }) => [
            styles.mic,
            voice.isRecording && styles.micRecording,
            (pressed || busy) && styles.micDimmed,
          ]}
          accessibilityRole="button"
          accessibilityLabel={voice.isRecording ? 'Stop recording' : 'Start recording'}>
          {busy ? (
            <ActivityIndicator color="#fff" size="large" />
          ) : (
            <Text style={styles.micText}>{voice.isRecording ? 'Stop' : 'Mic'}</Text>
          )}
        </Pressable>

        {voice.permission === 'denied' && (
          <Text style={styles.warning}>
            Microphone access is needed to talk to Sahayak. Tap the mic to be asked again.
          </Text>
        )}
        {voice.permission === 'blocked' && (
          <View style={styles.center}>
            <Text style={styles.warning}>
              Microphone access is turned off for this app. Enable it in your phone&apos;s
              settings.
            </Text>
            <Pressable onPress={voice.openSettings} style={styles.smallButton}>
              <Text style={styles.smallButtonText}>Open phone settings</Text>
            </Pressable>
          </View>
        )}
        {voice.error && <Text style={styles.error}>{voice.error}</Text>}
        {ttsNotice && <Text style={styles.warning}>{ttsNotice}</Text>}

        <View style={styles.footer}>
          {voice.recordingUri && !voice.isRecording && (
            <Pressable onPress={voice.playRecording}>
              <Text style={styles.link}>Play my recording</Text>
            </Pressable>
          )}
          <Link href="/settings" style={styles.link}>
            Settings
          </Link>
        </View>
      </View>
    </View>
  );
}

function MessageRow({
  message,
  isSpeaking,
  onPress,
}: {
  message: ChatMessage;
  isSpeaking: boolean;
  onPress?: () => void;
}) {
  const isUser = message.role === 'user';
  const meta = message.meta;
  const details = [
    meta?.eligible !== undefined && `eligible: ${meta.eligible ? 'yes' : 'no'}`,
    meta?.missing_fields?.length && `needs: ${meta.missing_fields.join(', ')}`,
    isSpeaking ? 'speaking…' : onPress && 'tap to hear again',
  ].filter(Boolean);

  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      style={[
        styles.bubble,
        isUser ? styles.userBubble : styles.assistantBubble,
        isSpeaking && styles.speakingBubble,
      ]}>
      <Text style={isUser ? styles.userText : styles.assistantText}>{message.text}</Text>
      <Text style={[styles.meta, isUser && styles.userMeta]}>
        {message.language}
        {details.length > 0 && ` · ${details.join(' · ')}`}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  center: { alignItems: 'center' },
  mockBadge: {
    alignSelf: 'center',
    marginTop: 8,
    fontSize: 12,
    fontWeight: '700',
    color: '#B45309',
    backgroundColor: '#FEF3C7',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  messages: { flex: 1 },
  messagesContent: { padding: 16, gap: 10 },
  empty: { color: '#94A3B8', textAlign: 'center', marginTop: 48, fontSize: 16 },
  bubble: { maxWidth: '85%', padding: 12, borderRadius: 16 },
  userBubble: { alignSelf: 'flex-end', backgroundColor: '#208AEF', borderBottomRightRadius: 4 },
  assistantBubble: {
    alignSelf: 'flex-start',
    backgroundColor: '#F1F5F9',
    borderBottomLeftRadius: 4,
  },
  speakingBubble: { borderWidth: 2, borderColor: '#208AEF' },
  userText: { color: '#fff', fontSize: 17 },
  assistantText: { color: '#0F172A', fontSize: 17 },
  meta: { marginTop: 4, fontSize: 11, color: '#64748B' },
  userMeta: { color: '#DBEAFE' },
  controls: {
    alignItems: 'center',
    paddingHorizontal: 24,
    paddingTop: 12,
    paddingBottom: 24,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#E2E8F0',
  },
  status: { fontSize: 16, color: '#333', marginBottom: 12 },
  mic: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: '#208AEF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  micRecording: { backgroundColor: '#E5484D' },
  micDimmed: { opacity: 0.7 },
  micText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  errorRow: { alignItems: 'center', marginBottom: 12 },
  smallButton: {
    marginTop: 8,
    paddingVertical: 6,
    paddingHorizontal: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#208AEF',
  },
  smallButtonText: { color: '#208AEF', fontSize: 15, fontWeight: '600' },
  warning: { marginTop: 12, color: '#B45309', textAlign: 'center' },
  error: { color: '#E5484D', textAlign: 'center' },
  footer: { flexDirection: 'row', gap: 24, marginTop: 16 },
  link: { color: '#208AEF', fontSize: 15 },
});
