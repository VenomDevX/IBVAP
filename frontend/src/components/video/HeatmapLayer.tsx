'use client';

import { useState } from 'react';
import { mediaSrc } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { useInterval } from '../../hooks/useInterval';

/** Activity heatmap PNG laid over a stream; refreshes every 5s. */
export default function HeatmapLayer({ cameraId, windowSeconds = 300 }: { cameraId: string; windowSeconds?: number }) {
  const { mediaTicket } = useAuth();
  const [tick, setTick] = useState(() => Date.now());
  const [failed, setFailed] = useState(false);

  useInterval(() => setTick(Date.now()), 5000);

  if (!mediaTicket) return null;
  return (
    <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={mediaSrc(`/api/cameras/${cameraId}/heatmap?window=${windowSeconds}&t=${tick}`, mediaTicket)}
        alt=""
        aria-hidden
        className={failed ? 'hidden' : 'pointer-events-none absolute inset-0 size-full object-contain opacity-75 mix-blend-screen'}
        onLoad={() => setFailed(false)}
        onError={() => setFailed(true)}
      />
      {failed && <span className="absolute bottom-2 right-2 rounded-sm bg-black/60 px-1.5 py-0.5 text-xs text-white/70">Heatmap unavailable</span>}
    </>
  );
}
