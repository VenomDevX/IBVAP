'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ArrowClockwise, Fire, Plus, VideoCameraSlash } from '@phosphor-icons/react';
import { apiJson, apiSend, errorMessage, formatRelative, formatStatus, mediaSrc } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { useInterval } from '@/src/hooks/useInterval';
import { pushToast } from '@/src/lib/toast';
import { Button } from '@/src/components/ui/Button';
import Dialog from '@/src/components/ui/Dialog';
import { Field, Input, SearchInput, Select } from '@/src/components/ui/Field';
import { Toolbar } from '@/src/components/ui/Section';
import { EmptyState, InlineError, Loading } from '@/src/components/ui/States';
import { cameraDisplayStatus, isCameraLive, StatusLabel } from '@/src/components/ui/Indicators';
import HeatmapLayer from '@/src/components/video/HeatmapLayer';
import type { Camera } from '@/src/types';

type CameraForm = {
  camera_id: string; name: string; source: string; type: string; location: string;
  enabled: boolean; fps_limit: number; latitude: string; longitude: string;
};

const EMPTY_FORM: CameraForm = {
  camera_id: '', name: '', source: '', type: 'general', location: '', enabled: true, fps_limit: 15, latitude: '', longitude: '',
};

const CAMERA_TYPES = [['general', 'General'], ['checkpoint', 'Checkpoint'], ['border', 'Border'], ['traffic', 'Traffic']];

function CameraTile({ camera, tick, isAdmin, onEdit, onAction, busy }: {
  camera: Camera;
  tick: number;
  isAdmin: boolean;
  onEdit: (camera: Camera) => void;
  onAction: (camera: Camera, action: 'test' | 'restart' | 'toggle') => void;
  busy: string | undefined;
}) {
  const { mediaTicket } = useAuth();
  const [failed, setFailed] = useState(false);
  const [heatmap, setHeatmap] = useState(false);
  const online = isCameraLive(camera);
  const disabled = camera.enabled === false;

  return (
    <article className="min-w-0">
      <div className="relative aspect-video overflow-hidden rounded-lg bg-video">
        {/* Offline cameras still serve their last frame; disabled ones return 404. */}
        {mediaTicket && !disabled && !failed && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={mediaSrc(`/api/stream/${camera.camera_id}/snapshot?v=${tick}`, mediaTicket)}
            alt={`Latest frame from ${camera.name}`}
            width={1280}
            height={720}
            loading="lazy"
            className={online ? 'absolute inset-0 size-full object-contain' : 'absolute inset-0 size-full object-contain opacity-40 grayscale'}
            onError={() => setFailed(true)}
          />
        )}
        {heatmap && online && <HeatmapLayer cameraId={camera.camera_id} />}
        {(!online || failed) && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-center text-sm text-white/75">
            <VideoCameraSlash size={20} aria-hidden />
            <span>{online ? 'No frame available' : formatStatus(cameraDisplayStatus(camera))}</span>
            <span className="text-xs text-white/55">
              {camera.last_frame_at ? `Last frame ${formatRelative(camera.last_frame_at)}` : 'No frame received yet'}
            </span>
          </div>
        )}
      </div>

      <div className="mt-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-base font-medium text-fg">{camera.name}</h2>
          <p className="truncate text-sm text-muted">
            {camera.location || camera.camera_id}{camera.type ? `, ${formatStatus(camera.type)}` : ''}
          </p>
        </div>
        <StatusLabel status={cameraDisplayStatus(camera)} className="pt-0.5 text-sm text-muted" />
      </div>

      <div className="-ml-2.5 mt-1.5 flex flex-wrap items-center gap-0.5">
        <Button size="sm" variant={heatmap ? 'secondary' : 'ghost'} aria-pressed={heatmap} disabled={!online}
          icon={<Fire size={14} />} onClick={() => setHeatmap(v => !v)}>
          Heatmap
        </Button>
        {isAdmin && (
          <>
            <Button size="sm" variant="ghost" onClick={() => onEdit(camera)}>Edit</Button>
            <Button size="sm" variant="ghost" loading={busy === 'test'} onClick={() => onAction(camera, 'test')}>Test</Button>
            {camera.enabled !== false && (
              <Button size="sm" variant="ghost" loading={busy === 'restart'} onClick={() => onAction(camera, 'restart')}>Restart</Button>
            )}
            <Button size="sm" variant="ghost" loading={busy === 'toggle'} onClick={() => onAction(camera, 'toggle')}
              className={camera.enabled !== false ? 'text-bad hover:text-bad' : undefined}>
              {camera.enabled !== false ? 'Disable' : 'Enable'}
            </Button>
          </>
        )}
      </div>
    </article>
  );
}

