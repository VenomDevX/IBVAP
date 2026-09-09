'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiFetch, formatEventType, formatTime } from '@/src/api/client';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import RiskBadge from '@/src/components/ui/RiskBadge';
import { Button, ButtonLink } from '@/src/components/ui/Button';
import { SearchInput, Select } from '@/src/components/ui/Field';
import { Toolbar } from '@/src/components/ui/Toolbar';
import { Loading } from '@/src/components/ui/States';
import type { Event } from '@/src/types';

const TYPES = [
  ['restricted_zone_entry', 'Zone Entry'],
  ['fence_crossing', 'Fence Crossing'],
  ['loitering', 'Loitering'],
  ['night_movement', 'Night Movement'],
  ['combined_suspicious_activity', 'Combined Suspicious'],
];

export default function EventsPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [type, setType] = useState('');
  const [risk, setRisk] = useState('');

  const load = useCallback(async () => {
    let url = '/api/events?limit=100';
    if (type) url += `&event_type=${type}`;
    if (risk) url += `&risk_level=${risk}`;
    try {
      const res = await apiFetch(url);
      setEvents(await res.json());
    } catch (err) {
      console.error('Failed to load events:', err);
    } finally {
      setLoading(false);
    }
  }, [type, risk]);

  useEffect(() => { load(); }, [load]);

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
        <Button icon="rotate-right" onClick={load}>Refresh</Button>
      </Toolbar>

      {loading ? (
        <Loading label="Loading events…" />
      ) : (
        <DataTable
          columns={columns}
          rows={events}
          rowKey={e => e.event_id}
          search={query}
          emptyMessage="No events match these filters"
        />
      )}
    </div>
  );
}
