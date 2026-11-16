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
// Metering is in dBFS: 0 is the loudest possible, -160 is silence.
// Silence detection: ignore the first/last EDGE_IGNORE_MS (the tap on the
// button makes a loud click right at the start and end), then call the clip
// speech only if at least MIN_LOUD_SAMPLES readings (~300 ms) are louder than
// LOUD_DB. A single spike is not enough. Tune with the [recorder] log line.
const EDGE_IGNORE_MS = 300;
const LOUD_DB = -30;
const MIN_LOUD_SAMPLES = 3;

type LevelSample = { t: number; db: number };

function analyseLevels(samples: LevelSample[]) {
  const end = samples.length ? samples[samples.length - 1].t : 0;
  const middle = samples.filter((s) => s.t >= EDGE_IGNORE_MS && s.t <= end - EDGE_IGNORE_MS);
  const sorted = middle.map((s) => s.db).sort((a, b) => a - b);
  const loud = sorted.filter((db) => db > LOUD_DB).length;
  return {
    // No readings (metering unsupported, or a very short clip): don't block it.
    isSilent: sorted.length > 0 && loud < MIN_LOUD_SAMPLES,
    peak: sorted.length ? sorted[sorted.length - 1] : -160,
    median: sorted.length ? sorted[Math.floor(sorted.length / 2)] : -160,
    loud,
    total: sorted.length,
  };
}

// 'undetermined' = never asked; 'blocked' = denied and the OS won't show the
// prompt again, so the only way forward is the phone's Settings app.
export type MicPermission = 'undetermined' | 'granted' | 'denied' | 'blocked';

export type FinishedRecording = {
  uri: string;
  // True when the clip had no sustained loud section (see analyseLevels).
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
  // Level readings for the current recording. A ref (not state) because
  // adding to it should not redraw the screen.
  const levels = useRef<LevelSample[]>([]);

  useEffect(() => {
    const db = recorderState.metering;
    if (recorderState.isRecording && db !== undefined) {
      levels.current.push({ t: recorderState.durationMillis, db });
    }
  }, [recorderState.isRecording, recorderState.metering, recorderState.durationMillis]);

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
      levels.current = [];
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
      const a = analyseLevels(levels.current);
      // Shows in the `npx expo start` terminal; use it to tune LOUD_DB.
      if (__DEV__) {
        console.log(
          `[recorder] peak ${a.peak.toFixed(1)} dB, median ${a.median.toFixed(1)} dB, ` +
            `loud ${a.loud}/${a.total} → ${a.isSilent ? 'SILENT' : 'speech'}`,
        );
      }
      return { uri, isSilent: a.isSilent };
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
