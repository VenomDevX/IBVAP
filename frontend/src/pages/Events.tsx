import { useState, useEffect, useRef } from 'react';
import { Grid, html } from 'gridjs';
import 'gridjs/dist/theme/mermaid.css';
import { apiFetch, getRiskEmoji, formatEventType, formatTime } from '../api/client';
import type { Event } from '../types';

export default function Events() {
  const [filterType, setFilterType] = useState('');
  const [filterRisk, setFilterRisk] = useState('');
  const [query, setQuery] = useState('');
  const gridRef = useRef<HTMLDivElement>(null);
  const gridInstance = useRef<Grid | null>(null);
  const rawRef = useRef<Event[]>([]);

  const render = () => {
    const q = query.trim().toLowerCase();
    const rows = rawRef.current
      .filter(e => !q || [e.event_id, e.event_type, e.camera_id, e.object_type, e.risk_level]
        .some(v => String(v ?? '').toLowerCase().includes(q)))
      .map(e => [
        html(`<span class="risk-badge ${e.risk_level}">${getRiskEmoji(e.risk_level)}</span>`),
        e.event_id,
        formatEventType(e.event_type),
        e.camera_id,
        e.object_type,
        formatTime(e.timestamp),
        e.risk_score?.toFixed(0) || 0,
        (e.contributing_factors || []).slice(0, 2).join(', '),
        html(`<a href="/events/${e.event_id}" class="btn btn-xs">View</a>`),
      ]);

    if (gridInstance.current) {
      gridInstance.current.updateConfig({ data: rows }).forceRender();
    } else if (gridRef.current) {
      gridInstance.current = new Grid({
        columns: ['Risk', 'Event ID', 'Type', 'Camera', 'Object', 'Time', 'Score', 'Factors', 'Details'],
        data: rows,
        search: false,
        sort: true,
        pagination: { limit: 15 },
        className: { table: 'data-table' },
      }).render(gridRef.current);
    }
  };

  const loadEvents = async () => {
    let url = '/api/events?limit=100';
    if (filterType) url += `&event_type=${filterType}`;
    if (filterRisk) url += `&risk_level=${filterRisk}`;
    try {
      const res = await apiFetch(url);
      rawRef.current = await res.json();
      render();
    } catch (err) {
      console.error('Failed to load events:', err);
    }
  };

  useEffect(() => {
    loadEvents();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterType, filterRisk]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { render(); }, [query]);

  return (
    <div className="list-page">
      <div className="filters-bar">
        <div className="filters-search">
          <i className="fas fa-magnifying-glass" />
          <input
            type="text" placeholder="Search events…"
            value={query} onChange={e => setQuery(e.target.value)}
          />
        </div>
        <select className="select-small" value={filterType} onChange={e => setFilterType(e.target.value)}>
          <option value="">All Types</option>
          <option value="restricted_zone_entry">Zone Entry</option>
          <option value="fence_crossing">Fence Crossing</option>
          <option value="loitering">Loitering</option>
          <option value="night_movement">Night Movement</option>
          <option value="combined_suspicious_activity">Combined Suspicious</option>
        </select>
        <select className="select-small" value={filterRisk} onChange={e => setFilterRisk(e.target.value)}>
          <option value="">All Risk Levels</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <button onClick={loadEvents} className="btn btn-sm"><i className="fas fa-rotate-right" /> Refresh</button>
      </div>

      <div className="table-container" ref={gridRef} />
    </div>
  );
}
