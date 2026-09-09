import { useState, useEffect, useRef } from 'react';
import { Grid, html } from 'gridjs';
import 'gridjs/dist/theme/mermaid.css';
import { apiFetch, getRiskEmoji, formatEventType, formatTime } from '../api/client';
import type { Alert, Camera } from '../types';

export default function Alerts() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [filterLevel, setFilterLevel] = useState('');
  const [filterReviewed, setFilterReviewed] = useState('');
  const [filterCamera, setFilterCamera] = useState('');
  const [query, setQuery] = useState('');
  const gridRef = useRef<HTMLDivElement>(null);
  const gridInstance = useRef<Grid | null>(null);
  const rawRef = useRef<Alert[]>([]);

  useEffect(() => {
    apiFetch('/api/cameras').then(r => r.json()).then(setCameras).catch(console.error);
  }, []);

  const render = () => {
    const q = query.trim().toLowerCase();
    const rows = rawRef.current
      .filter(a => !q || [a.alert_id, a.event_type, a.camera_id, a.risk_level]
        .some(v => String(v ?? '').toLowerCase().includes(q)))
      .map(a => [
        html(`<span class="risk-badge ${a.risk_level}">${getRiskEmoji(a.risk_level)} ${a.risk_level}</span>`),
        a.alert_id,
        formatEventType(a.event_type),
        a.camera_id,
        formatTime(a.timestamp),
        a.risk_score?.toFixed(0) || 0,
        html(a.reviewed
          ? '<span style="color:var(--success)"><i class="fas fa-check"></i> Reviewed</span>'
          : '<span style="color:var(--warning)"><i class="fas fa-clock"></i> Pending</span>'),
        html(`
          <a href="/events/${a.event_id}" class="btn btn-xs">View</a>
          ${!a.reviewed ? `<button class="btn btn-xs btn-success" onclick="window.__reviewAlert('${a.alert_id}')">Review</button>` : ''}
        `),
      ]);

    if (gridInstance.current) {
      gridInstance.current.updateConfig({ data: rows }).forceRender();
    } else if (gridRef.current) {
      gridInstance.current = new Grid({
        columns: ['Level', 'Alert ID', 'Event Type', 'Camera', 'Time', 'Score', 'Status', 'Actions'],
        data: rows,
        search: false,
        sort: true,
        pagination: { limit: 15 },
        className: { table: 'data-table' },
      }).render(gridRef.current);
    }
  };

  const loadAlerts = async () => {
    let url = '/api/alerts?limit=200';
    if (filterLevel) url += `&risk_level=${filterLevel}`;
    if (filterReviewed) url += `&reviewed=${filterReviewed}`;
    if (filterCamera) url += `&camera_id=${filterCamera}`;
    try {
      const res = await apiFetch(url);
      rawRef.current = await res.json();
      render();
    } catch (err) {
      console.error('Failed to load alerts:', err);
    }
  };

  useEffect(() => {
    (window as unknown as Record<string, unknown>).__reviewAlert = async (alertId: string) => {
      try {
        await apiFetch(`/api/alerts/${alertId}/review`, { method: 'POST' });
        loadAlerts();
      } catch (err) {
        console.error('Review error:', err);
      }
    };
    loadAlerts();
    return () => { delete (window as unknown as Record<string, unknown>).__reviewAlert; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterLevel, filterReviewed, filterCamera]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { render(); }, [query]);

  return (
    <div className="list-page">
      <div className="filters-bar">
        <div className="filters-search">
          <i className="fas fa-magnifying-glass" />
          <input
            type="text" placeholder="Search alerts…"
            value={query} onChange={e => setQuery(e.target.value)}
          />
        </div>
        <select className="select-small" value={filterLevel} onChange={e => setFilterLevel(e.target.value)}>
          <option value="">All Levels</option>
          <option value="critical">🔴 Critical</option>
          <option value="high">🟠 High</option>
          <option value="medium">🟡 Medium</option>
          <option value="low">🟢 Low</option>
        </select>
        <select className="select-small" value={filterReviewed} onChange={e => setFilterReviewed(e.target.value)}>
          <option value="">All Status</option>
          <option value="false">Unreviewed</option>
          <option value="true">Reviewed</option>
        </select>
        <select className="select-small" value={filterCamera} onChange={e => setFilterCamera(e.target.value)}>
          <option value="">All Cameras</option>
          {cameras.map(c => <option key={c.camera_id} value={c.camera_id}>{c.name}</option>)}
        </select>
        <button onClick={loadAlerts} className="btn btn-sm"><i className="fas fa-rotate-right" /> Refresh</button>
      </div>

      <div className="table-container" ref={gridRef} />
    </div>
  );
}
