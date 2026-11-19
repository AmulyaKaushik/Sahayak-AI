import { Stack } from 'expo-router';

// Screens shown while signed out. The root layout only mounts this group when
// nobody is signed in (see Stack.Protected in ../_layout.tsx).
export default function AuthLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="login" />
      <Stack.Screen name="register" />
    </Stack>
  );
}
