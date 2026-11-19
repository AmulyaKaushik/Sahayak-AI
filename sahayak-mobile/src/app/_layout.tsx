import Ionicons from '@expo/vector-icons/Ionicons';
import { Link, Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/constants/colors';
import { useAuth } from '@/store/auth';
import { useConnectivityMonitor } from '@/store/connectivity';

// Root layout: wraps every screen in src/app/. A <Stack> navigator pushes
// screens on top of each other (with a back button), like pages in a browser.
//
// Stack.Protected decides which screens exist right now. When `guard` turns
// false (e.g. on logout) its screens are removed and the user is sent to the
// first screen that is still allowed, so there's no manual redirect code.
export default function RootLayout() {
  // App-wide: watch network + backend health for the offline banner. Its
  // first /health ping also wakes the free server while the user signs in.
  useConnectivityMonitor();

  const status = useAuth((s) => s.status);
  const profileCompleted = useAuth((s) => s.profileCompleted);
  const logout = useAuth((s) => s.logout);

  // Read the saved login (secure storage) once on launch.
  useEffect(() => {
    useAuth.getState().restore();
  }, []);

  if (status === 'loading') {
    return (
      <View style={styles.splash}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  const signedIn = status === 'signedIn';

  return (
    <>
      <StatusBar style="auto" />
      {/* iOS 26 draws headers transparent with content underneath; keep them
          opaque so nothing is hidden behind the header. */}
      <Stack screenOptions={{ headerTransparent: false }}>
        <Stack.Protected guard={!signedIn}>
          <Stack.Screen name="(auth)" options={{ headerShown: false }} />
        </Stack.Protected>

        <Stack.Protected guard={signedIn && !profileCompleted}>
          <Stack.Screen
            name="onboarding"
            options={{
              title: 'About you',
              headerRight: () => (
                <Pressable onPress={logout} hitSlop={12} accessibilityRole="button">
                  <Text style={styles.headerLink}>Sign out</Text>
                </Pressable>
              ),
            }}
          />
        </Stack.Protected>

        <Stack.Protected guard={signedIn && profileCompleted}>
          <Stack.Screen
            name="index"
            options={{
              title: 'Sahayak AI',
              headerRight: () => (
                <View style={styles.headerIcons}>
                  <Link href="/profile" asChild>
                    <Pressable hitSlop={12} accessibilityLabel="My details">
                      <Ionicons name="person-circle-outline" size={26} color={colors.primary} />
                    </Pressable>
                  </Link>
                  <Link href="/settings" asChild>
                    <Pressable hitSlop={12} accessibilityLabel="Settings">
                      <Ionicons name="settings-outline" size={24} color={colors.primary} />
                    </Pressable>
                  </Link>
                </View>
              ),
            }}
          />
          <Stack.Screen name="profile" options={{ title: 'My details' }} />
          <Stack.Screen name="settings" options={{ title: 'Settings' }} />
        </Stack.Protected>
      </Stack>
    </>
  );
}

const styles = StyleSheet.create({
  splash: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background },
  headerIcons: { flexDirection: 'row', alignItems: 'center', gap: 18 },
  headerLink: { color: colors.primary, fontSize: 16, fontWeight: '600' },
});
