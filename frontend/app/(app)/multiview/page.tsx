'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/src/context/AuthContext';
import { apiFetch, mediaSrc } from '@/src/api/client';
import { useInterval } from '@/src/hooks/useInterval';
import { cn } from '@/src/lib/cn';
import Icon from '@/src/components/ui/Icon';
import SegmentedControl from '@/src/components/ui/SegmentedControl';
import { Loading } from '@/src/components/ui/States';
import { Toolbar, Spacer } from '@/src/components/ui/Toolbar';
import type { Camera, ThreatsData } from '@/src/types';

type GridSize = '4' | '9' | '16';

const LAYOUTS: { value: GridSize; label: string }[] = [
  { value: '4', label: '2 × 2' },
  { value: '9', label: '3 × 3' },
  { value: '16', label: '4 × 4' },
];

export default function MultiViewPage() {
  const { session } = useAuth();
  const token = session?.access_token;
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [threats, setThreats] = useState<ThreatsData | null>(null);
  const [size, setSize] = useState<GridSize>('4');
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const [camRes, threatRes] = await Promise.all([
        apiFetch('/api/cameras'),
        apiFetch('/api/statistics/threats'),
      ]);
      setCameras(await camRes.json());
      setThreats(await threatRes.json());
      setLoading(false);
    } catch (err) {
      console.error('Failed to load multiview data:', err);
    }
  };

  useEffect(() => { load(); }, []);
  useInterval(load, 5000);

  if (loading) return <Loading label="Loading multi-camera view…" />;

  const count = Number(size);
  const cols = Math.sqrt(count);

  return (
    <div>
      <Toolbar>
        <Spacer />
        <SegmentedControl options={LAYOUTS} value={size} onChange={setSize} ariaLabel="Grid layout" />
      </Toolbar>

      <div
        className="grid gap-2.5"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, height: 'calc(100vh - 11rem)' }}
      >
        {Array.from({ length: count }).map((_, idx) => {
          const cam = cameras[idx];
          const threatCount = cam ? threats?.camera_distribution?.[cam.camera_id] ?? 0 : 0;
          return (
            <div
              key={idx}
              className={cn(
                'relative flex items-center justify-center overflow-hidden rounded-sm bg-black',
                threatCount > 0 ? 'border-2 border-danger' : 'border border-default',
              )}
            >
              {cam ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={mediaSrc(`/api/stream/${cam.camera_id}`, token)}
                    alt={cam.name}
                    className="size-full object-contain"
                    onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden'; }}
                  />
                  <div className="absolute inset-x-0 top-0 flex items-start justify-between gap-2 bg-gradient-to-b from-black/80 to-transparent p-2.5">
                    <div className="text-white [text-shadow:0_1px_2px_#000]">
                      <strong className="block text-[0.82rem]">{cam.name}</strong>
                      <span className="text-[0.7rem] opacity-80">{cam.camera_id}</span>
                    </div>
                    {threatCount > 0 && (
                      <span className="flex items-center gap-1.5 rounded-sm bg-danger px-2 py-0.5 text-[0.72rem] font-semibold text-white [animation:pulse-ring_2s_ease-in-out_infinite]">
                        <Icon name="triangle-exclamation" />
                        {threatCount} {threatCount === 1 ? 'threat' : 'threats'}
                      </span>
                    )}
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center gap-2 text-fg-subtle">
                  <Icon name="video-slash" className="text-2xl opacity-60" />
                  <span className="text-[0.8rem]">No camera</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
