'use client';

import { Suspense, useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { supabase } from '@/src/api/supabase';
import { useAuth } from '@/src/context/AuthContext';
import AuthShell from '@/src/components/auth/AuthShell';
import { Input, FieldLabel } from '@/src/components/ui/Field';
import { Button } from '@/src/components/ui/Button';

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { isAuthenticated } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) router.replace('/');
  }, [isAuthenticated, router]);

  const timedOut = params.get('timeout') === '1';

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const email = identifier.includes('@') ? identifier : `${identifier}@ibvap.local`;
      const { error: authError } = await supabase.auth.signInWithPassword({ email, password });
      if (authError) throw authError;
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      subtitle="Intelligent Border Video Analytics Platform"
      footer={
        <>
          <p>Authorized personnel only</p>
          {process.env.NODE_ENV !== 'production' && (
            <p className="mt-2"><Link href="/signup" className="text-accent hover:text-accent-hover">Create an account</Link></p>
          )}
        </>
      }
    >
      {timedOut && (
        <p className="mb-4 rounded-sm border border-warning/40 px-3 py-2 text-[0.8rem] text-warning">
          Your session timed out. Sign in again to continue.
        </p>
      )}
      <form onSubmit={submit} className="space-y-4">
        <div>
          <FieldLabel icon="user">Username or email</FieldLabel>
          <Input
            type="text" value={identifier} onChange={e => setIdentifier(e.target.value)}
            required autoComplete="username" placeholder="operator@ibvap.gov"
          />
        </div>
        <div>
          <FieldLabel icon="lock">Password</FieldLabel>
          <Input
            type="password" value={password} onChange={e => setPassword(e.target.value)}
            required autoComplete="current-password" placeholder="Enter password"
          />
        </div>
        {error && (
          <p className="rounded-sm border border-danger/40 px-3 py-2 text-[0.8rem] text-danger">{error}</p>
        )}
        <Button type="submit" variant="primary" size="md" block icon={loading ? 'spinner' : 'right-to-bracket'} disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
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
