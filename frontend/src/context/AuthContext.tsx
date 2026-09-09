'use client';

import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { supabase } from '../api/supabase';
import { apiFetch } from '../api/client';
import type { User, Session } from '@supabase/supabase-js';

type AppRole = 'admin' | 'operator' | 'auditor' | null;

interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  session: Session | null;
  role: AppRole;
  loading: boolean;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<AppRole>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession()
      .then(({ data: { session } }) => {
        setSession(session);
        setUser(session?.user ?? null);
      })
      .catch((e) => console.error('getSession failed:', e))
      .finally(() => setLoading(false));

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  // Resolve the application role (lives in user_profiles, not the JWT) whenever we have a session.
  useEffect(() => {
    let cancelled = false;
    if (!session) { setRole(null); return; }
    apiFetch('/api/auth/me')
      .then(r => r.json())
      .then(me => { if (!cancelled) setRole((me?.role as AppRole) ?? 'operator'); })
      .catch(() => { if (!cancelled) setRole('operator'); });
    return () => { cancelled = true; };
  }, [session]);

  const logout = async () => {
    // Revoke the access token server-side first (a plain signOut only clears the
    // browser; the JWT stays valid for the rest of its ~1h life otherwise).
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch {
      /* best effort — sign out locally regardless */
    }
    await supabase.auth.signOut();
  };

  const isAuthenticated = !!user;

  return (
    <AuthContext.Provider value={{ isAuthenticated, user, session, role, loading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
