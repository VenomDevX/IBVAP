'use client';

import { useCallback, useDeferredValue, useEffect, useState } from 'react';
import { apiFetch, formatEventType, formatTime } from '@/src/api/client';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import RiskBadge from '@/src/components/ui/RiskBadge';
import Icon from '@/src/components/ui/Icon';
import { Button, ButtonLink } from '@/src/components/ui/Button';
import { Input, SearchInput, Select } from '@/src/components/ui/Field';
import { Toolbar } from '@/src/components/ui/Toolbar';
import { Loading } from '@/src/components/ui/States';
import Card from '@/src/components/ui/Card';
import type { Alert, Camera } from '@/src/types';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [level, setLevel] = useState('');
  const [reviewed, setReviewed] = useState('');
  const [status, setStatus] = useState('');
  const [camera, setCamera] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Alert | null>(null);
  const [assignee, setAssignee] = useState('');
  const [note, setNote] = useState('');
  const deferredQuery = useDeferredValue(query);
  const pageSize = 25;

  useEffect(() => {
    apiFetch('/api/cameras').then(r => r.json()).then(setCameras).catch(console.error);
  }, []);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (level) params.set('risk_level', level);
    if (reviewed) params.set('reviewed', reviewed);
    if (status) params.set('status', status);
    if (camera) params.set('camera_id', camera);
    if (deferredQuery.trim()) params.set('search', deferredQuery.trim());
    if (startTime) params.set('start_time', new Date(startTime).toISOString());
    if (endTime) params.set('end_time', new Date(endTime).toISOString());
    try {
      const res = await apiFetch(`/api/alerts/query?${params}`);
      if (!res.ok) throw new Error(`Alerts request returned ${res.status}`);
      const data = await res.json();
      setAlerts(data.items);
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to load alerts:', err);
    } finally {
      setLoading(false);
    }
  }, [page, level, reviewed, status, camera, deferredQuery, startTime, endTime]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => { setPage(1); }, [level, reviewed, status, camera, deferredQuery, startTime, endTime]);

  const updateIncident = async (alertId: string, changes: Record<string, string>) => {
    try {
      const response = await apiFetch(`/api/alerts/${alertId}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
      });
      if (!response.ok) throw new Error(`Incident update returned ${response.status}`);
      await load();
      if (selected?.alert_id === alertId) await openIncident(alertId);
    } catch (err) {
      console.error('Review error:', err);
    }
  };

  const openIncident = async (alertId: string) => {
    const response = await apiFetch(`/api/alerts/${alertId}`);
    if (!response.ok) return;
    const detail: Alert = await response.json();
    setSelected(detail);
    setAssignee(detail.assignee ?? '');
    setNote('');
  };

  const columns: Column<Alert>[] = [
    { key: 'risk_level', header: 'Level', sortable: true, render: a => <RiskBadge level={a.risk_level} /> },
    { key: 'alert_id', header: 'Alert ID', sortable: true, className: 'font-mono text-[0.78rem]' },
    { key: 'event_type', header: 'Type', sortable: true, accessor: a => formatEventType(a.event_type), render: a => formatEventType(a.event_type) },
    { key: 'camera_id', header: 'Camera', sortable: true },
    { key: 'timestamp', header: 'Time', sortable: true, accessor: a => a.timestamp, render: a => formatTime(a.timestamp) },
    { key: 'risk_score', header: 'Score', sortable: true, align: 'right', accessor: a => a.risk_score ?? 0, render: a => (a.risk_score?.toFixed(0) ?? 0) },
    {
      key: 'status', header: 'Status', sortable: true,
      accessor: a => a.status ?? (a.reviewed ? 'resolved' : 'open'),
      render: a => {
        const closed = a.status === 'resolved' || a.status === 'false_positive';
        return <span className={`inline-flex items-center gap-1.5 text-[0.78rem] ${closed ? 'text-success' : 'text-warning'}`}>
          <Icon name={closed ? 'check' : 'clock'} /> {(a.status ?? 'open').replace('_', ' ')}
        </span>;
      },
    },
    {
      key: 'actions', header: 'Actions', align: 'right',
      render: a => (
        <span className="inline-flex justify-end gap-1.5">
          <ButtonLink href={`/event?id=${a.event_id}`} size="xs" variant="outline">View</ButtonLink>
          <Button size="xs" variant="outline" onClick={() => openIncident(a.alert_id)}>Manage</Button>
          {(a.status ?? 'open') === 'open' && <Button size="xs" onClick={() => updateIncident(a.alert_id, { status: 'acknowledged' })}>Acknowledge</Button>}
          {!a.reviewed && <Button size="xs" variant="success" onClick={() => updateIncident(a.alert_id, { status: 'resolved', disposition: 'true_alarm' })}>Resolve</Button>}
          {!a.reviewed && <Button size="xs" variant="outline" onClick={() => updateIncident(a.alert_id, { status: 'false_positive', disposition: 'false_alarm' })}>False alarm</Button>}
        </span>
      ),
    },
  ];

  return (
    <div>
      <Toolbar>
          <SearchInput placeholder="Search alerts…" value={query} onChange={e => setQuery(e.target.value)} />
          <Select value={level} onChange={e => setLevel(e.target.value)} className="w-auto">
            <option value="">All levels</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </Select>
          <Select value={reviewed} onChange={e => setReviewed(e.target.value)} className="w-auto">
            <option value="">All statuses</option>
            <option value="false">Unreviewed</option>
            <option value="true">Reviewed</option>
          </Select>
          <Select value={status} onChange={e => setStatus(e.target.value)} className="w-auto">
            <option value="">All workflow states</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="investigating">Investigating</option>
            <option value="resolved">Resolved</option>
            <option value="false_positive">False positive</option>
            <option value="reopened">Reopened</option>
          </Select>
          <Select value={camera} onChange={e => setCamera(e.target.value)} className="w-auto">
            <option value="">All cameras</option>
            {cameras.map(c => <option key={c.camera_id} value={c.camera_id}>{c.name}</option>)}
          </Select>
          <Input type="datetime-local" aria-label="From time" value={startTime} onChange={e => setStartTime(e.target.value)} className="w-auto" />
          <Input type="datetime-local" aria-label="To time" value={endTime} onChange={e => setEndTime(e.target.value)} className="w-auto" />
          <Button icon="rotate-right" onClick={load}>Refresh</Button>
        </Toolbar>

        {selected && (
          <Card title={`Incident ${selected.alert_id}`} icon="triangle-exclamation" className="mb-4">
            <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
              <div className="space-y-2 text-sm text-fg-muted">
                <p><span className="text-fg-subtle">Event:</span> {formatEventType(selected.event_type)}</p>
                <p><span className="text-fg-subtle">Camera:</span> {selected.camera_id}</p>
                <p><span className="text-fg-subtle">Opened:</span> {formatTime(selected.timestamp)}</p>
                <div className="flex flex-wrap gap-2 pt-2">
                  <Select aria-label="Incident status" value={selected.status ?? 'open'} onChange={e => updateIncident(selected.alert_id, { status: e.target.value })} className="w-auto">
                    {['open', 'acknowledged', 'investigating', 'resolved', 'false_positive', 'reopened'].map(value => <option key={value} value={value}>{value.replace('_', ' ')}</option>)}
                  </Select>
                  <Input aria-label="Assignee" placeholder="Assignee" value={assignee} onChange={e => setAssignee(e.target.value)} className="w-48" />
                  <Button size="xs" onClick={() => updateIncident(selected.alert_id, { assignee })}>Assign</Button>
                </div>
              </div>
              <div>
                <div className="max-h-36 space-y-2 overflow-auto rounded border border-default bg-surface p-3" aria-label="Incident notes">
                  {selected.notes?.length ? selected.notes.map((item, index) => <div key={`${item.created_at}-${index}`} className="text-sm"><span className="font-medium text-fg">{item.author}</span><span className="ml-2 text-xs text-fg-subtle">{formatTime(item.created_at)}</span><p className="text-fg-muted">{item.note}</p></div>) : <p className="text-sm text-fg-subtle">No investigation notes yet.</p>}
                </div>
                <div className="mt-2 flex gap-2">
                  <Input aria-label="New incident note" placeholder="Add an immutable investigation note" value={note} onChange={e => setNote(e.target.value)} />
                  <Button disabled={!note.trim()} onClick={() => updateIncident(selected.alert_id, { note: note.trim() })}>Add note</Button>
                  <Button variant="ghost" onClick={() => setSelected(null)}>Close</Button>
                </div>
              </div>
            </div>
          </Card>
        )}

        {loading ? (
          <Loading label="Loading alerts…" />
        ) : (
          <DataTable
            columns={columns}
            rows={alerts}
            rowKey={a => a.alert_id}
            pageSize={pageSize}
            emptyMessage="No alerts match these filters"
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
