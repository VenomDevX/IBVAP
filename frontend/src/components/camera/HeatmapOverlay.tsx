'use client';

import { useState } from 'react';
import { useInterval } from '../../hooks/useInterval';
import { useAuth } from '../../context/AuthContext';
import { mediaSrc } from '../../api/client';

interface HeatmapOverlayProps {
  cameraId: string;
  isVisible: boolean;
  windowMinutes?: number;
}

export default function HeatmapOverlay({ cameraId, isVisible, windowMinutes = 5 }: HeatmapOverlayProps) {
  const [timestamp, setTimestamp] = useState(Date.now());
  const { session } = useAuth();

  useInterval(() => {
    if (isVisible) setTimestamp(Date.now());
  }, 5000);

  if (!isVisible) return null;

  const windowSeconds = windowMinutes * 60;
  return (
    <div className="pointer-events-none absolute inset-0 opacity-70 mix-blend-screen">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={mediaSrc(`/api/cameras/${cameraId}/heatmap?window=${windowSeconds}&t=${timestamp}`, session?.access_token)}
        alt=""
        className="size-full object-contain"
      />
    </div>
  );
}
