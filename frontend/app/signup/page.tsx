'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { supabase } from '@/src/api/supabase';
import { pushToast } from '@/src/lib/toast';
import AuthShell from '@/src/components/auth/AuthShell';
import { Input, FieldLabel } from '@/src/components/ui/Field';
import { Button } from '@/src/components/ui/Button';

export default function SignupPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (process.env.NODE_ENV === 'production') {
    return (
      <AuthShell subtitle="Register new account">
        <p className="text-center text-[0.85rem] text-fg-muted">
          Self-service registration is disabled. Contact an administrator for access.
        </p>
        <p className="mt-4 text-center text-[0.8rem]">
          <Link href="/login" className="text-accent hover:text-accent-hover">Back to sign in</Link>
        </p>
      </AuthShell>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const email = identifier.includes('@') ? identifier : `${identifier}@ibvap.local`;
      const username = identifier.includes('@') ? identifier.split('@')[0] : identifier;
      const { error: authError } = await supabase.auth.signUp({
        email, password, options: { data: { username } },
      });
      if (authError) throw authError;
      pushToast({ title: 'Account created', message: 'Sign in to continue.' });
      router.replace('/login');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error signing up');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      subtitle="Register new account"
      footer={<p>Already have an account? <Link href="/login" className="text-accent hover:text-accent-hover">Sign in</Link></p>}
    >
      <form onSubmit={submit} className="space-y-4">
        <div>
          <FieldLabel icon="user">Username or email</FieldLabel>
          <Input type="text" value={identifier} onChange={e => setIdentifier(e.target.value)} required autoComplete="username" placeholder="operator@ibvap.gov" />
        </div>
        <div>
          <FieldLabel icon="lock">Password</FieldLabel>
          <Input type="password" value={password} onChange={e => setPassword(e.target.value)} required autoComplete="new-password" placeholder="Choose a password" />
        </div>
        {error && <p className="rounded-sm border border-danger/40 px-3 py-2 text-[0.8rem] text-danger">{error}</p>}
        <Button type="submit" variant="primary" size="md" block icon="user-plus" disabled={loading}>
          {loading ? 'Creating account…' : 'Sign up'}
        </Button>
      </form>
    </AuthShell>
  );
}
