import * as Speech from 'expo-speech';

// Text-to-speech using the phone's built-in voices (expo-speech): no network,
// no API key. Which languages are available depends on the phone and on the
// voice packs the user has installed, so always test on the demo device.

let voicesPromise: Promise<Speech.Voice[]> | null = null;
function getVoices() {
  voicesPromise ??= Speech.getAvailableVoicesAsync().catch(() => []);
  return voicesPromise;
}

// Best installed voice for a BCP-47 tag like "hi-IN": exact match first, then
// the same base language ("hi-*"), preferring Enhanced (higher quality) voices.
async function findVoice(language: string): Promise<Speech.Voice | undefined> {
  const voices = await getVoices();
  const norm = (tag: string) => tag.replace('_', '-').toLowerCase();
  const wanted = norm(language);
  const base = wanted.split('-')[0];
  const exact = voices.filter((v) => norm(v.language) === wanted);
  const candidates = exact.length
    ? exact
    : voices.filter((v) => norm(v.language).split('-')[0] === base);
  return (
    candidates.find((v) => v.quality === Speech.VoiceQuality.Enhanced) ?? candidates[0]
  );
}

// true / false, or null when the phone didn't report its voices (some Android
// phones return an empty list until the TTS engine has warmed up).
export async function hasVoiceFor(language: string): Promise<boolean | null> {
  if ((await getVoices()).length === 0) return null;
  return (await findVoice(language)) !== undefined;
}

// Speaks `text`, stopping anything already being spoken first (otherwise
// expo-speech queues it). onFinish runs exactly once: when speech ends, is
// stopped, or fails.
export async function speak(
  text: string,
  language: string,
  onFinish: (error?: Error) => void,
): Promise<void> {
  await Speech.stop();
  const voice = await findVoice(language);
  let finished = false;
  const finish = (error?: Error) => {
    if (finished) return;
    finished = true;
    onFinish(error);
  };
  Speech.speak(text.slice(0, Speech.maxSpeechInputLength), {
    language,
    voice: voice?.identifier,
    onDone: () => finish(),
    onStopped: () => finish(),
    onError: (e) => finish(e),
  });
}

export async function stopSpeaking(): Promise<void> {
  await Speech.stop();
}
