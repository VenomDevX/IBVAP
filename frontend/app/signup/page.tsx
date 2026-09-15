'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { supabase } from '@/src/api/supabase';
import AuthShell from '@/src/components/auth/AuthShell';
import { Field, Input } from '@/src/components/ui/Field';
import { Button } from '@/src/components/ui/Button';
import { InlineError } from '@/src/components/ui/States';

export default function SignupPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (process.env.NODE_ENV === 'production') {
    return (
      <AuthShell title="Create an account" footer={<Link href="/login" className="font-medium text-accent hover:text-accent-hover">Back to sign in</Link>}>
        <p className="text-sm text-muted">Self-service registration is disabled. Ask an administrator for access.</p>
      </AuthShell>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const value = identifier.trim();
      const email = value.includes('@') ? value : `${value}@ibvap.local`;
      const username = value.includes('@') ? value.split('@')[0] : value;
      const { error: authError } = await supabase.auth.signUp({ email, password, options: { data: { username } } });
      if (authError) throw authError;
      router.replace('/login');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the account. Try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Create an account"
      description="Development builds only. An administrator assigns your role afterwards."
      footer={<>Already have an account? <Link href="/login" className="font-medium text-accent hover:text-accent-hover">Sign in</Link></>}
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="Username or email" htmlFor="identifier">
          <Input id="identifier" name="username" type="text" value={identifier} onChange={e => setIdentifier(e.target.value)}
            required autoComplete="username" spellCheck={false} autoCapitalize="none" placeholder="operator@ibvap.gov" />
        </Field>
        <Field label="Password" htmlFor="password" hint="At least 6 characters.">
          <Input id="password" name="password" type="password" value={password} onChange={e => setPassword(e.target.value)}
            required minLength={6} autoComplete="new-password" placeholder="Choose a password" />
        </Field>
        {error && <InlineError>{error}</InlineError>}
        <Button type="submit" variant="primary" className="h-9 w-full" loading={submitting}>
          {submitting ? 'Creating account…' : 'Sign up'}
        </Button>
      </form>
    </AuthShell>
  );
}
