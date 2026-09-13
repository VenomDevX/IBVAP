'use client';

import { useCallback, useDeferredValue, useEffect, useState } from 'react';
import { apiFetch, formatEventType, formatTime } from '@/src/api/client';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import RiskBadge from '@/src/components/ui/RiskBadge';
import { Button, ButtonLink } from '@/src/components/ui/Button';
import { Input, SearchInput, Select } from '@/src/components/ui/Field';
import { Toolbar } from '@/src/components/ui/Toolbar';
import { Loading } from '@/src/components/ui/States';
import Card from '@/src/components/ui/Card';
import type { Camera, Event } from '@/src/types';

const TYPES = [
  ['restricted_zone_entry', 'Zone Entry'],
  ['fence_crossing', 'Fence Crossing'],
  ['loitering', 'Loitering'],
  ['night_movement', 'Night Movement'],
  ['combined_suspicious_activity', 'Combined Suspicious'],
];

export default function EventsPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [type, setType] = useState('');
  const [risk, setRisk] = useState('');
  const [camera, setCamera] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const deferredQuery = useDeferredValue(query);
  const pageSize = 25;

  useEffect(() => {
    apiFetch('/api/cameras').then(r => r.json()).then(setCameras).catch(() => setCameras([]));
  }, []);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (type) params.set('event_type', type);
    if (risk) params.set('risk_level', risk);
    if (camera) params.set('camera_id', camera);
    if (deferredQuery.trim()) params.set('search', deferredQuery.trim());
    if (startTime) params.set('start_time', new Date(startTime).toISOString());
    if (endTime) params.set('end_time', new Date(endTime).toISOString());
    try {
      const res = await apiFetch(`/api/events/query?${params}`);
      if (!res.ok) throw new Error(`Events request returned ${res.status}`);
      const data = await res.json();
      setEvents(data.items);
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to load events:', err);
    } finally {
      setLoading(false);
    }
  }, [page, type, risk, camera, deferredQuery, startTime, endTime]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [type, risk, camera, deferredQuery, startTime, endTime]);

  const columns: Column<Event>[] = [
    { key: 'risk_level', header: 'Risk', sortable: true, render: e => <RiskBadge level={e.risk_level} /> },
    { key: 'event_id', header: 'Event ID', sortable: true, className: 'font-mono text-[0.78rem]' },
    { key: 'event_type', header: 'Type', sortable: true, accessor: e => formatEventType(e.event_type), render: e => formatEventType(e.event_type) },
    { key: 'camera_id', header: 'Camera', sortable: true },
    { key: 'object_type', header: 'Object', sortable: true, className: 'capitalize' },
    { key: 'timestamp', header: 'Time', sortable: true, accessor: e => e.timestamp, render: e => formatTime(e.timestamp) },
    { key: 'risk_score', header: 'Score', sortable: true, align: 'right', accessor: e => e.risk_score ?? 0, render: e => (e.risk_score?.toFixed(0) ?? 0) },
    {
      key: 'contributing_factors', header: 'Factors',


      accessor: e => (e.contributing_factors ?? []).join(' '),
      render: e => <span className="text-fg-muted">{(e.contributing_factors ?? []).slice(0, 2).join(', ') || '—'}</span>,
    },
    { key: 'details', header: '', align: 'right', render: e => <ButtonLink href={`/event?id=${e.event_id}`} size="xs" variant="outline">View</ButtonLink> },
  ];

  return (
    <div>
      <Toolbar>
          <SearchInput placeholder="Search events…" value={query} onChange={e => setQuery(e.target.value)} />
          <Select value={type} onChange={e => setType(e.target.value)} className="w-auto">
            <option value="">All types</option>
            {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          <Select value={risk} onChange={e => setRisk(e.target.value)} className="w-auto">
            <option value="">All risk levels</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </Select>
          <Select value={camera} onChange={e => setCamera(e.target.value)} className="w-auto">
            <option value="">All cameras</option>
            {cameras.map(c => <option key={c.camera_id} value={c.camera_id}>{c.name}</option>)}
          </Select>
          <Input type="datetime-local" aria-label="From time" value={startTime} onChange={e => setStartTime(e.target.value)} className="w-auto" />
          <Input type="datetime-local" aria-label="To time" value={endTime} onChange={e => setEndTime(e.target.value)} className="w-auto" />
          <Button icon="rotate-right" onClick={load}>Refresh</Button>
        </Toolbar>

        {loading ? (
          <Loading label="Loading events…" />
        ) : (
          <DataTable
            columns={columns}
            rows={events}
            rowKey={e => e.event_id}
            pageSize={pageSize}
            emptyMessage="No events match these filters"
          />
        )}
        {!loading && total > 0 && (
          <div className="mt-3 flex items-center justify-between text-sm text-fg-muted">
            <span>{(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}</span>
            <span className="flex gap-2">
              <Button size="xs" variant="outline" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</Button>
              <Button size="xs" variant="outline" disabled={page * pageSize >= total} onClick={() => setPage(p => p + 1)}>Next</Button>
            </span>
          </div>
        )}
    </div>
  );
}
