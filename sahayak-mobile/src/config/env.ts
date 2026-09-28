// All environment configuration lives here, so the rest of the app never reads
// process.env directly.
//
// Expo only exposes variables prefixed with EXPO_PUBLIC_, and it copies their
// values into the JavaScript bundle at build time. That means:
//   - they must be written out literally as process.env.EXPO_PUBLIC_X
//     (destructuring or process.env[name] does not work), and
//   - after editing .env.local you must restart `npx expo start`.
//   - anyone who has the built app could extract them, so an API key here
//     is acceptable for a class demo but not for a real release.

export const env = {
  useMockStt: process.env.EXPO_PUBLIC_USE_MOCK_STT !== 'false',
  groqApiKey: process.env.EXPO_PUBLIC_GROQ_API_KEY ?? '',
  // Both default to the mock so the app works with no .env.local at all.
  useMockApi: process.env.EXPO_PUBLIC_USE_MOCK_API !== 'false',
  apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? '',
};
