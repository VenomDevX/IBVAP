'use client';

import Link from 'next/link';
import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { ArrowClockwise } from '@phosphor-icons/react';
import { apiJson, errorMessage, formatEventType, formatTime, RISK_LEVELS, riskMeta } from '@/src/api/client';
import { useCameras } from '@/src/hooks/useCameras';
import { useDebouncedValue, useUrlState } from '@/src/hooks/useUrlState';
import { Button } from '@/src/components/ui/Button';
import DataTable, { type Column, type SortState } from '@/src/components/ui/DataTable';
import { Input, SearchInput, Select } from '@/src/components/ui/Field';
import Pagination from '@/src/components/ui/Pagination';
import { Toolbar } from '@/src/components/ui/Section';
import { InlineError, Loading } from '@/src/components/ui/States';
import { RiskLabel } from '@/src/components/ui/Indicators';
import type { Event, Paged } from '@/src/types';

const PAGE_SIZE = 25;

const EVENT_TYPES = [
  ['restricted_zone_entry', 'Restricted zone entry'],
  ['fence_crossing', 'Fence crossing'],
  ['loitering', 'Loitering'],
  ['night_movement', 'Night movement'],
  ['combined_suspicious_activity', 'Combined suspicious activity'],
];

const DEFAULTS = { q: '', type: '', risk: '', camera: '', from: '', to: '', page: '1', sort: '', dir: '' };

function EventsInner() {
  const [url, setUrl] = useUrlState(DEFAULTS);
  const cameras = useCameras();
  const [search, setSearch] = useState(url.q);
  const debouncedSearch = useDebouncedValue(search);
  const [rows, setRows] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    if (debouncedSearch !== url.q) setUrl({ q: debouncedSearch, page: null });
  }, [debouncedSearch]); // eslint-disable-line react-hooks/exhaustive-deps

  const page = Math.max(1, Number(url.page) || 1);
  const sort: SortState = url.sort ? { key: url.sort, dir: url.dir === 'asc' ? 'asc' : 'desc' } : null;

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setFetching(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (url.type) params.set('event_type', url.type);
    if (url.risk) params.set('risk_level', url.risk);
    if (url.camera) params.set('camera_id', url.camera);
    if (url.q.trim()) params.set('search', url.q.trim());
    if (url.from) params.set('start_time', new Date(url.from).toISOString());
    if (url.to) params.set('end_time', new Date(url.to).toISOString());
    if (url.sort) { params.set('sort_by', url.sort); params.set('sort_order', url.dir === 'asc' ? 'asc' : 'desc'); }
    try {
      const data = await apiJson<Paged<Event>>(`/api/events/query?${params}`);
      if (id !== requestId.current) return;
      setRows(data.items);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      if (id === requestId.current) setError(errorMessage(err));
    } finally {
      if (id === requestId.current) { setLoading(false); setFetching(false); }
    }
  }, [page, url.type, url.risk, url.camera, url.q, url.from, url.to, url.sort, url.dir]);

  useEffect(() => { void load(); }, [load]);

  const filtersActive = !!(url.q || url.type || url.risk || url.camera || url.from || url.to);

  const columns: Column<Event>[] = [
    { key: 'risk_level', header: 'Risk', render: event => <RiskLabel level={event.risk_level} /> },
    { key: 'event_type', header: 'Type', sortable: true, render: event => formatEventType(event.event_type) },
    { key: 'camera_id', header: 'Camera', sortable: true },
    { key: 'object_type', header: 'Object', hideBelow: 'md', render: event => <span className="capitalize">{event.object_type}</span> },
    { key: 'timestamp', header: 'Time', sortable: true, render: event => <span className="num whitespace-nowrap">{formatTime(event.timestamp)}</span> },
    { key: 'risk_score', header: 'Score', sortable: true, align: 'right', render: event => <span className="num">{Math.round(event.risk_score ?? 0)}</span> },
    {
      key: 'contributing_factors', header: 'Factors', hideBelow: 'xl',
      render: event => (
        <span className="block max-w-xs truncate text-muted" title={(event.contributing_factors ?? []).join(', ')}>
          {(event.contributing_factors ?? []).join(', ') || 'None'}
        </span>
      ),
    },
    {
      key: 'view', header: '', align: 'right',
      render: event => (
        <Link href={`/event?id=${encodeURIComponent(event.event_id)}`} className="text-sm font-medium text-accent hover:text-accent-hover">View</Link>
      ),
    },
  ];

  return (
    <div>
      <Toolbar>
        <SearchInput placeholder="Search events…" aria-label="Search events" value={search}
          onChange={e => setSearch(e.target.value)} wrapperClassName="w-full sm:w-64" />
        <Select aria-label="Event type" value={url.type} onChange={e => setUrl({ type: e.target.value, page: null })} wrapperClassName="w-52">
          <option value="">All event types</option>
          {EVENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>
        <Select aria-label="Risk level" value={url.risk} onChange={e => setUrl({ risk: e.target.value, page: null })} wrapperClassName="w-36">
          <option value="">Any risk</option>
          {RISK_LEVELS.map(level => <option key={level} value={level}>{riskMeta(level).label}</option>)}
        </Select>
        <Select aria-label="Camera" value={url.camera} onChange={e => setUrl({ camera: e.target.value, page: null })} wrapperClassName="w-44">
          <option value="">All cameras</option>
          {cameras.map(camera => <option key={camera.camera_id} value={camera.camera_id}>{camera.name}</option>)}
        </Select>
        <div className="w-[13.5rem]">
          <Input type="datetime-local" aria-label="From" title="From" value={url.from} onChange={e => setUrl({ from: e.target.value, page: null })} />
        </div>
        <div className="w-[13.5rem]">
          <Input type="datetime-local" aria-label="To" title="To" value={url.to} onChange={e => setUrl({ to: e.target.value, page: null })} />
        </div>
        {filtersActive && (
          <Button variant="ghost" onClick={() => { setSearch(''); setUrl({ q: null, type: null, risk: null, camera: null, from: null, to: null, page: null }); }}>
            Clear filters
          </Button>
        )}
        <Button variant="ghost" className="ml-auto" icon={<ArrowClockwise size={14} />} loading={fetching && !loading} onClick={() => void load()}>
          Refresh
        </Button>
      </Toolbar>

      {error && <div className="mb-4"><InlineError>Events could not be loaded: {error}</InlineError></div>}

      <DataTable
        label="Events"
        columns={columns}
        rows={rows}
        rowKey={event => event.event_id}
        sort={sort}
        onSortChange={next => setUrl({ sort: next?.key ?? null, dir: next?.dir ?? null, page: null })}
        loading={loading}
        emptyTitle={filtersActive ? 'No events match these filters' : 'No events recorded yet'}
        emptyDescription={filtersActive ? 'Widen the time range or clear a filter.' : 'Events appear here as the pipeline detects activity.'}
        rowAccent={event => (event.risk_level === 'critical' ? riskMeta('critical').color : undefined)}
      />
      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={next => setUrl({ page: String(next) })} />
    </div>
  );
}

export default function EventsPage() {
  return (
    <Suspense fallback={<Loading label="Loading events…" />}>
      <EventsInner />
    </Suspense>
  );
}
