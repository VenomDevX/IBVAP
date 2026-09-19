'use client';

import { useEffect, useState } from 'react';
import { apiJson } from '../api/client';
import type { Camera } from '../types';

/** Camera list for filter dropdowns; loaded once per page. */
export function useCameras() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  useEffect(() => {
    let cancelled = false;
    apiJson<Camera[]>('/api/cameras')
      .then(rows => { if (!cancelled) setCameras(rows); })
      .catch(() => { if (!cancelled) setCameras([]); });
    return () => { cancelled = true; };
  }, []);
  return cameras;
}
