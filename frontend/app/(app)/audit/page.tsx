'use client';

import { useCallback, useEffect, useState } from 'react';
import { ArrowClockwise } from '@phosphor-icons/react';
import { apiJson, errorMessage, formatStatus, formatTime, toDate } from '@/src/api/client';
import { Button } from '@/src/components/ui/Button';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import { SearchInput } from '@/src/components/ui/Field';
import { Toolbar } from '@/src/components/ui/Section';
import SegmentedControl from '@/src/components/ui/SegmentedControl';
import { describeAudit } from '@/src/lib/audit';
import { EmptyState } from '@/src/components/ui/States';
import type { AuditEntry } from '@/src/types';

function detailsText(details: unknown): string {
  if (details == null || details === '') return '';
  return typeof details === 'string' ? details : JSON.stringify(details);
}

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState<'actions' | 'all'>('actions');

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setRows(await apiJson<AuditEntry[]>(`/api/audit?limit=200${scope === 'actions' ? '&actions_only=true' : ''}`));
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [scope]);

  useEffect(() => { void load(); }, [load]);

  const columns: Column<AuditEntry>[] = [
    {
      key: 'timestamp', header: 'Time', sortable: true,
      accessor: row => toDate(row.timestamp)?.getTime() ?? 0,
      render: row => <span className="num whitespace-nowrap text-muted">{formatTime(row.timestamp)}</span>,
    },
    { key: 'username', header: 'User', sortable: true, render: row => <span className="font-medium">{row.username}</span> },
    {
      key: 'action', header: 'Action', sortable: true,
      accessor: row => `${describeAudit(row.action, row.details) ?? ''} ${row.action}`,
      render: row => {
        const summary = describeAudit(row.action, row.details);
        return summary
          ? <span title={formatStatus(row.action)}>{summary}</span>
          : <span className="font-mono text-xs">{row.action.includes(' /') ? row.action : formatStatus(row.action)}</span>;
      },
    },
    {
      key: 'ip_address', header: 'IP address', hideBelow: 'md', accessor: row => row.ip_address ?? '',
      render: row => <span className="num font-mono text-xs text-muted" translate="no">{row.ip_address || 'Not recorded'}</span>,
    },
    {
      key: 'details', header: 'Details', hideBelow: 'lg', accessor: row => detailsText(row.details),
      render: row => {
        const text = detailsText(row.details);
        return text
          ? <span className="block max-w-md truncate font-mono text-xs text-muted" title={text}>{text}</span>
          : <span className="text-muted">None</span>;
      },
    },
  ];

  return (
    <div>
      <Toolbar>
        <SegmentedControl
          ariaLabel="Audit entries to show"
          value={scope}
          onChange={value => { setScope(value); setLoading(true); }}
          options={[{ value: 'actions', label: 'User actions' }, { value: 'all', label: 'All requests' }]}
        />
        <SearchInput placeholder="Filter by user, action or IP…" aria-label="Filter audit log" value={query}
          onChange={e => setQuery(e.target.value)} wrapperClassName="w-full sm:w-80" />
        <span className="num text-sm text-muted">Latest {rows.length} entries</span>
        <Button variant="ghost" className="ml-auto" icon={<ArrowClockwise size={14} />} loading={refreshing && !loading} onClick={() => void load()}>
          Refresh
        </Button>
      </Toolbar>

      {error && rows.length === 0 && !loading ? (
        <EmptyState
          title="The audit log could not be loaded"
          description={error.includes('403') || /forbidden|permission/i.test(error) ? 'Only administrators, commanders and auditors can view the audit log.' : error}
          action={<Button onClick={() => void load()}>Try again</Button>}
        />
      ) : (
        <DataTable
          label="Audit log"
          columns={columns}
          rows={rows}
          rowKey={row => String(row.id)}
          search={query}
          loading={loading}
          emptyTitle={query ? 'No entries match this filter' : 'No audit entries yet'}
        />
      )}
    </div>
  );
}
