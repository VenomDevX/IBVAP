import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../src/context/AuthContext', () => ({ useAuth: () => ({ mediaTicket: 'ticket-1' }) }));

import StreamView from '../src/components/video/StreamView';

const frame = () => screen.getByAltText('Camera A') as HTMLImageElement;

describe('StreamView', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('keeps the MJPEG stream URL in stream mode', () => {
    render(<StreamView path="/api/stream/CAM_A" alt="Camera A" />);
    expect(frame().src).toContain('/api/stream/CAM_A?ticket=ticket-1');
  });

  // Browsers allow 6 connections per host; open MJPEG streams use them up,
  // so large grids poll snapshots instead of holding a connection each.
  it('in poll mode requests one snapshot at a time, only after the last one loaded', () => {
    render(<StreamView path="/api/stream/CAM_A" mode="poll" pollMs={1000} alt="Camera A" />);
    const first = frame().src;
    expect(first).toContain('/api/stream/CAM_A/snapshot');
    expect(first).toContain('ticket=ticket-1');

    act(() => { vi.advanceTimersByTime(5000); });
    expect(frame().src).toBe(first);

    fireEvent.load(frame());
    act(() => { vi.advanceTimersByTime(1000); });
    const second = frame().src;
    expect(second).toContain('/api/stream/CAM_A/snapshot');
    expect(second).not.toBe(first);
  });

  it('in poll mode retries after a failed snapshot', () => {
    render(<StreamView path="/api/stream/CAM_A" mode="poll" pollMs={1000} alt="Camera A" />);
    const first = frame().src;
    fireEvent.error(frame());
    act(() => { vi.advanceTimersByTime(3000); });
    expect(frame().src).not.toBe(first);
  });
});
