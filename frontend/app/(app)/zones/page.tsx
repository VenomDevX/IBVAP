'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent, type MouseEvent } from 'react';
import { Plus } from '@phosphor-icons/react';
import { apiJson, apiSend, errorMessage, formatStatus, mediaSrc } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { pushToast } from '@/src/lib/toast';
import { Button } from '@/src/components/ui/Button';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import Dialog from '@/src/components/ui/Dialog';
import { Field, Input, Select } from '@/src/components/ui/Field';
import { Toolbar } from '@/src/components/ui/Section';
import { EmptyState, InlineError } from '@/src/components/ui/States';
import { Dot } from '@/src/components/ui/Indicators';
import type { Camera, Zone } from '@/src/types';

type ZoneDraft = { zone_id: string; camera_id: string; name: string; type: string; enabled: boolean; points: number[][] };

const EMPTY: ZoneDraft = { zone_id: '', camera_id: '', name: '', type: 'restricted', enabled: true, points: [] };

const ZONE_TYPES: { value: string; label: string; color: string }[] = [
  { value: 'restricted', label: 'Restricted', color: 'var(--risk-critical)' },
  { value: 'buffer', label: 'Buffer', color: 'var(--risk-medium)' },
  { value: 'safe', label: 'Safe', color: 'var(--risk-low)' },
  { value: 'entry_exit', label: 'Entry or exit', color: 'var(--accent)' },
];

const zoneType = (type: string) => ZONE_TYPES.find(t => t.value === type) ?? { value: type, label: formatStatus(type), color: 'var(--faint)' };