export default function CamerasPage() {
  const { role } = useAuth();
  const isAdmin = role === 'admin';
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState<Record<string, string>>({});
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<CameraForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setCameras(await apiJson<Camera[]>('/api/cameras'));
      setTick(Date.now());
      setLoadError(null);
    } catch (err) {
      setLoadError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useInterval(load, 10_000);

  const set = <K extends keyof CameraForm>(key: K, value: CameraForm[K]) => setForm(current => ({ ...current, [key]: value }));

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setFormOpen(true);
  };

  const openEdit = async (camera: Camera) => {
    try {
      const config = await apiJson<Camera>(`/api/cameras/${encodeURIComponent(camera.camera_id)}/config`);
      setForm({
        camera_id: config.camera_id, name: config.name, source: config.source ?? '', type: config.type ?? 'general',
        location: config.location ?? '', enabled: config.enabled ?? true, fps_limit: config.fps_limit ?? 15,
        latitude: config.latitude == null ? '' : String(config.latitude),
        longitude: config.longitude == null ? '' : String(config.longitude),
      });
      setEditingId(camera.camera_id);
      setFormError(null);
      setFormOpen(true);
    } catch (err) {
      pushToast({ title: `Could not load settings for ${camera.name}`, message: errorMessage(err), level: 'error' });
    }
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    const payload = {
      ...form,
      latitude: form.latitude === '' ? null : Number(form.latitude),
      longitude: form.longitude === '' ? null : Number(form.longitude),
    };
    try {
      if (editingId) {
        const { camera_id: _ignored, ...changes } = payload;
        void _ignored;
        await apiSend(`/api/cameras/${encodeURIComponent(editingId)}`, 'PATCH', changes);
      } else {
        await apiSend('/api/cameras', 'POST', payload);
      }
      setFormOpen(false);
      pushToast({ title: editingId ? 'Camera saved' : 'Camera added', message: form.name, level: 'success' });
      await load();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const runAction = async (camera: Camera, action: 'test' | 'restart' | 'toggle') => {
    setBusy(current => ({ ...current, [camera.camera_id]: action }));
    const id = encodeURIComponent(camera.camera_id);
    try {
      if (action === 'test') {
        const result = await apiSend<{ reachable?: boolean; frame_received?: boolean }>(`/api/cameras/${id}/test`, 'POST');
        const ok = result.frame_received ?? result.reachable;
        pushToast({
          title: ok ? `${camera.name} returned a frame` : `${camera.name} did not return a frame`,
          message: ok ? undefined : 'Check the source address and that the camera is powered and on the network.',
          level: ok ? 'success' : 'error',
        });
      } else if (action === 'restart') {
        await apiSend(`/api/cameras/${id}/restart`, 'POST');
        pushToast({ title: `Restarting ${camera.name}`, level: 'success' });
      } else {
        const enabled = camera.enabled === false;
        await apiSend(`/api/cameras/${id}`, 'PATCH', { enabled });
        pushToast({ title: `${camera.name} ${enabled ? 'enabled' : 'disabled'}`, level: 'success' });
      }
      await load();
    } catch (err) {
      pushToast({ title: `Could not ${action === 'toggle' ? 'update' : action} ${camera.name}`, message: errorMessage(err), level: 'error' });
    } finally {
      setBusy(current => { const next = { ...current }; delete next[camera.camera_id]; return next; });
    }
  };

  if (loading) return <Loading label="Loading cameras…" />;

  const q = query.trim().toLowerCase();
  const visible = q
    ? cameras.filter(c => [c.name, c.camera_id, c.location].some(v => v?.toLowerCase().includes(q)))
    : cameras;
  const online = cameras.filter(isCameraLive).length;

  return (
    <div>
      <Toolbar>
        <SearchInput placeholder="Search by name, ID or location…" aria-label="Search cameras" value={query}
          onChange={e => setQuery(e.target.value)} wrapperClassName="w-full sm:w-72" />
        <span className="num text-sm text-muted">{online} of {cameras.length} online</span>
        <div className="ml-auto flex gap-2">
          <Button size="md" variant="ghost" icon={<ArrowClockwise size={14} />} onClick={() => void load()}>Refresh</Button>
          {isAdmin && <Button variant="primary" icon={<Plus size={14} />} onClick={openCreate}>Add camera</Button>}
        </div>
      </Toolbar>

      {loadError && cameras.length > 0 && (
        <div className="mb-4"><InlineError>Showing the last known list. Refresh failed: {loadError}</InlineError></div>
      )}

      {cameras.length === 0 ? (
        loadError
          ? <EmptyState title="Cameras could not be loaded" description={loadError} action={<Button onClick={() => void load()}>Try again</Button>} />
          : <EmptyState title="No cameras yet" description={isAdmin ? 'Add a camera with its RTSP, HTTP or file source to start analysing video.' : 'An administrator has not added any cameras you can access.'}
              action={isAdmin && <Button variant="primary" icon={<Plus size={14} />} onClick={openCreate}>Add camera</Button>} />
      ) : visible.length === 0 ? (
        <EmptyState title="No cameras match your search" action={<Button onClick={() => setQuery('')}>Clear search</Button>} />
      ) : (
        <div className="grid gap-x-6 gap-y-8 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {visible.map(camera => (
            <CameraTile key={camera.camera_id} camera={camera} tick={tick} isAdmin={isAdmin}
              onEdit={openEdit} onAction={runAction} busy={busy[camera.camera_id]} />
          ))}
        </div>
      )}

      <Dialog
        open={formOpen}
        onClose={() => setFormOpen(false)}
        size="lg"
        title={editingId ? `Edit ${form.name || editingId}` : 'Add camera'}
        description={editingId ? 'Changes apply when the pipeline next reads the camera configuration.' : 'The camera starts streaming as soon as it is saved.'}
      >
        <form id="camera-form" onSubmit={save} className="grid gap-4 sm:grid-cols-2">
          <Field label="Camera ID" htmlFor="camera_id" hint={editingId ? 'IDs cannot be changed.' : 'Short and unique, e.g. gate-north-1.'}>
            <Input id="camera_id" name="camera_id" required disabled={!!editingId} value={form.camera_id} spellCheck={false}
              autoComplete="off" onChange={e => set('camera_id', e.target.value)} placeholder="gate-north-1" />
          </Field>
          <Field label="Display name" htmlFor="name">
            <Input id="name" name="name" required value={form.name} autoComplete="off" onChange={e => set('name', e.target.value)} placeholder="North gate…" />
          </Field>
          <Field label="Video source" htmlFor="source" hint="RTSP or HTTP URL, or a local file path." className="sm:col-span-2">
            <Input id="source" name="source" required value={form.source} spellCheck={false} autoComplete="off"
              onChange={e => set('source', e.target.value)} placeholder="rtsp://10.0.0.12:554/stream1" />
          </Field>
          <Field label="Location" htmlFor="location">
            <Input id="location" name="location" value={form.location} autoComplete="off" onChange={e => set('location', e.target.value)} placeholder="Sector 4, outer fence…" />
          </Field>
          <Field label="Type" htmlFor="type">
            <Select id="type" name="type" value={form.type} onChange={e => set('type', e.target.value)}>
              {CAMERA_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </Select>
          </Field>
          <Field label="Frame rate limit" htmlFor="fps_limit" hint="Frames per second analysed, 1 to 120.">
            <Input id="fps_limit" name="fps_limit" type="number" inputMode="numeric" min={1} max={120} required
              value={form.fps_limit} onChange={e => set('fps_limit', Number(e.target.value))} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Latitude" htmlFor="latitude">
              <Input id="latitude" name="latitude" type="number" inputMode="decimal" step="any" min={-90} max={90}
                value={form.latitude} onChange={e => set('latitude', e.target.value)} placeholder="28.6139" />
            </Field>
            <Field label="Longitude" htmlFor="longitude">
              <Input id="longitude" name="longitude" type="number" inputMode="decimal" step="any" min={-180} max={180}
                value={form.longitude} onChange={e => set('longitude', e.target.value)} placeholder="77.2090" />
            </Field>
          </div>
          {formError && <div className="sm:col-span-2"><InlineError>{formError}</InlineError></div>}
          <div className="flex justify-end gap-2 border-t border-line pt-4 sm:col-span-2">
            <Button variant="ghost" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>{editingId ? 'Save changes' : 'Add camera'}</Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
