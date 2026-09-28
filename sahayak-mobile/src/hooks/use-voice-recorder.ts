import {
  getRecordingPermissionsAsync,
  RecordingOptions,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioPlayer,
  useAudioPlayerStatus,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { useCallback, useEffect, useState } from 'react';
import { Linking } from 'react-native';

// .m4a (AAC) on both platforms, which Whisper accepts. Mono is plenty for
// speech and halves the upload size. (LOW_QUALITY records .3gp on Android,
// which Whisper rejects.)
const RECORDING_OPTIONS: RecordingOptions = {
  ...RecordingPresets.HIGH_QUALITY,
  numberOfChannels: 1,
};

// 'undetermined' = never asked; 'blocked' = denied and the OS won't show the
// prompt again, so the only way forward is the phone's Settings app.
export type MicPermission = 'undetermined' | 'granted' | 'denied' | 'blocked';

export function useVoiceRecorder() {
  const recorder = useAudioRecorder(RECORDING_OPTIONS);
  const recorderState = useAudioRecorderState(recorder);
  const player = useAudioPlayer();
  const playerStatus = useAudioPlayerStatus(player);

  const [permission, setPermission] = useState<MicPermission>('undetermined');
  const [recordingUri, setRecordingUri] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Check (without prompting) whether permission was already granted.
  useEffect(() => {
    getRecordingPermissionsAsync().then((res) => {
      if (res.granted) setPermission('granted');
      else if (!res.canAskAgain) setPermission('blocked');
    });
  }, []);

  const ensurePermission = useCallback(async (): Promise<boolean> => {
    const res = await requestRecordingPermissionsAsync();
    if (res.granted) {
      setPermission('granted');
      return true;
    }
    setPermission(res.canAskAgain ? 'denied' : 'blocked');
    return false;
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    try {
      if (!(await ensurePermission())) return;
      if (playerStatus.playing) player.pause();
      // iOS: the audio session must be switched into recording mode first.
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (e) {
      setError(`Could not start recording: ${String(e)}`);
    }
  }, [ensurePermission, player, playerStatus.playing, recorder]);

  // Returns the local file URI of the finished clip, or null on failure.
  const stopRecording = useCallback(async (): Promise<string | null> => {
    try {
      await recorder.stop();
      // iOS: while allowsRecording is true, playback goes to the quiet
      // earpiece instead of the loudspeaker. Switch it off before playing.
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      const uri = recorder.uri;
      if (!uri) throw new Error('recording produced no file');
      setRecordingUri(uri);
      player.replace({ uri });
      return uri;
    } catch (e) {
      setError(`Could not stop recording: ${String(e)}`);
      return null;
    }
  }, [player, recorder]);

  const playRecording = useCallback(async () => {
    if (!recordingUri) return;
    await player.seekTo(0);
    player.play();
  }, [player, recordingUri]);

  return {
    permission,
    isRecording: recorderState.isRecording,
    durationMillis: recorderState.durationMillis,
    isPlaying: playerStatus.playing,
    recordingUri,
    error,
    startRecording,
    stopRecording,
    playRecording,
    openSettings: Linking.openSettings,
  };
}
