'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowsOut } from '@phosphor-icons/react';
import { apiJson, errorMessage } from '@/src/api/client';
import { useInterval } from '@/src/hooks/useInterval';
import { cn } from '@/src/lib/cn';
import SegmentedControl from '@/src/components/ui/SegmentedControl';
import { Toolbar } from '@/src/components/ui/Section';
import { Button } from '@/src/components/ui/Button';
import { EmptyState, Loading } from '@/src/components/ui/States';
import StreamView from '@/src/components/video/StreamView';
import type { Camera, ThreatsData } from '@/src/types';

type GridSize = '4' | '9' | '16';

const LAYOUTS: { value: GridSize; label: string }[] = [
  { value: '4', label: '2 × 2' },
  { value: '9', label: '3 × 3' },
  { value: '16', label: '4 × 4' },
];

// Static class strings so Tailwind can see them.
const GRID: Record<GridSize, string> = {
  '4': 'sm:grid-cols-2 lg:grid-rows-2',
  '9': 'sm:grid-cols-3 lg:grid-rows-3',
  '16': 'sm:grid-cols-4 lg:grid-rows-4',
};

export default function MultiViewPage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [threats, setThreats] = useState<ThreatsData | null>(null);
  const [size, setSize] = useState<GridSize>('4');
  const [selections, setSelections] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const inFlight = useRef(false);

  const load = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    const [cameraResult, threatResult] = await Promise.allSettled([
      apiJson<Camera[]>('/api/cameras'),
      apiJson<ThreatsData>('/api/statistics/threats'),
    ]);
    inFlight.current = false;
    if (cameraResult.status === 'fulfilled') {
      setCameras(cameraResult.value);
      setSelections(previous => (previous.length ? previous : cameraResult.value.map(c => c.camera_id)));
      setError(null);
    } else {
      setError(errorMessage(cameraResult.reason));
    }
    if (threatResult.status === 'fulfilled') setThreats(threatResult.value);
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);
  useInterval(load, 5000);

  if (loading) return <Loading label="Loading cameras…" />;
  if (cameras.length === 0) {
    return error
      ? <EmptyState title="Cameras could not be loaded" description={error} action={<Button onClick={() => void load()}>Try again</Button>} />
      : <EmptyState title="No cameras to show" description="Cameras you have access to appear here once they are configured." />;
  }

  const count = Number(size);
  const withThreats = cameras.filter(c => (threats?.camera_distribution?.[c.camera_id] ?? 0) > 0).length;

  return (
    <div>
      <Toolbar>
        <p className="text-sm text-muted">
          {cameras.length} cameras{withThreats > 0 && <>, <span className="text-critical">{withThreats} with active threats</span></>}
        </p>
        <SegmentedControl options={LAYOUTS} value={size} onChange={setSize} ariaLabel="Grid layout" className="ml-auto" />
      </Toolbar>

      <div className={cn('grid grid-cols-1 gap-2 lg:h-[calc(100dvh-9.5rem)]', GRID[size])}>
        {Array.from({ length: count }).map((_, index) => {
          const cameraId = selections[index] ?? cameras[index]?.camera_id;
          const camera = cameras.find(c => c.camera_id === cameraId);
          const threatCount = camera ? threats?.camera_distribution?.[camera.camera_id] ?? 0 : 0;
          return (
            <div key={index} data-tile className="relative aspect-video min-h-0 overflow-hidden rounded-lg bg-video lg:aspect-auto">
              {camera ? (
                <>
                  <StreamView path={camera.enabled === false ? null : `/api/stream/${camera.camera_id}`} alt={camera.name}
                    idleLabel="Camera disabled" className="absolute inset-0" />
                  <div className="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-black/60 px-2 py-1 text-white">
                    <select
                      aria-label={`Camera for tile ${index + 1}`}
                      value={camera.camera_id}
                      onChange={event => setSelections(previous => {
                        const next = cameras.map((c, i) => previous[i] ?? c.camera_id);
                        next[index] = event.target.value;
                        return next;
                      })}
                      className="min-w-0 max-w-[65%] truncate rounded-sm bg-transparent py-1 pl-1 pr-1 text-sm font-medium text-white transition-colors duration-150 hover:bg-white/10"
                    >
                      {cameras.map(c => <option key={c.camera_id} value={c.camera_id}>{c.name}</option>)}
                    </select>
                    {threatCount > 0 && (
                      <span className="num shrink-0 text-xs font-medium text-[#f4a29b]">
                        {threatCount} {threatCount === 1 ? 'threat' : 'threats'}
                      </span>
                    )}
                    <button
                      type="button"
                      aria-label={`Show ${camera.name} full screen`}
                      title="Full screen"
                      className="ml-auto shrink-0 rounded-sm p-1 text-white/75 transition-colors duration-150 hover:bg-white/10 hover:text-white"
                      onClick={event => void event.currentTarget.closest<HTMLElement>('[data-tile]')?.requestFullscreen()}
                    >
                      <ArrowsOut size={15} />
                    </button>
                  </div>
                  {threatCount > 0 && <div aria-hidden className="pointer-events-none absolute inset-0 rounded-lg ring-2 ring-inset ring-critical" />}
                </>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-white/45">Empty tile</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
