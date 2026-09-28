import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

// Root layout: wraps every screen in src/app/. A <Stack> navigator pushes
// screens on top of each other (with a back button), like pages in a browser.
export default function RootLayout() {
  return (
    <>
      <StatusBar style="auto" />
      <Stack>
        <Stack.Screen name="index" options={{ title: 'Sahayak AI' }} />
        <Stack.Screen name="settings" options={{ title: 'Settings' }} />
      </Stack>
    </>
  );
}
