import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

// User preferences, saved on the phone (AsyncStorage = a small key-value store
// that survives app restarts) via Zustand's persist middleware.

// 'auto' lets Whisper detect the language; otherwise it is told which
// language to expect, which improves accuracy for short or mixed sentences.
export type SpokenLanguage = 'auto' | 'hi-IN' | 'en-IN';

export const LANGUAGE_OPTIONS: { value: SpokenLanguage; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'hi-IN', label: 'हिंदी' },
  { value: 'en-IN', label: 'English' },
];

type SettingsState = {
  spokenLanguage: SpokenLanguage;
  setSpokenLanguage: (language: SpokenLanguage) => void;
};

export const useSettings = create<SettingsState>()(
  persist(
    (set) => ({
      spokenLanguage: 'auto',
      setSpokenLanguage: (spokenLanguage) => set({ spokenLanguage }),
    }),
    {
      name: 'sahayak-settings',
      storage: createJSONStorage(() => AsyncStorage),
    },
  ),
);
