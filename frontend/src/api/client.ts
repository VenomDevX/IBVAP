import { supabase } from './supabase';

const API_BASE = '';

/** Append the access token as a query param for <img>/<video> src (can't send a header). */
export function mediaSrc(path: string, token?: string | null): string {
  if (!token) return path;
  return path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);
}

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
  if (!timestamp && timestamp !== 0) return '—';
  try {
    let ms: number;
    if (typeof timestamp === 'number') {
      // epoch seconds vs milliseconds — some endpoints send seconds
      ms = timestamp < 1e12 ? timestamp * 1000 : timestamp;
    } else if (/^\d+(\.\d+)?$/.test(timestamp.trim())) {
      const n = parseFloat(timestamp);
      ms = n < 1e12 ? n * 1000 : n;
    } else {
      ms = new Date(timestamp).getTime();
    }
    const date = new Date(ms);
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
