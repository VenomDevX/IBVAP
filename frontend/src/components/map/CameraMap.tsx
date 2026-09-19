'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { apiJson, errorMessage, formatStatus, riskMeta } from '../../api/client';
import { useTheme } from '../../context/ThemeContext';
import { useChartColors } from '../../hooks/useChartColors';
import { useInterval } from '../../hooks/useInterval';
import { cn } from '../../lib/cn';
import type { Camera, ThreatsData } from '../../types';
import { Button } from '../ui/Button';
import { Dot, statusColor } from '../ui/Indicators';
import { EmptyState, Loading } from '../ui/States';

const TILES = {
  light: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  dark: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
};
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

function FlyTo({ target }: { target: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo(target, Math.max(map.getZoom(), 15), { duration: 0.5 });
  }, [target, map]);
  return null;
}

export default function CameraMap() {
  const { resolved } = useTheme();
  const colors = useChartColors();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [threats, setThreats] = useState<ThreatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const inFlight = useRef(false);

  const load = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    const [cameraResult, threatResult] = await Promise.allSettled([
      apiJson<Camera[]>('/api/cameras'),
      apiJson<ThreatsData>('/api/statistics/threats'),
    ]);
    inFlight.current = false;
    if (cameraResult.status === 'fulfilled') { setCameras(cameraResult.value); setError(null); }
    else setError(errorMessage(cameraResult.reason));
    if (threatResult.status === 'fulfilled') setThreats(threatResult.value);
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);
  useInterval(load, 5000);

  const located = useMemo(() => cameras.filter(c => c.latitude != null && c.longitude != null), [cameras]);
  const center = useMemo<[number, number]>(() => (located.length
    ? [located.reduce((s, c) => s + Number(c.latitude), 0) / located.length, located.reduce((s, c) => s + Number(c.longitude), 0) / located.length]
    : [28.6139, 77.209]), [located.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const target = useMemo<[number, number] | null>(() => {
    const camera = located.find(c => c.camera_id === selected);
    return camera ? [Number(camera.latitude), Number(camera.longitude)] : null;
  }, [selected, located]);

  if (loading) return <Loading label="Loading map…" />;
  if (error && cameras.length === 0) {
    return <EmptyState title="Cameras could not be loaded" description={error} action={<Button onClick={() => void load()}>Try again</Button>} />;
  }
  if (located.length === 0) {
    return (
      <EmptyState
        title="No cameras have coordinates"
        description="Add a latitude and longitude to a camera to place it on the map."
        action={<Link href="/cameras" className="text-sm font-medium text-accent hover:text-accent-hover">Go to cameras</Link>}
      />
    );
  }

  const threatCount = (id: string) => threats?.camera_distribution?.[id] ?? 0;
  const unlocated = cameras.length - located.length;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="h-[60dvh] overflow-hidden rounded-lg lg:h-[calc(100dvh-8.5rem)]">
        <MapContainer center={center} zoom={13} style={{ height: '100%', width: '100%' }}>
          <TileLayer key={resolved} attribution={ATTRIBUTION} url={process.env.NEXT_PUBLIC_MAP_TILE_URL ?? TILES[resolved]} />
          <FlyTo target={target} />
          {located.map(camera => {
            const count = threatCount(camera.camera_id);
            const camThreats = threats?.top_threats?.filter(t => t.camera_id === camera.camera_id) ?? [];
            const fill = count > 0 ? colors.critical : camera.status === 'online' ? colors.ok : colors.faint;
            return (
              <CircleMarker
                key={camera.camera_id}
                center={[Number(camera.latitude), Number(camera.longitude)]}
                radius={selected === camera.camera_id ? 10 : 7}
                pathOptions={{ color: colors.surface, weight: 2, fillColor: fill, fillOpacity: 1 }}
                eventHandlers={{ click: () => setSelected(camera.camera_id) }}
              >
                <Popup>
                  <p className="text-sm font-medium text-fg">{camera.name}</p>
                  {camera.location && <p className="text-xs text-muted">{camera.location}</p>}
                  <p className="mt-1.5 flex items-center gap-1.5 text-xs text-fg">
                    <Dot color={statusColor(camera.status)} className="size-1.5" />{formatStatus(camera.status)}
                  </p>
                  {count > 0 ? (
                    <ul className="mt-1.5 space-y-0.5 text-xs">
                      {camThreats.map(threat => (
                        <li key={threat.track_id} className="flex items-center gap-1.5">
                          <Dot color={riskMeta(threat.risk_level).color} className="size-1.5" />
                          <span className="capitalize">{threat.object_type}</span>
                          <span className="num text-muted">score {Math.round(threat.risk_score)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-xs text-muted">No active threats</p>
                  )}
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>

      <aside className="min-w-0">
        <h2 className="text-base font-medium">Cameras on the map</h2>
        <p className="text-sm text-muted">Select one to centre the map on it.</p>
        <ul className="-mx-3 mt-3 lg:max-h-[calc(100dvh-14rem)] lg:overflow-y-auto">
          {located.map(camera => {
            const count = threatCount(camera.camera_id);
            return (
              <li key={camera.camera_id}>
                <button
                  type="button"
                  aria-pressed={selected === camera.camera_id}
                  onClick={() => setSelected(camera.camera_id)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors duration-150 hover:bg-subtle',
                    selected === camera.camera_id && 'bg-subtle',
                  )}
                >
                  <Dot color={count > 0 ? 'var(--risk-critical)' : statusColor(camera.status)} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-fg">{camera.name}</span>
                    <span className={cn('block truncate text-xs', count > 0 ? 'text-critical' : 'text-muted')}>
                      {count > 0 ? `${count} active ${count === 1 ? 'threat' : 'threats'}` : formatStatus(camera.status)}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {unlocated > 0 && (
          <p className="mt-4 text-sm text-muted">
            {unlocated} {unlocated === 1 ? 'camera has' : 'cameras have'} no coordinates. Add them on the{' '}
            <Link href="/cameras" className="text-accent hover:text-accent-hover">Cameras</Link> page.
          </p>
        )}
      </aside>
    </div>
  );
}
