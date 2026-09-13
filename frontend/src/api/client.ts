import { supabase } from './supabase';
import type { RiskLevel } from '../types';

/**
 * Dev: the browser calls the backend cross-origin (backend CORS allows :3001).
 * Prod: empty — nginx serves the static app and proxies /api on the same origin.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? '';

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** Append a short-lived, media-only ticket for native <img>/<video> requests. */
export function mediaSrc(path: string, ticket?: string | null): string {
  const url = apiUrl(path);
  if (!ticket) return url;
  return url + (url.includes('?') ? '&' : '?') + 'ticket=' + encodeURIComponent(ticket);
}

async function doFetch(url: string, options: RequestInit, token?: string): Promise<Response> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string>) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return fetch(apiUrl(url), { ...options, headers });
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
    if (typeof window !== 'undefined') window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  return res;
}

// ======================== Risk coding ========================

export interface RiskMeta {
  /** stable key, also the Tailwind colour suffix: text-risk-<key> / bg-risk-<key> */
  key: RiskLevel | 'unknown';
  label: string;
  /** resolved CSS colour, for inline dots / chart series */
  color: string;
}

export const RISK_META: Record<RiskMeta['key'], RiskMeta> = {
  low: { key: 'low', label: 'Low', color: 'var(--risk-low)' },
  medium: { key: 'medium', label: 'Medium', color: 'var(--risk-medium)' },
  high: { key: 'high', label: 'High', color: 'var(--risk-high)' },
  critical: { key: 'critical', label: 'Critical', color: 'var(--risk-critical)' },
  unknown: { key: 'unknown', label: 'Unknown', color: 'var(--risk-unknown)' },
};

export function riskMeta(level: string | null | undefined): RiskMeta {
  return RISK_META[(level ?? '') as RiskMeta['key']] ?? RISK_META.unknown;
}

// ======================== Formatting ========================

export function formatEventType(type: string): string {
  if (!type) return 'Unknown';
  return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

export function formatTime(timestamp: string | number): string {
  if (!timestamp && timestamp !== 0) return '—';
  try {
    let ms: number;
    if (typeof timestamp === 'number') {
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
