'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiFetch, formatEventType, formatTime } from '@/src/api/client';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import RiskBadge from '@/src/components/ui/RiskBadge';
import Icon from '@/src/components/ui/Icon';
import { Button, ButtonLink } from '@/src/components/ui/Button';
import { SearchInput, Select } from '@/src/components/ui/Field';
import { Toolbar } from '@/src/components/ui/Toolbar';
import { Loading } from '@/src/components/ui/States';
import type { Alert, Camera } from '@/src/types';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [level, setLevel] = useState('');
  const [reviewed, setReviewed] = useState('');
  const [camera, setCamera] = useState('');

  useEffect(() => {
    apiFetch('/api/cameras').then(r => r.json()).then(setCameras).catch(console.error);
  }, []);

  const load = useCallback(async () => {
    let url = '/api/alerts?limit=200';
    if (level) url += `&risk_level=${level}`;
    if (reviewed) url += `&reviewed=${reviewed}`;
    if (camera) url += `&camera_id=${camera}`;
    try {
      const res = await apiFetch(url);
      setAlerts(await res.json());
    } catch (err) {
      console.error('Failed to load alerts:', err);
    } finally {
      setLoading(false);
    }
  }, [level, reviewed, camera]);

  useEffect(() => { load(); }, [load]);

  const review = async (alertId: string) => {
    try {
      await apiFetch(`/api/alerts/${alertId}/review`, { method: 'POST' });
      load();
    } catch (err) {
      console.error('Review error:', err);
    }
  };

  const columns: Column<Alert>[] = [
    { key: 'risk_level', header: 'Level', sortable: true, render: a => <RiskBadge level={a.risk_level} /> },
    { key: 'alert_id', header: 'Alert ID', sortable: true, className: 'font-mono text-[0.78rem]' },
    { key: 'event_type', header: 'Type', sortable: true, accessor: a => formatEventType(a.event_type), render: a => formatEventType(a.event_type) },
    { key: 'camera_id', header: 'Camera', sortable: true },
    { key: 'timestamp', header: 'Time', sortable: true, accessor: a => a.timestamp, render: a => formatTime(a.timestamp) },
    { key: 'risk_score', header: 'Score', sortable: true, align: 'right', accessor: a => a.risk_score ?? 0, render: a => (a.risk_score?.toFixed(0) ?? 0) },
    {
      key: 'reviewed', header: 'Status', sortable: true,
      accessor: a => (a.reviewed ? 'reviewed' : 'pending'),
      render: a => a.reviewed
        ? <span className="inline-flex items-center gap-1.5 text-[0.78rem] text-success"><Icon name="check" /> Reviewed</span>
        : <span className="inline-flex items-center gap-1.5 text-[0.78rem] text-warning"><Icon name="clock" /> Pending</span>,
    },
    {
      key: 'actions', header: 'Actions', align: 'right',
      render: a => (
        <span className="inline-flex justify-end gap-1.5">
          <ButtonLink href={`/event?id=${a.event_id}`} size="xs" variant="outline">View</ButtonLink>
          {!a.reviewed && <Button size="xs" variant="success" onClick={() => review(a.alert_id)}>Review</Button>}
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
        <Select value={camera} onChange={e => setCamera(e.target.value)} className="w-auto">
          <option value="">All cameras</option>
          {cameras.map(c => <option key={c.camera_id} value={c.camera_id}>{c.name}</option>)}
        </Select>
        <Button icon="rotate-right" onClick={load}>Refresh</Button>
      </Toolbar>

      {loading ? (
        <Loading label="Loading alerts…" />
      ) : (
        <DataTable
          columns={columns}
          rows={alerts}
          rowKey={a => a.alert_id}
          search={query}
          emptyMessage="No alerts match these filters"
        />
      )}
    </div>
  );
}
