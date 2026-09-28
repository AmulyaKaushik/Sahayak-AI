import Ionicons from '@expo/vector-icons/Ionicons';
import { useRef } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { MessageBubble, TypingIndicator } from '@/components/message-bubble';
import { MicButton, MicState } from '@/components/mic-button';
import { NoticeCard } from '@/components/notice-card';
import { OfflineBanner } from '@/components/offline-banner';
import { colors } from '@/constants/colors';
import { env } from '@/config/env';
import { useVoiceRecorder } from '@/hooks/use-voice-recorder';
import { useConversation } from '@/store/conversation';

function formatDuration(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

const EXAMPLES = ['"I want to apply for a home loan"', '"मुझे बचत खाता खोलना है"'];

// Home screen (route "/"): the voice conversation.
export default function HomeScreen() {
  const voice = useVoiceRecorder();
  const messages = useConversation((s) => s.messages);
  const status = useConversation((s) => s.status);
  const error = useConversation((s) => s.error);
  const canRetry = useConversation((s) => s.pending !== null);
  const speakingId = useConversation((s) => s.speakingId);
  const ttsNotice = useConversation((s) => s.ttsNotice);
  const { processRecording, retry, clearError, speakMessage, stopSpeaking, dismissTtsNotice } =
    useConversation.getState();
  const scrollRef = useRef<ScrollView>(null);
  const insets = useSafeAreaInsets();

  const micState: MicState = voice.isRecording
    ? 'recording'
    : status === 'error' || voice.error
      ? 'error'
      : status;
  const busy = micState === 'transcribing' || micState === 'sending' || micState === 'waiting';

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

  const statusText: Record<MicState, string> = {
    idle: 'Tap the mic and speak',
    recording: `Listening… ${formatDuration(voice.durationMillis)} · tap to stop`,
    transcribing: 'Understanding what you said…',
    sending: 'Sending…',
    waiting: 'Sahayak is thinking…',
    speaking: 'Speaking… tap the mic to interrupt',
    error: 'Tap the mic to try again',
  };

  return (
    <View style={styles.container}>
      <OfflineBanner />
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
          <View style={styles.empty}>
            <Ionicons name="chatbubbles-outline" size={48} color={colors.textFaint} />
            <Text style={styles.emptyTitle}>Namaste! How can I help?</Text>
            <Text style={styles.emptyText}>
              Ask about loans, accounts or government schemes in Hindi or English. Try:
            </Text>
            {EXAMPLES.map((e) => (
              <Text key={e} style={styles.example}>
                {e}
              </Text>
            ))}
          </View>
        )}
        {messages.map((m) => (
          <MessageBubble
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
        {(status === 'sending' || status === 'waiting') && <TypingIndicator />}
      </ScrollView>

      <View style={[styles.controls, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        {error && (
          <NoticeCard
            tone="danger"
            message={error}
            actions={[
              ...(canRetry ? [{ label: 'Retry', onPress: retry }] : []),
              { label: 'Dismiss', onPress: clearError },
            ]}
          />
        )}
        {voice.error && <NoticeCard tone="danger" message={voice.error} />}
        {ttsNotice && (
          <NoticeCard
            tone="warning"
            message={ttsNotice}
            actions={[{ label: 'OK', onPress: dismissTtsNotice }]}
          />
        )}
        {voice.permission === 'denied' && (
          <NoticeCard
            tone="warning"
            message="Microphone access is needed to talk to Sahayak. Tap the mic to be asked again."
          />
        )}
        {voice.permission === 'blocked' && (
          <NoticeCard
            tone="warning"
            message="Microphone access is turned off for this app."
            actions={[{ label: 'Open phone settings', onPress: voice.openSettings }]}
          />
        )}

        <Text style={styles.status} accessibilityLiveRegion="polite">
          {statusText[micState]}
        </Text>
        <MicButton state={micState} onPress={onMicPress} disabled={busy} />

        {voice.recordingUri && !voice.isRecording && (
          <Pressable onPress={voice.playRecording} hitSlop={8}>
            <Text style={styles.link}>
              {voice.isPlaying ? 'Playing your recording…' : 'Play my last recording'}
            </Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  mockBadge: {
    alignSelf: 'center',
    marginTop: 8,
    fontSize: 12,
    fontWeight: '700',
    color: colors.warning,
    backgroundColor: colors.warningSoft,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: 'hidden',
  },
  messages: { flex: 1 },
  messagesContent: { padding: 16, gap: 10, flexGrow: 1 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8, padding: 24 },
  emptyTitle: { fontSize: 20, fontWeight: '700', color: colors.text, marginTop: 8 },
  emptyText: { fontSize: 15, color: colors.textMuted, textAlign: 'center', lineHeight: 22 },
  example: { fontSize: 15, color: colors.primary, fontStyle: 'italic' },
  controls: {
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    backgroundColor: colors.background,
  },
  status: { fontSize: 15, color: colors.textMuted },
  link: { color: colors.primary, fontSize: 14, marginTop: 4 },
});
