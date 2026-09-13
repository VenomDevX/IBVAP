import { describe, expect, it } from 'vitest';
import { mediaSrc, riskMeta } from '../src/api/client';

describe('API client helpers', () => {
  it('uses the short-lived media ticket parameter', () => {
    expect(mediaSrc('/api/stream/a?frame=1', 'signed ticket')).toContain('&ticket=signed%20ticket');
    expect(mediaSrc('/api/stream/a', null)).not.toContain('token=');
  });

  it('falls back to an explicit unknown risk style', () => {
    expect(riskMeta('unexpected').key).toBe('unknown');
  });
});
