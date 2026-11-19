import Ionicons from '@expo/vector-icons/Ionicons';
import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { NoticeCard } from '@/components/notice-card';
import { colors } from '@/constants/colors';
import { env } from '@/config/env';
import { useAuth } from '@/store/auth';

const MIN_PASSWORD = 8; // the backend rejects shorter ones
// A sleeping free server needs up to a minute to answer the first request.
const SLOW_AFTER_MS = 5000;

// Shared by the Login and Register screens.
export function AuthForm({ mode }: { mode: 'login' | 'register' }) {
  const login = useAuth((s) => s.login);
  const register = useAuth((s) => s.register);
  const insets = useSafeAreaInsets();

  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isRegister = mode === 'register';

  useEffect(() => {
    if (!busy) return;
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => {
      clearTimeout(timer);
      setSlow(false);
    };
  }, [busy]);

  function validate(): string | null {
    if (loginId.trim().length < 3) return 'Enter your phone number or email.';
    if (password.length < MIN_PASSWORD) return `Password must be at least ${MIN_PASSWORD} characters.`;
    if (isRegister && password !== confirm) return 'The two passwords do not match.';
    return null;
  }

  async function submit() {
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await (isRegister ? register : login)(loginId, password);
      // Success: the root layout's route guard switches screens by itself.
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        style={styles.flex}
        contentContainerStyle={[styles.content, { paddingTop: insets.top + 32 }]}
        keyboardShouldPersistTaps="handled">
        <View style={styles.logo}>
          <Ionicons name="chatbubbles" size={48} color={colors.primary} />
        </View>
        <Text style={styles.title}>{isRegister ? 'Create your account' : 'Welcome to Sahayak AI'}</Text>
        <Text style={styles.subtitle}>
          {isRegister
            ? 'Your details are saved to this account so Sahayak remembers them.'
            : 'Sign in to ask about loans and government schemes.'}
        </Text>
        {env.useMockApi && (
          <Text style={styles.mock}>MOCK backend: any login works (password ≥ 8 characters).</Text>
        )}

        <Text style={styles.label}>Phone number or email</Text>
        <TextInput
          value={loginId}
          onChangeText={setLoginId}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="username"
          textContentType="username"
          keyboardType="email-address"
          placeholder="9876543210 or name@example.com"
          placeholderTextColor={colors.textFaint}
          style={styles.input}
          editable={!busy}
        />

        <Text style={styles.label}>Password</Text>
        <View>
          <TextInput
            value={password}
            onChangeText={setPassword}
            secureTextEntry={!showPassword}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete={isRegister ? 'new-password' : 'current-password'}
            textContentType={isRegister ? 'newPassword' : 'password'}
            placeholder={`At least ${MIN_PASSWORD} characters`}
            placeholderTextColor={colors.textFaint}
            style={[styles.input, styles.passwordInput]}
            editable={!busy}
            onSubmitEditing={isRegister ? undefined : submit}
          />
          <Pressable
            onPress={() => setShowPassword((v) => !v)}
            hitSlop={8}
            style={styles.eye}
            accessibilityLabel={showPassword ? 'Hide password' : 'Show password'}>
            <Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={22} color={colors.textMuted} />
          </Pressable>
        </View>

        {isRegister && (
          <>
            <Text style={styles.label}>Confirm password</Text>
            <TextInput
              value={confirm}
              onChangeText={setConfirm}
              secureTextEntry={!showPassword}
              autoCapitalize="none"
              autoCorrect={false}
              textContentType="newPassword"
              style={styles.input}
              editable={!busy}
              onSubmitEditing={submit}
            />
          </>
        )}

        <Text style={styles.privacy}>
          Sahayak will never ask for your bank PIN, OTP or card number.
        </Text>

        {error && <NoticeCard tone="danger" message={error} />}

        <Pressable
          onPress={submit}
          disabled={busy}
          style={({ pressed }) => [styles.primary, (pressed || busy) && styles.dimmed]}>
          {busy ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.primaryText}>{isRegister ? 'Create account' : 'Sign in'}</Text>
          )}
        </Pressable>
        {slow && (
          <Text style={styles.slow}>
            Waking up the Sahayak server… the first sign-in can take up to a minute.
          </Text>
        )}

        <View style={styles.switchRow}>
          <Text style={styles.switchText}>
            {isRegister ? 'Already have an account?' : 'New to Sahayak?'}
          </Text>
          <Link href={isRegister ? '/login' : '/register'} replace asChild>
            <Pressable hitSlop={8} disabled={busy}>
              <Text style={styles.switchLink}>{isRegister ? 'Sign in' : 'Create an account'}</Text>
            </Pressable>
          </Link>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  content: { paddingHorizontal: 24, paddingBottom: 48 },
  logo: {
    alignSelf: 'center',
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  title: { fontSize: 26, fontWeight: '800', color: colors.text, textAlign: 'center' },
  subtitle: {
    fontSize: 15,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    marginBottom: 12,
    lineHeight: 22,
  },
  mock: {
    alignSelf: 'center',
    fontSize: 12,
    fontWeight: '700',
    color: colors.warning,
    backgroundColor: colors.warningSoft,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    overflow: 'hidden',
    marginBottom: 4,
  },
  label: { fontSize: 15, fontWeight: '600', color: colors.text, marginTop: 16, marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 13,
    fontSize: 17,
    color: colors.text,
    backgroundColor: colors.surface,
  },
  passwordInput: { paddingRight: 48 },
  eye: { position: 'absolute', right: 12, top: 0, bottom: 0, justifyContent: 'center' },
  privacy: { fontSize: 13, color: colors.textMuted, marginTop: 16, marginBottom: 12 },
  primary: {
    backgroundColor: colors.primary,
    borderRadius: 10,
    paddingVertical: 15,
    alignItems: 'center',
    marginTop: 4,
  },
  primaryText: { color: '#fff', fontSize: 17, fontWeight: '700' },
  dimmed: { opacity: 0.7 },
  slow: { fontSize: 14, color: colors.warning, textAlign: 'center', marginTop: 12, lineHeight: 20 },
  switchRow: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginTop: 24 },
  switchText: { fontSize: 15, color: colors.textMuted },
  switchLink: { fontSize: 15, color: colors.primary, fontWeight: '700' },
});
