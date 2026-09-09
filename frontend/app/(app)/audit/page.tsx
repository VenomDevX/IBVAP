'use client';

import { useEffect, useState } from 'react';
import { apiFetch, formatTime } from '@/src/api/client';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import { Button } from '@/src/components/ui/Button';
import { SearchInput } from '@/src/components/ui/Field';
import { Toolbar } from '@/src/components/ui/Toolbar';
import { Loading } from '@/src/components/ui/States';

interface AuditEntry {
  id: number;
  timestamp: string | number;
  username: string;
  action: string;
  ip_address?: string;
  details?: unknown;
}

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');

  const load = async () => {
    try {
      const res = await apiFetch('/api/audit?limit=200');
      setRows(await res.json());
    } catch (err) {
      console.error('Failed to load audit logs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const columns: Column<AuditEntry>[] = [
    { key: 'id', header: 'ID', sortable: true, align: 'right', accessor: r => r.id },
    { key: 'timestamp', header: 'Timestamp', sortable: true, accessor: r => r.timestamp, render: r => formatTime(r.timestamp) },
    { key: 'username', header: 'User', sortable: true, render: r => <span className="font-medium text-fg">{r.username}</span> },
    { key: 'action', header: 'Action', sortable: true },
    { key: 'ip_address', header: 'IP Address', accessor: r => r.ip_address ?? '', render: r => r.ip_address || '—' },
    {
      key: 'details', header: 'Details',
      accessor: r => JSON.stringify(r.details ?? ''),
      render: r => (
        <pre className="max-w-md overflow-x-auto whitespace-pre-wrap font-mono text-[0.72rem] text-fg-muted">
          {JSON.stringify(r.details, null, 2)}
        </pre>
      ),
    },
  ];

  return (
    <div>
      <Toolbar>
        <SearchInput placeholder="Search by user, action, IP…" value={query} onChange={e => setQuery(e.target.value)} />
        <Button icon="rotate-right" onClick={load}>Refresh</Button>
      </Toolbar>

      {loading ? (
        <Loading label="Loading audit log…" />
      ) : (
        <DataTable columns={columns} rows={rows} rowKey={r => String(r.id)} search={query} emptyMessage="No audit entries" />
      )}
    </div>
  );
}
