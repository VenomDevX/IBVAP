import { describe, expect, it } from 'vitest';
import { formatDuration, formatEventType, formatRelative, formatStatus, formatTime, toDate } from '../src/api/client';

describe('formatting helpers', () => {
  it('reads epoch seconds, epoch milliseconds and ISO strings as the same instant', () => {
    const iso = '2026-09-15T10:00:00Z';
    const ms = Date.parse(iso);
    expect(toDate(ms / 1000)?.getTime()).toBe(ms);
    expect(toDate(ms)?.getTime()).toBe(ms);
    expect(toDate(String(ms / 1000))?.getTime()).toBe(ms);
    expect(toDate(iso)?.getTime()).toBe(ms);
  });

  it('never renders an em dash or "Invalid Date" for missing values', () => {
    expect(formatTime(null)).toBe('Unknown');
    expect(formatTime('not a date')).toBe('Unknown');
    expect(formatRelative(undefined)).toBe('Unknown');
  });

  it('writes snake_case values in sentence case', () => {
    expect(formatEventType('restricted_zone_entry')).toBe('Restricted zone entry');
    expect(formatStatus('false_positive')).toBe('False positive');
  });

  it('formats relative times and durations compactly', () => {
    const now = Date.parse('2026-09-15T10:00:00Z');
    expect(formatRelative(now - 10_000, now)).toBe('just now');
    expect(formatRelative(now - 5 * 60_000, now)).toMatch(/5 min/);
    expect(formatDuration(4.25)).toBe('4.3s');
    expect(formatDuration(200)).toBe('3m 20s');
  });
});
