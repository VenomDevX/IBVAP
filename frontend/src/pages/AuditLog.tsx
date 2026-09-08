import { useState, useEffect, useRef } from 'react';
import { Grid, html } from 'gridjs';
import 'gridjs/dist/theme/mermaid.css';
import { apiFetch, formatTime } from '../api/client';

export default function AuditLog() {
  const [loading, setLoading] = useState(true);
  const gridRef = useRef<HTMLDivElement>(null);
  const gridInstance = useRef<Grid | null>(null);

  const loadLogs = async () => {
    try {
      const res = await apiFetch('/api/audit?limit=200');
      const logs: any[] = await res.json();

      const mappedData = logs.map(l => [
        l.id,
        formatTime(l.timestamp),
        html(`<strong>${l.username}</strong>`),
        l.action,
        l.ip_address || 'N/A',
        html(`<pre style="margin:0;font-size:0.8em;white-space:pre-wrap;">${JSON.stringify(l.details, null, 2)}</pre>`),
      ]);

      if (gridInstance.current) {
        gridInstance.current.updateConfig({ data: mappedData }).forceRender();
      } else if (gridRef.current) {
        gridInstance.current = new Grid({
          columns: ['ID', 'Timestamp', 'User', 'Action', 'IP Address', 'Details'],
          data: mappedData,
          search: true,
          sort: true,
          pagination: { limit: 15 },
          className: { table: 'data-table' },
        }).render(gridRef.current);
      }
      setLoading(false);
    } catch (err) {
      console.error('Failed to load audit logs:', err);
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  return (
    <div className="audit-page">
      <div className="page-header" style={{ marginBottom: '1rem' }}>
        <h2><i className="fas fa-clipboard-list"></i> System Audit Logs</h2>
      </div>
      
      {loading && <div className="loading"><i className="fas fa-spinner fa-spin" /> Loading Logs...</div>}
      
      <div ref={gridRef} />
    </div>
  );
}
