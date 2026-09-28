import Ionicons from '@expo/vector-icons/Ionicons';
import { Link, Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Pressable } from 'react-native';

import { colors } from '@/constants/colors';
import { useConnectivityMonitor } from '@/store/connectivity';

// Root layout: wraps every screen in src/app/. A <Stack> navigator pushes
// screens on top of each other (with a back button), like pages in a browser.
export default function RootLayout() {
  // App-wide: watch network + backend health for the offline banner.
  useConnectivityMonitor();

  return (
    <>
      <StatusBar style="auto" />
      <Stack>
        <Stack.Screen
          name="index"
          options={{
            title: 'Sahayak AI',
            headerRight: () => (
              <Link href="/settings" asChild>
                <Pressable hitSlop={12} accessibilityLabel="Settings">
                  <Ionicons name="settings-outline" size={24} color={colors.primary} />
                </Pressable>
              </Link>
            ),
          }}
        />
        <Stack.Screen name="settings" options={{ title: 'Settings' }} />
      </Stack>
    </>
  );
}
