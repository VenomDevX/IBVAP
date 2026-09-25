'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '../api/supabase';
import { apiFetch } from '../api/client';

export type AppRole = 'admin' | 'commander' | 'operator' | 'viewer' | 'supervisor' | 'auditor' | null;

interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  session: Session | null;
  role: AppRole;
  allowedAreas: string[] | null;
  profileError: boolean;
  mediaTicket: string | null;
  loading: boolean;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

/**
 * Whether this user must enter a 6-digit code at sign-in. An admin sets it per user
 * (Settings → Users); users can read but not change their own. Unknown means yes.
 */
export async function mfaRequiredFor(userId: string) {
  const { data, error } = await supabase.from('user_profiles').select('mfa_required').eq('id', userId).maybeSingle();
  return error || !data ? true : data.mfa_required !== false;
}

/** True once the session has passed the TOTP step. */
function hasSecondFactor(session: Session | null) {
  if (!session) return false;
  try {
    const part = session.access_token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(part)).aal === 'aal2';
  } catch {
    return false;
  }
}

/** Roles the backend accepts for PATCH /api/alerts/{id}. */
export function canManageAlerts(role: AppRole) {
  return role === 'admin' || role === 'commander' || role === 'supervisor' || role === 'operator';
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<AppRole>(null);
  const [allowedAreas, setAllowedAreas] = useState<string[] | null>(null);
  const [profileError, setProfileError] = useState(false);
  const [mediaTicket, setMediaTicket] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // For a password-only session: whether an admin exempted this user from the code step.
  const [mfaCheck, setMfaCheck] = useState<{ userId: string; exempt: boolean } | null>(null);

  useEffect(() => {
    supabase.auth.getSession()
      .then(({ data }) => {
        setSession(data.session);
        setUser(data.session?.user ?? null);
      })
      .catch(e => console.error('getSession failed:', e))
      .finally(() => setLoading(false));

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setUser(next?.user ?? null);
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  // The application role lives in user_profiles, not in the JWT.
  const accessToken = session?.access_token ?? null;
  const secondFactor = hasSecondFactor(session);
  const sessionUserId = session?.user.id ?? null;
  useEffect(() => {
    if (!sessionUserId || secondFactor) return;
    let cancelled = false;
    void mfaRequiredFor(sessionUserId).then(required => {
      if (!cancelled) setMfaCheck({ userId: sessionUserId, exempt: !required });
    });
    return () => { cancelled = true; };
  }, [sessionUserId, secondFactor]);
  const mfaExempt = mfaCheck && mfaCheck.userId === sessionUserId ? mfaCheck.exempt : null;
  const hasSession = secondFactor || mfaExempt === true;
  const checkingMfa = !!session && !secondFactor && mfaExempt === null;

  useEffect(() => {
    let cancelled = false;
    if (!hasSession) {
      setRole(null); setAllowedAreas(null); setMediaTicket(null); setProfileError(false);
      return;
    }
    setProfileError(false);
    const loadProfile = async () => {
      try {
        const response = await apiFetch('/api/auth/me');
        if (!response.ok) throw new Error('Profile unavailable');
        const me = await response.json();
        if (!cancelled) {
          setRole((me?.role as AppRole) ?? null);
          setAllowedAreas(Array.isArray(me?.allowed_areas) ? me.allowed_areas : null);
        }
      } catch {
        if (!cancelled) { setRole(null); setAllowedAreas(null); setProfileError(true); }
      }
    };
    const refreshTicket = async () => {
      try {
        const response = await apiFetch('/api/auth/media-ticket', { method: 'POST' });
        if (!response.ok) throw new Error('Media ticket unavailable');
        const data = await response.json();
        if (!cancelled) setMediaTicket(data.ticket ?? null);
      } catch {
        if (!cancelled) setMediaTicket(null);
      }
    };
    void loadProfile();
    void refreshTicket();
    const ticketTimer = window.setInterval(() => void refreshTicket(), 90_000);
    return () => { cancelled = true; window.clearInterval(ticketTimer); };
    // Re-run when the user changes, not on every silent token refresh.
  }, [hasSession, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  void accessToken;

  const logout = useCallback(async () => {
    // Revoke the access token server-side first; a plain signOut only clears the browser.
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch {
      /* best effort, sign out locally regardless */
    }
    await supabase.auth.signOut();
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated: hasSession, user, session, role, allowedAreas, profileError, mediaTicket, loading: loading || checkingMfa, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
