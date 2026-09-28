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
import { useCallback, useEffect, useRef, useState } from 'react';
import { Linking } from 'react-native';

// .m4a (AAC) on both platforms, which Whisper accepts. Mono is plenty for
// speech and halves the upload size. (LOW_QUALITY records .3gp on Android,
// which Whisper rejects.) Metering reports the live input level so we can
// tell a silent clip from real speech.
const RECORDING_OPTIONS: RecordingOptions = {
  ...RecordingPresets.HIGH_QUALITY,
  numberOfChannels: 1,
  isMeteringEnabled: true,
};

// How often (ms) the recorder reports duration and level while recording.
const STATUS_INTERVAL_MS = 100;
// Metering is in dBFS: 0 is the loudest possible, -160 is silence. A quiet
// room sits around -50 to -60; speech near the phone peaks around -25 to -10.
const SILENCE_THRESHOLD_DB = -40;

// 'undetermined' = never asked; 'blocked' = denied and the OS won't show the
// prompt again, so the only way forward is the phone's Settings app.
export type MicPermission = 'undetermined' | 'granted' | 'denied' | 'blocked';

export type FinishedRecording = {
  uri: string;
  // True when the clip never got louder than SILENCE_THRESHOLD_DB.
  isSilent: boolean;
};

export function useVoiceRecorder() {
  const recorder = useAudioRecorder(RECORDING_OPTIONS);
  const recorderState = useAudioRecorderState(recorder, STATUS_INTERVAL_MS);
  const player = useAudioPlayer();
  const playerStatus = useAudioPlayerStatus(player);

  const [permission, setPermission] = useState<MicPermission>('undetermined');
  const [recordingUri, setRecordingUri] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Loudest level seen during the current recording. A ref (not state)
  // because updating it should not redraw the screen.
  const peakDb = useRef(-160);

  useEffect(() => {
    const level = recorderState.metering;
    if (recorderState.isRecording && level !== undefined && level > peakDb.current) {
      peakDb.current = level;
    }
  }, [recorderState.isRecording, recorderState.metering]);

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

  // Returns true if recording actually started.
  const startRecording = useCallback(async (): Promise<boolean> => {
    setError(null);
    try {
      if (!(await ensurePermission())) return false;
      if (playerStatus.playing) player.pause();
      // iOS: the audio session must be switched into recording mode first.
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      peakDb.current = -160;
      recorder.record();
      return true;
    } catch (e) {
      setError(`Could not start recording: ${String(e)}`);
      return false;
    }
  }, [ensurePermission, player, playerStatus.playing, recorder]);

  const stopRecording = useCallback(async (): Promise<FinishedRecording | null> => {
    try {
      await recorder.stop();
      // iOS: while allowsRecording is true, playback goes to the quiet
      // earpiece instead of the loudspeaker. Switch it off before playing.
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      const uri = recorder.uri;
      if (!uri) throw new Error('recording produced no file');
      setRecordingUri(uri);
      player.replace({ uri });
      // Shows in the `npx expo start` terminal; use it to tune the threshold.
      if (__DEV__) console.log(`[recorder] peak level ${peakDb.current.toFixed(1)} dB`);
      return { uri, isSilent: peakDb.current < SILENCE_THRESHOLD_DB };
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
