import { useState, useEffect, useRef } from 'react';
import { Grid, html } from 'gridjs';
import 'gridjs/dist/theme/mermaid.css';
import { apiFetch, formatTime } from '../api/client';

interface AuditEntry {
  id: number;
  timestamp: string | number;
  username: string;
  action: string;
  ip_address?: string;
  details?: unknown;
}

export default function AuditLog() {
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const gridRef = useRef<HTMLDivElement>(null);
  const gridInstance = useRef<Grid | null>(null);
  const rawRef = useRef<AuditEntry[]>([]);

  const render = () => {
    const q = query.trim().toLowerCase();
    const rows = rawRef.current
      .filter(l => !q || [l.username, l.action, l.ip_address, JSON.stringify(l.details)]
        .some(v => String(v ?? '').toLowerCase().includes(q)))
      .map(l => [
        l.id,
        formatTime(l.timestamp),
        html(`<strong>${l.username}</strong>`),
        l.action,
        l.ip_address || 'N/A',
        html(`<pre style="margin:0;font-size:0.8em;white-space:pre-wrap;">${JSON.stringify(l.details, null, 2)}</pre>`),
      ]);

    if (gridInstance.current) {
      gridInstance.current.updateConfig({ data: rows }).forceRender();
    } else if (gridRef.current) {
      gridInstance.current = new Grid({
        columns: ['ID', 'Timestamp', 'User', 'Action', 'IP Address', 'Details'],
        data: rows,
        search: false,
        sort: true,
        pagination: { limit: 15 },
        className: { table: 'data-table' },
      }).render(gridRef.current);
    }
  };

  const loadLogs = async () => {
    try {
      const res = await apiFetch('/api/audit?limit=200');
      rawRef.current = await res.json();
      render();
    } catch (err) {
      console.error('Failed to load audit logs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadLogs(); }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { render(); }, [query]);

  return (
    <div className="list-page">
      <div className="filters-bar">
        <div className="filters-search">
          <i className="fas fa-magnifying-glass" />
          <input
            type="text" placeholder="Search by user, action, IP…"
            value={query} onChange={e => setQuery(e.target.value)}
          />
        </div>
        <button onClick={loadLogs} className="btn btn-sm"><i className="fas fa-rotate-right" /> Refresh</button>
      </div>

      {loading && <div className="loading"><i className="fas fa-spinner fa-spin" /> Loading Logs…</div>}
      <div className="table-container" ref={gridRef} />
    </div>
  );
}
