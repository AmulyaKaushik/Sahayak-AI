import { AuthForm } from '@/components/auth-form';

// Route "/login". Groups in parentheses, like "(auth)", don't appear in the URL.
export default function LoginScreen() {
  return <AuthForm mode="login" />;
}
