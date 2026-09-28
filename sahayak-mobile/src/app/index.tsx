import { Link } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { env } from '@/config/env';
import { useVoiceRecorder } from '@/hooks/use-voice-recorder';
import { transcribe, Transcript } from '@/services/stt';

function formatDuration(ms: number) {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// Home screen (route "/"). Phase C: record a clip, then transcribe it.
export default function HomeScreen() {
  const voice = useVoiceRecorder();
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [sttError, setSttError] = useState<string | null>(null);

  async function runTranscription(uri: string) {
    setIsTranscribing(true);
    setSttError(null);
    try {
      setTranscript(await transcribe(uri));
    } catch (e) {
      setSttError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsTranscribing(false);
    }
  }

  async function onMicPress() {
    if (voice.isRecording) {
      const uri = await voice.stopRecording();
      if (uri) await runTranscription(uri);
    } else {
      setTranscript(null);
      setSttError(null);
      await voice.startRecording();
    }
  }

  const status = voice.isRecording
    ? `Recording… ${formatDuration(voice.durationMillis)}`
    : isTranscribing
      ? 'Transcribing…'
      : voice.isPlaying
        ? 'Playing back…'
        : 'Tap the mic and speak';

  return (
    <View style={styles.container}>
      {env.useMockStt && <Text style={styles.mockBadge}>MOCK speech-to-text</Text>}

      <Text style={styles.status}>{status}</Text>

      <Pressable
        onPress={onMicPress}
        disabled={isTranscribing}
        style={({ pressed }) => [
          styles.mic,
          voice.isRecording && styles.micRecording,
          (pressed || isTranscribing) && styles.micDimmed,
        ]}
        accessibilityRole="button"
        accessibilityLabel={voice.isRecording ? 'Stop recording' : 'Start recording'}>
        {isTranscribing ? (
          <ActivityIndicator color="#fff" size="large" />
        ) : (
          <Text style={styles.micText}>{voice.isRecording ? 'Stop' : 'Mic'}</Text>
        )}
      </Pressable>

      {transcript && (
        <View style={styles.transcriptBox}>
          <Text style={styles.transcriptLabel}>You said ({transcript.language}):</Text>
          <Text style={styles.transcriptText}>{transcript.text || '(no speech detected)'}</Text>
        </View>
      )}

      {sttError && (
        <View style={styles.center}>
          <Text style={styles.error}>{sttError}</Text>
          {voice.recordingUri && (
            <Pressable
              onPress={() => runTranscription(voice.recordingUri!)}
              style={styles.secondaryButton}>
              <Text style={styles.secondaryText}>Retry</Text>
            </Pressable>
          )}
        </View>
      )}

      {voice.recordingUri && !voice.isRecording && !isTranscribing && (
        <Pressable onPress={voice.playRecording} style={styles.secondaryButton}>
          <Text style={styles.secondaryText}>Play my recording</Text>
        </Pressable>
      )}

      {voice.permission === 'denied' && (
        <Text style={styles.warning}>
          Microphone access is needed to talk to Sahayak. Tap the mic to be asked again.
        </Text>
      )}
      {voice.permission === 'blocked' && (
        <View style={styles.center}>
          <Text style={styles.warning}>
            Microphone access is turned off for this app. Enable it in your phone&apos;s settings.
          </Text>
          <Pressable onPress={voice.openSettings} style={styles.secondaryButton}>
            <Text style={styles.secondaryText}>Open phone settings</Text>
          </Pressable>
        </View>
      )}
      {voice.error && <Text style={styles.error}>{voice.error}</Text>}

      <Link href="/settings" style={styles.settingsLink}>
        Settings
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    backgroundColor: '#fff',
  },
  center: { alignItems: 'center' },
  mockBadge: {
    position: 'absolute',
    top: 16,
    fontSize: 12,
    fontWeight: '700',
    color: '#B45309',
    backgroundColor: '#FEF3C7',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  status: { fontSize: 18, color: '#333', marginBottom: 32 },
  mic: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: '#208AEF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  micRecording: { backgroundColor: '#E5484D' },
  micDimmed: { opacity: 0.7 },
  micText: { color: '#fff', fontSize: 20, fontWeight: '700' },
  transcriptBox: {
    marginTop: 32,
    padding: 16,
    borderRadius: 12,
    backgroundColor: '#F1F5F9',
    alignSelf: 'stretch',
  },
  transcriptLabel: { fontSize: 13, color: '#64748B', marginBottom: 6 },
  transcriptText: { fontSize: 18, color: '#0F172A' },
  secondaryButton: {
    marginTop: 24,
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#208AEF',
  },
  secondaryText: { color: '#208AEF', fontSize: 16, fontWeight: '600' },
  warning: { marginTop: 24, color: '#B45309', textAlign: 'center' },
  error: { marginTop: 24, color: '#E5484D', textAlign: 'center' },
  settingsLink: { position: 'absolute', bottom: 32, color: '#208AEF', fontSize: 16 },
});
