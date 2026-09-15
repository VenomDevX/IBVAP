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
  const { mediaTicket } = useAuth();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [threats, setThreats] = useState<ThreatsData | null>(null);
  const [size, setSize] = useState<GridSize>('4');
  const [loading, setLoading] = useState(true);
  const [selections, setSelections] = useState<string[]>([]);

  const load = async () => {
    try {
      const [camRes, threatRes] = await Promise.all([
        apiFetch('/api/cameras'),
        apiFetch('/api/statistics/threats'),
      ]);
      const cameraRows: Camera[] = await camRes.json();
      setCameras(cameraRows);
      setSelections(previous => previous.length ? previous : cameraRows.map(camera => camera.camera_id));
      setThreats(await threatRes.json());
    } catch (err) {
      console.error('Failed to load multiview data:', err);
    } finally {
      setLoading(false);
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
          const cameraId = selections[idx] ?? cameras[idx]?.camera_id;
          const cam = cameras.find(camera => camera.camera_id === cameraId);
          const threatCount = cam ? threats?.camera_distribution?.[cam.camera_id] ?? 0 : 0;
          return (
            <div
              key={idx}
              data-tile
              className={cn(
                'relative flex items-center justify-center rounded-sm bg-black',
                threatCount > 0 ? 'border-2 border-danger' : 'border border-default',
              )}
            >
              {cam ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={mediaSrc(`/api/stream/${cam.camera_id}`, mediaTicket)}
                    alt={cam.name}
                    className="size-full object-contain"
                    onError={e => {
                      (e.target as HTMLImageElement).style.opacity = '0.1';
                      const parent = (e.target as HTMLImageElement).parentElement;
                      if (parent && !parent.querySelector('.stream-error')) {
                        const err = document.createElement('div');
                        err.className = 'stream-error absolute inset-0 flex flex-col items-center justify-center text-danger z-0 gap-2';
                        err.innerHTML = '<svg class="w-8 h-8 opacity-60" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"></path></svg><span class="text-xs font-medium">Stream Offline</span>';
                        parent.appendChild(err);
                      }
                    }}
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
                    <button
                      type="button"
                      aria-label={`Fullscreen ${cam.name}`}
                      className="rounded bg-black/40 px-2 py-1 text-white hover:bg-black/70"
                      onClick={event => void event.currentTarget.closest<HTMLElement>('[data-tile]')?.requestFullscreen()}
                    >
                      <Icon name="expand" />
                    </button>
                  </div>
                  <select
                    aria-label={`Camera for tile ${idx + 1}`}
                    value={cam.camera_id}
                    onChange={event => setSelections(previous => {
                      const next = [...previous]; next[idx] = event.target.value; return next;
                    })}
                    className="absolute bottom-2 left-2 z-30 max-w-[70%] rounded border border-white/20 bg-black/80 backdrop-blur-sm px-2.5 py-1.5 text-xs text-white cursor-pointer outline-none focus:ring-2 focus:ring-accent"
                  >
                    {cameras.map(camera => <option key={camera.camera_id} value={camera.camera_id}>{camera.name}</option>)}
                  </select>
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
