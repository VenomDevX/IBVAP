import { supabase } from './supabase';
import type { RiskLevel } from '../types';

/**
 * Dev: the browser calls the backend cross-origin (backend CORS allows :3001).
 * Prod: empty, so requests go to the same origin and nginx proxies /api.
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
  const { data: { session } } = await supabase.auth.getSession();
  let res = await doFetch(url, options, session?.access_token);

  if (res.status === 401) {
    // One refresh + retry before giving up (just-expired token or clock skew).
    const { data } = await supabase.auth.refreshSession();
    if (data.session?.access_token) {
      res = await doFetch(url, options, data.session.access_token);
    }
  }

  if (res.status === 401) {
    await supabase.auth.signOut();
    if (typeof window !== 'undefined') window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  return res;
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function readError(res: Response): Promise<string> {
  const text = await res.text().catch(() => '');
  try {
    const body = JSON.parse(text);
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail) && body.detail[0]?.msg) return String(body.detail[0].msg);
  } catch {
    /* not JSON */
  }
  return text || `Request failed with status ${res.status}`;
}

/** Fetch JSON and throw on non-2xx, so an error body is never used as data. */
export async function apiJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await apiFetch(url, options);
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return res.json() as Promise<T>;
}

/** POST/PATCH/DELETE with an optional JSON body. */
export function apiSend<T = unknown>(url: string, method: 'POST' | 'PATCH' | 'PUT' | 'DELETE', body?: unknown): Promise<T> {
  return apiJson<T>(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong';
}

// ======================== Risk coding ========================

export interface RiskMeta {
  key: RiskLevel | 'unknown';
  label: string;
  /** CSS colour, works for dots, rules and chart series */
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

export const RISK_LEVELS: RiskLevel[] = ['critical', 'high', 'medium', 'low'];

// ======================== Formatting ========================

export function formatEventType(type: string | null | undefined): string {
  if (!type) return 'Unknown';
  const words = type.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** snake_case status to sentence case: "false_positive" -> "False positive". */
export function formatStatus(status: string | null | undefined): string {
  return formatEventType(status);
}

export function toDate(value: string | number | null | undefined): Date | null {
  if (value == null || value === '') return null;
  let ms: number;
  if (typeof value === 'number') {
    ms = value < 1e12 ? value * 1000 : value;
  } else if (/^\d+(\.\d+)?$/.test(value.trim())) {
    const n = parseFloat(value);
    ms = n < 1e12 ? n * 1000 : n;
  } else {
    ms = new Date(value).getTime();
  }
  const date = new Date(ms);
  return isNaN(date.getTime()) ? null : date;
}

const DATE_TIME = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
});
const TIME_ONLY = new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
const RELATIVE = new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'short' });
const NUMBER = new Intl.NumberFormat('en-IN');

export function formatTime(value: string | number | null | undefined): string {
  const date = toDate(value);
  return date ? DATE_TIME.format(date) : 'Unknown';
}

export function formatClock(date: Date): string {
  return TIME_ONLY.format(date);
}

export function formatRelative(value: string | number | null | undefined, now = Date.now()): string {
  const date = toDate(value);
  if (!date) return 'Unknown';
  const seconds = Math.round((date.getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return 'just now';
  if (abs < 3600) return RELATIVE.format(Math.round(seconds / 60), 'minute');
  if (abs < 86400) return RELATIVE.format(Math.round(seconds / 3600), 'hour');
  return RELATIVE.format(Math.round(seconds / 86400), 'day');
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || isNaN(seconds)) return 'Unknown';
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function formatNumber(value: number | null | undefined): string {
  return NUMBER.format(value ?? 0);
}
