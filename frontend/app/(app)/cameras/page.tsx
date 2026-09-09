'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/src/context/AuthContext';
import { apiFetch, mediaSrc } from '@/src/api/client';
import { useInterval } from '@/src/hooks/useInterval';
import Icon from '@/src/components/ui/Icon';
import { Button } from '@/src/components/ui/Button';
import StatusDot from '@/src/components/ui/StatusDot';
import { EmptyState, Loading } from '@/src/components/ui/States';
import type { Camera } from '@/src/types';

export default function CamerasPage() {
  const { session } = useAuth();
  const token = session?.access_token;
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [heatmaps, setHeatmaps] = useState<Record<string, boolean>>({});

  const load = async () => {
    try {
      const res = await apiFetch('/api/cameras');
      setCameras(await res.json());
      setLoading(false);
    } catch (err) {
      console.error('Failed to load cameras:', err);
    }
  };

  useEffect(() => { load(); }, []);
  useInterval(load, 10000);

  if (loading) return <Loading label="Loading cameras…" />;
  if (cameras.length === 0) return <EmptyState icon="video-slash" message="No cameras configured" />;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {cameras.map(c => {
        const showHeatmap = !!heatmaps[c.camera_id];
        return (
          <article key={c.camera_id} className="flex flex-col overflow-hidden rounded-[3px] border border-default bg-card">
            <div className="relative aspect-video bg-black">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={mediaSrc(`/api/stream/${c.camera_id}/snapshot`, token)}
                alt={c.name}
                className="absolute inset-0 size-full object-cover"
                onError={e => {
                  const img = e.target as HTMLImageElement;
                  img.style.display = 'none';
                  (img.parentElement?.querySelector('[data-offline]') as HTMLElement | null)?.style.setProperty('display', 'flex');
                }}
              />
              {showHeatmap && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={mediaSrc(`/api/cameras/${c.camera_id}/heatmap`, token)}
                  alt=""
                  className="pointer-events-none absolute inset-0 size-full object-cover opacity-80 mix-blend-screen"
                />
              )}
              <div
                data-offline
                className="absolute inset-0 hidden flex-col items-center justify-center gap-2 text-fg-subtle"
              >
                <Icon name="video-slash" className="text-2xl opacity-60" />
                <p className="text-[0.8rem]">Offline</p>
              </div>
            </div>

            <div className="flex items-start justify-between gap-3 p-3.5">
              <div className="min-w-0">
                <h4 className="text-[0.9rem] font-semibold text-fg">{c.name}</h4>
                <span className="font-mono text-[0.72rem] text-fg-subtle">{c.camera_id}</span>
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <span className="flex items-center gap-2 text-[0.78rem] text-fg-muted">
                  <StatusDot status={c.status} />
                  <span className="capitalize">{c.status}</span>
                  {c.fps ? <span className="rounded-sm border border-default px-1.5 py-0.5 text-[0.66rem] tabular-nums">{c.fps} fps</span> : null}
                </span>
                <Button
                  size="xs"
                  variant={showHeatmap ? 'primary' : 'outline'}
                  icon="fire"
                  onClick={() => setHeatmaps(p => ({ ...p, [c.camera_id]: !p[c.camera_id] }))}
                >
                  {showHeatmap ? 'Hide heatmap' : 'Show heatmap'}
                </Button>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
