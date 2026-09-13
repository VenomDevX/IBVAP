'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/src/context/AuthContext';
import { apiFetch, formatTime, mediaSrc } from '@/src/api/client';
import { useInterval } from '@/src/hooks/useInterval';
import Icon from '@/src/components/ui/Icon';
import { Button } from '@/src/components/ui/Button';
import { Input, Select } from '@/src/components/ui/Field';
import Card from '@/src/components/ui/Card';
import StatusDot from '@/src/components/ui/StatusDot';
import { EmptyState, Loading } from '@/src/components/ui/States';
import { pushToast } from '@/src/lib/toast';
import type { Camera } from '@/src/types';

type CameraForm = { camera_id: string; name: string; source: string; type: string; location: string; enabled: boolean; fps_limit: number; latitude: string; longitude: string };
const EMPTY_CAMERA: CameraForm = { camera_id: '', name: '', source: '', type: 'general', location: '', enabled: true, fps_limit: 15, latitude: '', longitude: '' };

export default function CamerasPage() {
  const { mediaTicket, role } = useAuth();
  const isAdmin = role === 'admin';
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [heatmaps, setHeatmaps] = useState<Record<string, boolean>>({});
  const [snapshotTick, setSnapshotTick] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(EMPTY_CAMERA);
  const [editingId, setEditingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await apiFetch('/api/cameras');
      if (!res.ok) throw new Error(`Camera request returned ${res.status}`);
      setCameras(await res.json());
      setSnapshotTick(Date.now());
    } catch (err) {
      console.error('Failed to load cameras:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useInterval(load, 10000);

  const saveCamera = async () => {
    const payload = {
      ...form,
      latitude: form.latitude === '' ? null : Number(form.latitude),
      longitude: form.longitude === '' ? null : Number(form.longitude),
    };
    const requestBody = editingId ? (({ camera_id: _cameraId, ...changes }) => changes)(payload) : payload;
    const response = await apiFetch(editingId ? `/api/cameras/${editingId}` : '/api/cameras', {
      method: editingId ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody),
    });
    if (!response.ok) {
      pushToast({ title: 'Camera creation failed', message: await response.text(), level: 'high' });
      return;
    }
    setShowCreate(false);
    setEditingId(null);
    setForm(EMPTY_CAMERA);
    pushToast({ title: editingId ? 'Camera updated' : 'Camera added', message: form.name });
    await load();
  };

  const editCamera = async (camera: Camera) => {
    const response = await apiFetch(`/api/cameras/${camera.camera_id}/config`);
    if (!response.ok) {
      pushToast({ title: 'Could not load camera settings', message: camera.name, level: 'high' });
      return;
    }
    const config: Camera = await response.json();
    setForm({
      camera_id: config.camera_id, name: config.name, source: config.source ?? '', type: config.type ?? 'general',
      location: config.location ?? '', enabled: config.enabled ?? true, fps_limit: config.fps_limit ?? 15,
      latitude: config.latitude == null ? '' : String(config.latitude), longitude: config.longitude == null ? '' : String(config.longitude),
    });
    setEditingId(camera.camera_id);
    setShowCreate(true);
  };

  const closeForm = () => { setShowCreate(false); setEditingId(null); setForm(EMPTY_CAMERA); };

  const cameraAction = async (camera: Camera, action: 'test' | 'restart' | 'toggle') => {
    const path = action === 'toggle' ? `/api/cameras/${camera.camera_id}` : `/api/cameras/${camera.camera_id}/${action}`;
    const response = await apiFetch(path, action === 'toggle' ? {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !camera.enabled }),
    } : { method: 'POST' });
    const result = await response.json().catch(() => ({}));
    pushToast({
      title: response.ok ? `Camera ${action} complete` : `Camera ${action} failed`,
      message: action === 'test' && response.ok ? (result.reachable ? 'Frame received' : 'Source did not return a frame') : camera.name,
      level: response.ok ? 'low' : 'high',
    });
    await load();
  };

  if (loading) return <Loading label="Loading cameras…" />;

  return (
    <div className="space-y-4">
      {isAdmin && <div className="flex justify-end"><Button variant="primary" icon="plus" onClick={() => { if (showCreate) closeForm(); else setShowCreate(true); }}>Add camera</Button></div>}

      {showCreate && (
        <Card title={editingId ? `Edit ${form.name}` : 'Add Camera'} icon="video">
          <div className="grid gap-3 md:grid-cols-2">
            <Input placeholder="Camera ID" value={form.camera_id} disabled={!!editingId} onChange={e => setForm(value => ({ ...value, camera_id: e.target.value }))} />
            <Input placeholder="Display name" value={form.name} onChange={e => setForm(value => ({ ...value, name: e.target.value }))} />
            <Input placeholder="RTSP, HTTP, or local video source" value={form.source} onChange={e => setForm(value => ({ ...value, source: e.target.value }))} className="md:col-span-2" />
            <Input placeholder="Location label" value={form.location} onChange={e => setForm(value => ({ ...value, location: e.target.value }))} />
            <Select value={form.type} onChange={e => setForm(value => ({ ...value, type: e.target.value }))}>
              <option value="general">General</option><option value="checkpoint">Checkpoint</option><option value="border">Border</option><option value="traffic">Traffic</option>
            </Select>
            <Input type="number" min={1} max={120} aria-label="FPS limit" placeholder="FPS limit" value={form.fps_limit} onChange={e => setForm(value => ({ ...value, fps_limit: Number(e.target.value) }))} />
            <Input type="number" min={-90} max={90} step="any" aria-label="Latitude" placeholder="Latitude (optional)" value={form.latitude} onChange={e => setForm(value => ({ ...value, latitude: e.target.value }))} />
            <Input type="number" min={-180} max={180} step="any" aria-label="Longitude" placeholder="Longitude (optional)" value={form.longitude} onChange={e => setForm(value => ({ ...value, longitude: e.target.value }))} />
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={closeForm}>Cancel</Button>
            <Button variant="primary" disabled={!form.camera_id || !form.name || !form.source} onClick={saveCamera}>{editingId ? 'Save changes' : 'Create camera'}</Button>
          </div>
        </Card>
      )}

      {cameras.length === 0 ? <EmptyState icon="video-slash" message="No cameras configured" /> : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {cameras.map(camera => {
            const showHeatmap = !!heatmaps[camera.camera_id];
            return (
              <article key={camera.camera_id} className="flex flex-col overflow-hidden rounded-lg border border-default bg-card shadow-sm">
                <div className="relative aspect-video bg-black">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={mediaSrc(`/api/stream/${camera.camera_id}/snapshot?v=${snapshotTick}`, mediaTicket)} alt={camera.name}
                    className={`absolute inset-0 size-full object-cover ${camera.status === 'online' ? '' : 'opacity-45 grayscale'}`}
                    onError={event => {
                      const img = event.target as HTMLImageElement;
                      img.style.display = 'none';
                      (img.parentElement?.querySelector('[data-offline]') as HTMLElement | null)?.style.setProperty('display', 'flex');
                    }}
                    onLoad={event => {
                      const img = event.target as HTMLImageElement;
                      img.style.display = 'block';
                      if (camera.status === 'online') (img.parentElement?.querySelector('[data-offline]') as HTMLElement | null)?.style.setProperty('display', 'none');
                    }}
                  />
                  {showHeatmap && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={mediaSrc(`/api/cameras/${camera.camera_id}/heatmap`, mediaTicket)} alt="" className="pointer-events-none absolute inset-0 size-full object-cover opacity-80 mix-blend-screen" />
                  )}
                  <div data-offline className={`absolute inset-0 flex-col items-center justify-center gap-2 bg-black/45 text-white ${camera.status === 'online' ? 'hidden' : 'flex'}`}>
                    <Icon name="video-slash" className="text-2xl opacity-80" /><p className="text-sm font-semibold">OFFLINE</p>
                    <p className="text-xs text-white/75">Last frame at: {camera.last_frame_at ? formatTime(camera.last_frame_at) : 'Unavailable'}</p>
                  </div>
                </div>

                <div className="space-y-3 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0"><h2 className="font-semibold text-fg">{camera.name}</h2><p className="text-sm text-fg-muted">{camera.location || camera.camera_id}</p></div>
                    <span className="flex items-center gap-2 text-sm text-fg-muted"><StatusDot status={camera.status === 'retired' ? 'offline' : camera.status} /><span className="capitalize">{camera.status}</span></span>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Button size="xs" variant={showHeatmap ? 'primary' : 'outline'} icon="fire" onClick={() => setHeatmaps(value => ({ ...value, [camera.camera_id]: !value[camera.camera_id] }))}>{showHeatmap ? 'Hide heatmap' : 'Heatmap'}</Button>
                    {isAdmin && <span className="flex flex-wrap justify-end gap-1.5">
                      <Button size="xs" variant="outline" onClick={() => editCamera(camera)}>Edit</Button>
                      <Button size="xs" variant="outline" onClick={() => cameraAction(camera, 'test')}>Test</Button>
                      {camera.enabled && <Button size="xs" variant="outline" onClick={() => cameraAction(camera, 'restart')}>Restart</Button>}
                      <Button size="xs" variant={camera.enabled ? 'danger' : 'success'} onClick={() => cameraAction(camera, 'toggle')}>{camera.enabled ? 'Disable' : 'Enable'}</Button>
                    </span>}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
