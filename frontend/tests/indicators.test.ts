import { describe, expect, it } from 'vitest';
import { cameraDisplayStatus, isCameraLive, isCameraStalled, STALE_AFTER_MS } from '../src/components/ui/Indicators';

const now = Date.parse('2026-09-16T02:40:00Z');
const iso = (msAgo: number) => new Date(now - msAgo).toISOString();

describe('camera liveness', () => {
  it('treats an online camera with a recent frame as live', () => {
    const camera = { status: 'online', enabled: true, last_frame_at: iso(5_000) };
    expect(isCameraLive(camera, now)).toBe(true);
    expect(cameraDisplayStatus(camera, now)).toBe('online');
  });

  it('flags an "online" camera whose capture stopped as stalled, not live', () => {
    const camera = { status: 'online', enabled: true, last_frame_at: iso(STALE_AFTER_MS + 1_000) };
    expect(isCameraStalled(camera, now)).toBe(true);
    expect(isCameraLive(camera, now)).toBe(false);
    expect(cameraDisplayStatus(camera, now)).toBe('stalled');
  });

  it('shows disabled even when the backend still reports online', () => {
    const camera = { status: 'online', enabled: false, last_frame_at: iso(1_000) };
    expect(isCameraLive(camera, now)).toBe(false);
    expect(cameraDisplayStatus(camera, now)).toBe('disabled');
  });

  it('does not call a camera stalled when there is no frame time to judge by', () => {
    expect(isCameraStalled({ status: 'online', enabled: true, last_frame_at: null }, now)).toBe(false);
    expect(cameraDisplayStatus({ status: 'offline', enabled: true }, now)).toBe('offline');
  });
});
