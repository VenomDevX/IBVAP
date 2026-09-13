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
  const [timestamp, setTimestamp] = useState(0);
  const { mediaTicket } = useAuth();

  useInterval(() => {
    if (isVisible) setTimestamp(Date.now());
  }, 5000);

  useInterval(() => {
    if (isVisible) setTimestamp(Date.now());
  }, 5000);

  if (!isVisible) return null;

  const windowSeconds = windowMinutes * 60;
  return (
    <div className="pointer-events-none absolute inset-0 opacity-70 mix-blend-screen">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={mediaSrc(`/api/cameras/${cameraId}/heatmap?window=${windowSeconds}&t=${timestamp}`, mediaTicket)}
        alt=""
        className="size-full object-contain relative z-10"
        onError={e => {
          (e.target as HTMLImageElement).style.opacity = '0';
          const parent = (e.target as HTMLImageElement).parentElement;
          if (parent && !parent.querySelector('.stream-error')) {
            const err = document.createElement('div');
            err.className = 'stream-error absolute inset-0 flex flex-col items-center justify-center text-danger z-0 gap-2';
            err.innerHTML = '<span class="text-xs font-medium">Heat Map Offline</span>';
            parent.appendChild(err);
          }
        }}
        onLoad={e => {
          (e.target as HTMLImageElement).style.opacity = '1';
          const err = (e.target as HTMLImageElement).parentElement?.querySelector('.stream-error');
          if (err) err.remove();
        }}
      />
    </div>
  );
}
