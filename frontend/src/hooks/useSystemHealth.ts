'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiUrl } from '../api/client';

export interface SystemHealth {
  status: 'ok' | 'degraded';
  api: 'online';
  pipeline: 'starting' | 'ready' | 'unavailable';
  ready: boolean;
  cameras: { online: number; total: number };
  models: Record<string, boolean>;
  storage: {
    snapshot_storage_mb: number | null;
    snapshot_storage_limit_mb: number;
    free_storage_mb: number;
    capture_enabled: boolean;
  } | null;
  persistence_enabled: boolean;
}

export function useSystemHealth(intervalMs = 10_000) {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [reachable, setReachable] = useState<boolean | null>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch(apiUrl('/api/health'), { cache: 'no-store', signal });
      if (!response.ok) throw new Error(`Health check returned ${response.status}`);
      setHealth(await response.json());
      setReachable(true);
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        setHealth(null);
        setReachable(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    const id = window.setInterval(() => void refresh(controller.signal), intervalMs);
    return () => {
      controller.abort();
      window.clearInterval(id);
    };
  }, [intervalMs, refresh]);

  return { health, reachable, refresh };
}
