'use client';

import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react';
import { apiFetch, mediaSrc } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { pushToast } from '@/src/lib/toast';
import Card from '@/src/components/ui/Card';
import Badge from '@/src/components/ui/Badge';
import StatusDot from '@/src/components/ui/StatusDot';
import { Button } from '@/src/components/ui/Button';
import { Input, Select } from '@/src/components/ui/Field';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import { Loading } from '@/src/components/ui/States';
import type { Camera, Zone } from '@/src/types';

type ZoneDraft = {
  zone_id: string;
  camera_id: string;
  name: string;
  type: string;
  enabled: boolean;
  points: number[][];
};

const EMPTY: ZoneDraft = { zone_id: '', camera_id: '', name: '', type: 'restricted', enabled: true, points: [] };

export default function ZonesPage() {
  const { role, mediaTicket } = useAuth();
  const isAdmin = role === 'admin';
  const [zones, setZones] = useState<Zone[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ZoneDraft>(EMPTY);
  const [frameSize, setFrameSize] = useState({ width: 1280, height: 720 });
  const [snapshotRevision, setSnapshotRevision] = useState(0);
  const frameRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const [zoneResponse, cameraResponse] = await Promise.all([apiFetch('/api/zones'), apiFetch('/api/cameras')]);
      if (!zoneResponse.ok || !cameraResponse.ok) throw new Error('Zone data request failed');
      setZones(await zoneResponse.json());
      setCameras(await cameraResponse.json());
    } catch (error) {
      console.error('Failed to load zones:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const openCreate = () => {
    setEditingId(null);
    setDraft({ ...EMPTY, camera_id: cameras[0]?.camera_id ?? '' });
    setEditorOpen(true);
    setSnapshotRevision(value => value + 1);
  };

  const openEdit = (zone: Zone) => {
    setEditingId(zone.zone_id);
    setDraft({ zone_id: zone.zone_id, camera_id: zone.camera_id, name: zone.name, type: zone.type, enabled: zone.enabled, points: zone.points ?? [] });
    setEditorOpen(true);
    setSnapshotRevision(value => value + 1);
  };

  const addPoint = (event: MouseEvent<HTMLDivElement>) => {
    if (!isAdmin || !frameRef.current) return;
    const rect = frameRef.current.getBoundingClientRect();
    const x = Math.round(((event.clientX - rect.left) / rect.width) * frameSize.width);
    const y = Math.round(((event.clientY - rect.top) / rect.height) * frameSize.height);
    setDraft(value => ({ ...value, points: [...value.points, [x, y]] }));
  };

  const save = async () => {
    if (!draft.camera_id || !draft.name || draft.points.length < 3) {
      pushToast({ title: 'Zone incomplete', message: 'Choose a camera, enter a name, and draw at least three points.', level: 'high' });
      return;
    }
    const path = editingId ? `/api/zones/${editingId}` : '/api/zones';
    const body = editingId ? { ...draft, zone_id: undefined } : draft;
    const response = await apiFetch(path, {
      method: editingId ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (!response.ok) {
      pushToast({ title: 'Zone save failed', message: await response.text(), level: 'high' });
      return;
    }
    pushToast({ title: editingId ? 'Zone updated' : 'Zone created', message: draft.name });
    setEditorOpen(false);
    await load();
  };

  const updateEnabled = async (zone: Zone) => {
    const response = await apiFetch(`/api/zones/${zone.zone_id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !zone.enabled }),
    });
    if (!response.ok) pushToast({ title: 'Zone update failed', message: await response.text(), level: 'high' });
    await load();
  };

  const remove = async (zone: Zone) => {
    if (!window.confirm(`Delete zone “${zone.name}”?`)) return;
    const response = await apiFetch(`/api/zones/${zone.zone_id}`, { method: 'DELETE' });
    if (!response.ok) pushToast({ title: 'Zone deletion failed', message: await response.text(), level: 'high' });
    await load();
  };

  const columns: Column<Zone>[] = [
    { key: 'name', header: 'Zone', sortable: true },
    { key: 'camera_id', header: 'Camera', sortable: true },
    { key: 'type', header: 'Type', sortable: true, render: zone => <Badge>{zone.type}</Badge> },
    { key: 'points', header: 'Geometry', accessor: zone => zone.points?.length ?? 0, render: zone => `${zone.points?.length ?? 0} points` },
    {
      key: 'enabled', header: 'Status', sortable: true, accessor: zone => zone.enabled ? 'active' : 'disabled',
      render: zone => <span className="inline-flex items-center gap-2"><StatusDot status={zone.enabled ? 'online' : 'offline'} />{zone.enabled ? 'Active' : 'Disabled'}</span>,
    },
    ...(isAdmin ? [{
      key: 'actions', header: 'Actions', align: 'right' as const,
      render: (zone: Zone) => <span className="inline-flex gap-1.5">
        <Button size="xs" variant="outline" onClick={() => openEdit(zone)}>Edit</Button>
        <Button size="xs" variant={zone.enabled ? 'outline' : 'success'} onClick={() => updateEnabled(zone)}>{zone.enabled ? 'Disable' : 'Enable'}</Button>
        <Button size="xs" variant="danger" onClick={() => remove(zone)}>Delete</Button>
      </span>,
    }] : []),
  ];

  const polygon = draft.points.map(point => point.join(',')).join(' ');

  return (
    <div className="space-y-4">
      {isAdmin && <div className="flex justify-end"><Button variant="primary" icon="plus" onClick={openCreate}>Draw zone</Button></div>}

      {editorOpen && (
        <Card title={editingId ? 'Edit Virtual Zone' : 'Draw Virtual Zone'} icon="draw-polygon">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
            <div>
              <div ref={frameRef} onClick={addPoint} className="relative aspect-video cursor-crosshair overflow-hidden rounded-lg border border-default bg-black">
                {draft.camera_id && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={mediaSrc(`/api/stream/${draft.camera_id}/snapshot?v=${snapshotRevision}`, mediaTicket)} alt="Camera frame used to draw the zone"
                    className="absolute inset-0 size-full object-contain opacity-75"
                    onLoad={event => setFrameSize({ width: event.currentTarget.naturalWidth || 1280, height: event.currentTarget.naturalHeight || 720 })}
                  />
                )}
                <svg className="pointer-events-none absolute inset-0 size-full" viewBox={`0 0 ${frameSize.width} ${frameSize.height}`} preserveAspectRatio="none" aria-label="Zone polygon preview">
                  {draft.points.length >= 2 && <polyline points={polygon} fill={draft.points.length >= 3 ? 'rgba(239,68,68,.22)' : 'none'} stroke="#ef4444" strokeWidth="4" />}
                  {draft.points.map(([x, y], index) => <circle key={`${x}-${y}-${index}`} cx={x} cy={y} r="8" fill="#fff" stroke="#ef4444" strokeWidth="4" />)}
                </svg>
                {!draft.camera_id && <div className="absolute inset-0 grid place-items-center text-fg-muted">Select a camera</div>}
              </div>
              <div className="mt-2 flex items-center justify-between text-sm text-fg-muted">
                <span>Click the frame to add polygon points clockwise.</span>
                <span className="flex gap-2"><Button size="xs" variant="ghost" disabled={!draft.points.length} onClick={() => setDraft(value => ({ ...value, points: value.points.slice(0, -1) }))}>Undo</Button><Button size="xs" variant="ghost" disabled={!draft.points.length} onClick={() => setDraft(value => ({ ...value, points: [] }))}>Clear</Button></span>
              </div>
            </div>
            <div className="space-y-3">
              {!editingId && <Input placeholder="Unique zone ID" value={draft.zone_id} onChange={event => setDraft(value => ({ ...value, zone_id: event.target.value }))} />}
              <Input placeholder="Zone name" value={draft.name} onChange={event => setDraft(value => ({ ...value, name: event.target.value }))} />
              <Select value={draft.camera_id} onChange={event => setDraft(value => ({ ...value, camera_id: event.target.value, points: [] }))}>
                <option value="">Select camera</option>{cameras.map(camera => <option key={camera.camera_id} value={camera.camera_id}>{camera.name}</option>)}
              </Select>
              <Select value={draft.type} onChange={event => setDraft(value => ({ ...value, type: event.target.value }))}>
                <option value="restricted">Restricted</option><option value="buffer">Buffer</option><option value="safe">Safe</option><option value="entry_exit">Entry / exit</option>
              </Select>
              <p className="text-sm text-fg-muted">{draft.points.length} point{draft.points.length === 1 ? '' : 's'} drawn</p>
              <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setEditorOpen(false)}>Cancel</Button><Button variant="primary" disabled={!draft.zone_id || !draft.name || draft.points.length < 3} onClick={save}>Save zone</Button></div>
            </div>
          </div>
        </Card>
      )}

      <Card title="Configured Zones" icon="draw-polygon" bodyClassName="p-0">
        {loading ? <Loading label="Loading zones…" /> : <DataTable columns={columns} rows={zones} rowKey={zone => zone.zone_id} emptyMessage="No zones configured" />}
      </Card>
    </div>
  );
}
