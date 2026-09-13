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
    if (!identifier || !password) {
      setError('Please enter both email and password.');
      return;
    }
    
    setLoading(true);
    setError('');
    
    try {
      const email = identifier.includes('@') ? identifier : `${identifier}@ibvap.local`;
      const { data, error: authError } = await supabase.auth.signInWithPassword({ email, password });
      
      if (authError) {
        throw new Error(authError.message === 'Invalid login credentials' ? 'Incorrect email or password.' : authError.message);
      }
      if (!data.user) {
        throw new Error('Authentication failed. Server unreachable.');
      }
      
      // Successfully authenticated. The AuthContext onAuthStateChange will pick it up.
      // We don't unset loading here so the button stays spinning until the page redirects.
      router.replace('/');
    } catch (err) {
      setLoading(false);
      setError(err instanceof Error ? err.message : 'An unexpected error occurred during login.');
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
          <div className="rounded-lg border border-danger/40 bg-danger/5 px-4 py-3 flex items-center gap-3 text-[0.85rem] text-danger shadow-sm">
            <svg className="w-5 h-5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <p className="font-medium">{error}</p>
          </div>
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