function ZoneEditor({ cameras, initial, editing, onCancel, onSaved }: {
  cameras: Camera[];
  initial: ZoneDraft;
  editing: boolean;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const { mediaTicket } = useAuth();
  const [draft, setDraft] = useState<ZoneDraft>(initial);
  const [natural, setNatural] = useState({ width: 1280, height: 720 });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [snapshotVersion] = useState(() => Date.now());
  const frameRef = useRef<HTMLDivElement>(null);
  const color = zoneType(draft.type).color;

  // Map a click into image pixels, accounting for object-contain letterboxing.
  const addPoint = (event: MouseEvent<HTMLDivElement>) => {
    const frame = frameRef.current;
    if (!frame || !draft.camera_id) return;
    const rect = frame.getBoundingClientRect();
    const scale = Math.min(rect.width / natural.width, rect.height / natural.height);
    const offsetX = (rect.width - natural.width * scale) / 2;
    const offsetY = (rect.height - natural.height * scale) / 2;
    const x = Math.round((event.clientX - rect.left - offsetX) / scale);
    const y = Math.round((event.clientY - rect.top - offsetY) / scale);
    if (x < 0 || y < 0 || x > natural.width || y > natural.height) return;
    setDraft(current => ({ ...current, points: [...current.points, [x, y]] }));
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (draft.points.length < 3) { setError('Place at least three points on the frame to close the zone.'); return; }
    setSaving(true);
    setError(null);
    try {
      if (editing) {
        const { zone_id: _id, ...changes } = draft;
        void _id;
        await apiSend(`/api/zones/${encodeURIComponent(initial.zone_id)}`, 'PATCH', changes);
      } else {
        await apiSend('/api/zones', 'POST', draft);
      }
      pushToast({ title: editing ? 'Zone saved' : 'Zone created', message: draft.name, level: 'success' });
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const polygon = draft.points.map(point => point.join(',')).join(' ');
  const strokeWidth = Math.max(2, natural.width / 400);

  return (
    <section aria-label="Zone editor" className="mb-10 grid gap-8 border-b border-line pb-10 xl:grid-cols-[minmax(0,2fr)_minmax(17rem,1fr)]">
      <div className="min-w-0">
        <div ref={frameRef} onClick={addPoint}
          className="relative aspect-video cursor-crosshair select-none overflow-hidden rounded-lg bg-video">
          {draft.camera_id && mediaTicket ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={mediaSrc(`/api/stream/${draft.camera_id}/snapshot?v=${snapshotVersion}`, mediaTicket)}
              alt="Camera frame used for drawing the zone"
              draggable={false}
              className="absolute inset-0 size-full object-contain"
              onLoad={e => setNatural({ width: e.currentTarget.naturalWidth || 1280, height: e.currentTarget.naturalHeight || 720 })}
            />
          ) : (
            <div className="absolute inset-0 grid place-items-center text-sm text-white/55">Choose a camera to load its frame</div>
          )}
          <svg className="pointer-events-none absolute inset-0 size-full" viewBox={`0 0 ${natural.width} ${natural.height}`}
            preserveAspectRatio="xMidYMid meet" aria-hidden>
            {draft.points.length >= 2 && (
              <polygon points={polygon} style={{ fill: draft.points.length >= 3 ? color : 'none', fillOpacity: 0.18, stroke: color, strokeWidth }} />
            )}
            {draft.points.map(([x, y], index) => (
              <circle key={`${x}-${y}-${index}`} cx={x} cy={y} r={strokeWidth * 2.5} style={{ fill: '#fff', stroke: color, strokeWidth }} />
            ))}
          </svg>
        </div>
        <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
          <span>Click the frame to place corners in order. <span className="num">{draft.points.length}</span> placed.</span>
          <span className="flex gap-1">
            <Button size="sm" variant="ghost" disabled={!draft.points.length}
              onClick={() => setDraft(current => ({ ...current, points: current.points.slice(0, -1) }))}>Undo point</Button>
            <Button size="sm" variant="ghost" disabled={!draft.points.length}
              onClick={() => setDraft(current => ({ ...current, points: [] }))}>Clear</Button>
          </span>
        </div>
      </div>

      <form onSubmit={save} className="space-y-4">
        <h2 className="text-base font-medium">{editing ? `Edit ${initial.name}` : 'New zone'}</h2>
        {!editing && (
          <Field label="Zone ID" htmlFor="zone_id" hint="Unique, e.g. fence-east.">
            <Input id="zone_id" required value={draft.zone_id} spellCheck={false} autoComplete="off"
              onChange={e => setDraft(current => ({ ...current, zone_id: e.target.value }))} placeholder="fence-east" />
          </Field>
        )}
        <Field label="Name" htmlFor="zone_name">
          <Input id="zone_name" required value={draft.name} autoComplete="off"
            onChange={e => setDraft(current => ({ ...current, name: e.target.value }))} placeholder="East fence line…" />
        </Field>
        <Field label="Camera" htmlFor="zone_camera" hint={draft.points.length ? 'Changing the camera clears the points.' : undefined}>
          <Select id="zone_camera" required value={draft.camera_id}
            onChange={e => setDraft(current => ({ ...current, camera_id: e.target.value, points: [] }))}>
            <option value="">Choose a camera</option>
            {cameras.map(camera => <option key={camera.camera_id} value={camera.camera_id}>{camera.name}</option>)}
          </Select>
        </Field>
        <Field label="Type" htmlFor="zone_type">
          <Select id="zone_type" value={draft.type} onChange={e => setDraft(current => ({ ...current, type: e.target.value }))}>
            {ZONE_TYPES.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}
          </Select>
        </Field>
        {error && <InlineError>{error}</InlineError>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button type="submit" variant="primary" loading={saving}>Save zone</Button>
        </div>
      </form>
    </section>
  );
}

export default function ZonesPage() {
  const { role } = useAuth();
  const isAdmin = role === 'admin';
  const [zones, setZones] = useState<Zone[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editor, setEditor] = useState<{ draft: ZoneDraft; editing: boolean; key: number } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Zone | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      const [zoneRows, cameraRows] = await Promise.all([apiJson<Zone[]>('/api/zones'), apiJson<Camera[]>('/api/cameras')]);
      setZones(zoneRows);
      setCameras(cameraRows);
      setLoadError(null);
    } catch (err) {
      setLoadError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const cameraName = (id: string) => cameras.find(c => c.camera_id === id)?.name ?? id;

  const toggle = async (zone: Zone) => {
    try {
      await apiSend(`/api/zones/${encodeURIComponent(zone.zone_id)}`, 'PATCH', { enabled: !zone.enabled });
      await load();
    } catch (err) {
      pushToast({ title: `Could not update ${zone.name}`, message: errorMessage(err), level: 'error' });
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await apiSend(`/api/zones/${encodeURIComponent(pendingDelete.zone_id)}`, 'DELETE');
      pushToast({ title: 'Zone deleted', message: pendingDelete.name, level: 'success' });
      setPendingDelete(null);
      await load();
    } catch (err) {
      pushToast({ title: 'Could not delete the zone', message: errorMessage(err), level: 'error' });
    } finally {
      setDeleting(false);
    }
  };

  const columns: Column<Zone>[] = [
    {
      key: 'name', header: 'Zone', sortable: true,
      render: zone => (
        <span className="block min-w-0">
          <span className="block truncate text-fg">{zone.name}</span>
          <span className="block truncate font-mono text-xs text-muted" translate="no">{zone.zone_id}</span>
        </span>
      ),
    },
    { key: 'camera_id', header: 'Camera', sortable: true, accessor: zone => cameraName(zone.camera_id) },
    {
      key: 'type', header: 'Type', sortable: true, accessor: zone => zoneType(zone.type).label,
      render: zone => <span className="inline-flex items-center gap-2"><Dot color={zoneType(zone.type).color} />{zoneType(zone.type).label}</span>,
    },
    { key: 'points', header: 'Corners', align: 'right', hideBelow: 'md', accessor: zone => zone.points?.length ?? 0, render: zone => <span className="num">{zone.points?.length ?? 0}</span> },
    {
      key: 'enabled', header: 'Status', sortable: true, accessor: zone => (zone.enabled ? 'Active' : 'Disabled'),
      render: zone => <span className={zone.enabled ? 'text-fg' : 'text-muted'}>{zone.enabled ? 'Active' : 'Disabled'}</span>,
    },
    ...(isAdmin ? [{
      key: 'actions', header: 'Actions', align: 'right' as const,
      render: (zone: Zone) => (
        <span className="-mr-2 inline-flex gap-0.5">
          <Button size="sm" variant="ghost" onClick={() => {
            setEditor({ draft: { zone_id: zone.zone_id, camera_id: zone.camera_id, name: zone.name, type: zone.type, enabled: zone.enabled, points: zone.points ?? [] }, editing: true, key: Date.now() });
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={() => void toggle(zone)}>{zone.enabled ? 'Disable' : 'Enable'}</Button>
          <Button size="sm" variant="ghost" className="text-bad hover:text-bad" onClick={() => setPendingDelete(zone)}>Delete</Button>
        </span>
      ),
    }] : []),
  ];

  return (
    <div>
      {editor && (
        <ZoneEditor key={editor.key} cameras={cameras} initial={editor.draft} editing={editor.editing}
          onCancel={() => setEditor(null)} onSaved={() => { setEditor(null); void load(); }} />
      )}

      <Toolbar>
        <p className="text-sm text-muted">
          {zones.length} {zones.length === 1 ? 'zone' : 'zones'}, {zones.filter(z => z.enabled).length} active
        </p>
        {isAdmin && !editor && (
          <Button variant="primary" icon={<Plus size={14} />} className="ml-auto"
            onClick={() => setEditor({ draft: { ...EMPTY, camera_id: cameras[0]?.camera_id ?? '' }, editing: false, key: Date.now() })}>
            Draw zone
          </Button>
        )}
      </Toolbar>

      {loadError && zones.length === 0 && !loading ? (
        <EmptyState title="Zones could not be loaded" description={loadError} action={<Button onClick={() => void load()}>Try again</Button>} />
      ) : (
        <DataTable
          label="Configured zones"
          columns={columns}
          rows={zones}
          rowKey={zone => zone.zone_id}
          loading={loading}
          emptyTitle="No zones yet"
          emptyDescription={isAdmin ? 'Draw a zone on a camera frame to mark restricted areas, buffers or entry points.' : 'An administrator has not configured any zones.'}
        />
      )}

      <Dialog
        open={!!pendingDelete}
        onClose={() => setPendingDelete(null)}
        title="Delete this zone?"
        description={pendingDelete ? `“${pendingDelete.name}” stops triggering events immediately. Past events keep their zone reference.` : undefined}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)}>Keep zone</Button>
            <Button variant="danger" loading={deleting} onClick={() => void confirmDelete()}>Delete zone</Button>
          </>
        }
      />
    </div>
  );
}
