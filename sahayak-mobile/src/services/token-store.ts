import * as SecureStore from 'expo-secure-store';

// Login tokens, kept in the phone's secure storage (iOS Keychain / Android
// Keystore). Never put tokens in AsyncStorage: that is a plain file any
// backup or rooted phone can read.
//
// Each value goes in its own key because some iOS versions reject secure-store
// values over ~2 KB. A copy is cached in memory so the API client doesn't hit
// the Keychain on every request.

export type Tokens = { accessToken: string; refreshToken: string };

// Non-secret account info saved alongside, so the app can restore the signed-in
// screen instantly on launch, before the (possibly sleeping) server answers.
export type Account = { customerId: string; loginId: string; profileCompleted: boolean };

const ACCESS_KEY = 'sahayak.accessToken';
const REFRESH_KEY = 'sahayak.refreshToken';
const ACCOUNT_KEY = 'sahayak.account';

let cache: Tokens | null = null;

export async function getTokens(): Promise<Tokens | null> {
  if (cache) return cache;
  const [accessToken, refreshToken] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_KEY),
    SecureStore.getItemAsync(REFRESH_KEY),
  ]);
  cache = accessToken && refreshToken ? { accessToken, refreshToken } : null;
  return cache;
}

export async function saveTokens(tokens: Tokens): Promise<void> {
  cache = tokens;
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, tokens.accessToken),
    SecureStore.setItemAsync(REFRESH_KEY, tokens.refreshToken),
  ]);
}

export async function getAccount(): Promise<Account | null> {
  const raw = await SecureStore.getItemAsync(ACCOUNT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Account;
  } catch {
    return null;
  }
}

export async function saveAccount(account: Account): Promise<void> {
  await SecureStore.setItemAsync(ACCOUNT_KEY, JSON.stringify(account));
}

export async function clearTokens(): Promise<void> {
  cache = null;
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
    SecureStore.deleteItemAsync(ACCOUNT_KEY),
  ]);
}
