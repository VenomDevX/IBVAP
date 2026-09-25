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
  // Two-step verification: 'code' for an enrolled user, 'enroll' the first time.
  const [step, setStep] = useState<'password' | 'code' | 'enroll'>('password');
  const [factorId, setFactorId] = useState('');
  const [enrollment, setEnrollment] = useState<{ qr: string; secret: string } | null>(null);
  const [code, setCode] = useState('');

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

      const { data: factors, error: factorError } = await supabase.auth.mfa.listFactors();
      if (factorError) throw factorError;
      const verified = factors.totp[0];
      if (verified) {
        setFactorId(verified.id);
        setStep('code');
      } else {
        // Clear half-finished enrollments so they don't pile up against the factor limit.
        for (const f of factors.all.filter(f => f.status === 'unverified')) {
          await supabase.auth.mfa.unenroll({ factorId: f.id });
        }
        const { data: enrolled, error: enrollError } = await supabase.auth.mfa.enroll({ factorType: 'totp' });
        if (enrollError) throw enrollError;
        setFactorId(enrolled.id);
        setEnrollment({ qr: enrolled.totp.qr_code, secret: enrolled.totp.secret });
        setStep('enroll');
      }
      setSubmitting(false);
    } catch (err) {
      setSubmitting(false);
      setError(err instanceof Error ? err.message : 'Sign-in failed. Try again.');
    }
  };

  const verify = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    const { error: verifyError } = await supabase.auth.mfa.challengeAndVerify({ factorId, code: code.trim() });
    if (verifyError) {
      setSubmitting(false);
      setCode('');
      setError(verifyError.message.toLowerCase().includes('invalid')
        ? 'That code is wrong or has expired. Enter the current code from your app.'
        : verifyError.message);
      return;
    }
    router.replace('/');
  };

  const cancel = async () => {
    await supabase.auth.signOut();
    setStep('password'); setCode(''); setEnrollment(null); setError(''); setPassword('');
  };

  if (step !== 'password') {
    return (
      <AuthShell
        title={step === 'enroll' ? 'Set up two-step verification' : 'Enter verification code'}
        description={step === 'enroll'
          ? 'Scan this code with an authenticator app (Google Authenticator, Authy, Microsoft Authenticator), then enter the 6-digit code it shows.'
          : 'Open your authenticator app and enter the 6-digit code for IBVAP.'}
      >
        {step === 'enroll' && enrollment && (
          <div className="mb-5 space-y-3">
            <img src={enrollment.qr} alt="QR code for your authenticator app" width={176} height={176}
              className="mx-auto rounded-md bg-white p-2" />
            <p className="text-center text-xs text-muted">
              Can't scan? Enter this key manually:
              <code className="mt-1 block select-all break-all font-mono text-fg">{enrollment.secret}</code>
            </p>
          </div>
        )}
        <form onSubmit={verify} className="space-y-4">
          <Field label="6-digit code" htmlFor="otp">
            <Input
              id="otp" name="otp" type="text" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
              required inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6}
              autoFocus placeholder="123456"
            />
          </Field>
          {error && <InlineError>{error}</InlineError>}
          <Button type="submit" variant="primary" className="h-9 w-full" loading={submitting} disabled={code.length !== 6}>
            {submitting ? 'Verifying…' : 'Verify'}
          </Button>
          <button type="button" onClick={() => void cancel()}
            className="w-full text-center text-sm text-muted hover:text-fg">
            Use a different account
          </button>
        </form>
      </AuthShell>
    );
  }

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
