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
  allowedAreas: string[] | null;
  profileError: boolean;
  mediaTicket: string | null;
  loading: boolean;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<AppRole>(null);
  const [allowedAreas, setAllowedAreas] = useState<string[] | null>(null);
  const [profileError, setProfileError] = useState(false);
  const [mediaTicket, setMediaTicket] = useState<string | null>(null);
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
    if (!session) { setRole(null); setAllowedAreas(null); setMediaTicket(null); setProfileError(false); return; }
    setProfileError(false);
    const loadProfile = async () => {
      try {
        const response = await apiFetch('/api/auth/me');
        if (!response.ok) throw new Error('Profile unavailable');
        const me = await response.json();
        if (!cancelled) { setRole((me?.role as AppRole) ?? null); setAllowedAreas(Array.isArray(me?.allowed_areas) ? me.allowed_areas : null); }
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
      } catch { if (!cancelled) setMediaTicket(null); }
    };
    void loadProfile();
    void refreshTicket();
    const ticketTimer = window.setInterval(() => void refreshTicket(), 90_000);
    return () => { cancelled = true; window.clearInterval(ticketTimer); };
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
    <AuthContext.Provider value={{ isAuthenticated, user, session, role, allowedAreas, profileError, mediaTicket, loading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
