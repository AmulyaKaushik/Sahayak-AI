import { Redirect } from 'expo-router';

import { useAuth } from '@/store/auth';

// Expo Router shows this for any URL with no screen. That includes "/" while
// signed out (the chat screen owns "/" but only exists once you are signed in),
// which is where the app opens, so send people to the right place instead of
// an error page.
export default function NotFound() {
  const status = useAuth((s) => s.status);
  const profileCompleted = useAuth((s) => s.profileCompleted);

  if (status === 'signedIn') return <Redirect href={profileCompleted ? '/' : '/onboarding'} />;
  return <Redirect href="/login" />;
}
