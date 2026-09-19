'use client';

import { Suspense, useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { supabase } from '@/src/api/supabase';
import { useAuth } from '@/src/context/AuthContext';
import AuthShell from '@/src/components/auth/AuthShell';
import { Field, Input } from '@/src/components/ui/Field';
import { Button } from '@/src/components/ui/Button';
import { InlineError } from '@/src/components/ui/States';

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { isAuthenticated } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isAuthenticated) router.replace('/');
  }, [isAuthenticated, router]);

  const timedOut = params.get('timeout') === '1';

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const email = identifier.includes('@') ? identifier.trim() : `${identifier.trim()}@ibvap.local`;
      const { data, error: authError } = await supabase.auth.signInWithPassword({ email, password });
      if (authError) {
        throw new Error(authError.message === 'Invalid login credentials'
          ? 'Incorrect email or password. Check both and try again.'
          : authError.message);
      }
      if (!data.user) throw new Error('The sign-in service did not respond. Try again in a moment.');
      router.replace('/');
    } catch (err) {
      setSubmitting(false);
      setError(err instanceof Error ? err.message : 'Sign-in failed. Try again.');
    }
  };

  return (
    <AuthShell
      title="Sign in"
      description="Border video analytics console for authorised personnel."
      footer={process.env.NODE_ENV !== 'production' && (
        <>No account yet? <Link href="/signup" className="font-medium text-accent hover:text-accent-hover">Create one</Link></>
      )}
    >
      {timedOut && (
        <p className="mb-5 rounded-md bg-warn/10 px-3 py-2 text-sm text-fg">
          You were signed out after 30 minutes of inactivity. Sign in again to continue.
        </p>
      )}
      <form onSubmit={submit} className="space-y-4" noValidate={false}>
        <Field label="Username or email" htmlFor="identifier">
          <Input
            id="identifier" name="username" type="text" value={identifier} onChange={e => setIdentifier(e.target.value)}
            required autoComplete="username" spellCheck={false} autoCapitalize="none" placeholder="operator@ibvap.gov"
          />
        </Field>
        <Field label="Password" htmlFor="password">
          <Input
            id="password" name="password" type="password" value={password} onChange={e => setPassword(e.target.value)}
            required autoComplete="current-password" placeholder="Enter password"
          />
        </Field>
        {error && <InlineError>{error}</InlineError>}
        <Button type="submit" variant="primary" className="h-9 w-full" loading={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </AuthShell>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
