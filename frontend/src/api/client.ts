import { supabase } from './supabase';

const API_BASE = '';

async function doFetch(url: string, options: RequestInit, token?: string): Promise<Response> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return fetch(`${API_BASE}${url}`, { ...options, headers });
}

export async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  let { data: { session } } = await supabase.auth.getSession();
  let res = await doFetch(url, options, session?.access_token);

  if (res.status === 401) {
    // one refresh + retry before giving up (handles a just-expired token / clock skew)
    const { data } = await supabase.auth.refreshSession();
    if (data.session?.access_token) {
      session = data.session;
      res = await doFetch(url, options, session.access_token);
    }
  }

  if (res.status === 401) {
    await supabase.auth.signOut();
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  return res;
}

// ======================== Utilities ========================

export function getRiskEmoji(level: string): string {
  const map: Record<string, string> = { low: '🟢', medium: '🟡', high: '🟠', critical: '🔴' };
  return map[level] || '⚪';
}

export function formatEventType(type: string): string {
  if (!type) return 'Unknown';
  return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

export function formatTime(timestamp: string | number): string {
  if (!timestamp) return '—';
  try {
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return String(timestamp);
    return date.toLocaleString('en-IN', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      day: '2-digit', month: 'short',
      hour12: false,
    });
  } catch {
    return String(timestamp);
  }
}
