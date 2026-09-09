'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { pushToast } from '@/src/lib/toast';
import Card from '@/src/components/ui/Card';
import Badge from '@/src/components/ui/Badge';
import StatusDot from '@/src/components/ui/StatusDot';
import { Button } from '@/src/components/ui/Button';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import { Loading } from '@/src/components/ui/States';
import type { Zone } from '@/src/types';

export default function ZonesPage() {
  const { role } = useAuth();
  const isAdmin = role === 'admin';
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch('/api/zones')
      .then(r => r.json())
      .then(z => { setZones(z); setLoading(false); })
      .catch(err => console.error('Failed to load zones:', err));
  }, []);

  useEffect(() => { load(); }, [load]);

  const remove = async (zoneId: string) => {
    setBusy(zoneId);
    try {
      const res = await apiFetch(`/api/zones/${zoneId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(String(res.status));
      pushToast({ title: 'Zone deleted', message: zoneId });
      load();
    } catch (err) {
      console.error('Failed to delete zone:', err);
      pushToast({ title: 'Delete failed', message: `Could not delete ${zoneId}`, level: 'high' });
    } finally {
      setBusy(null);
      setConfirming(null);
    }
  };

  const columns: Column<Zone>[] = [
    { key: 'zone_id', header: 'Zone ID', sortable: true, className: 'font-mono text-[0.78rem]' },
    { key: 'name', header: 'Name', sortable: true },
    { key: 'camera_id', header: 'Camera', sortable: true },
    { key: 'type', header: 'Type', sortable: true, render: z => <Badge>{z.type}</Badge> },
    {
      key: 'enabled', header: 'Status', sortable: true,
      accessor: z => (z.enabled ? 'active' : 'disabled'),
      render: z => (
        <span className="inline-flex items-center gap-2 text-[0.82rem] text-fg-muted">
          <StatusDot status={z.enabled ? 'online' : 'offline'} />
          {z.enabled ? 'Active' : 'Disabled'}
        </span>
      ),
    },
    ...(isAdmin
      ? [{
          key: 'actions', header: 'Actions', align: 'right' as const,
          render: (z: Zone) => confirming === z.zone_id ? (
            <span className="inline-flex justify-end gap-1.5">
              <Button size="xs" variant="danger" disabled={busy === z.zone_id} onClick={() => remove(z.zone_id)}>Confirm</Button>
              <Button size="xs" variant="ghost" onClick={() => setConfirming(null)}>Cancel</Button>
            </span>
          ) : (
            <Button size="xs" variant="outline" icon="trash" onClick={() => setConfirming(z.zone_id)}>Delete</Button>
          ),
        }]
      : []),
  ];

  return (
    <Card title="Configured Zones" icon="draw-polygon" bodyClassName="p-0">
      {loading ? (
        <Loading label="Loading zones…" />
      ) : (
        <DataTable columns={columns} rows={zones} rowKey={z => z.zone_id} emptyMessage="No zones configured" />
      )}
    </Card>
  );
}
