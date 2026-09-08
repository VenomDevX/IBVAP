import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Card from '../components/ui/Card';
import type { Zone } from '../types';

export default function Zones() {
  const { role } = useAuth();
  const isAdmin = role === 'admin';
  const [zones, setZones] = useState<Zone[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch('/api/zones')
      .then(r => r.json())
      .then(setZones)
      .catch(err => console.error('Failed to load zones:', err));
  }, []);

  useEffect(() => { load(); }, [load]);

  const removeZone = async (zoneId: string) => {
    if (!window.confirm(`Delete zone ${zoneId}? Detections in this zone will stop.`)) return;
    setBusy(zoneId);
    try {
      const res = await apiFetch(`/api/zones/${zoneId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(String(res.status));
      load();
    } catch (err) {
      console.error('Failed to delete zone:', err);
      alert('Could not delete the zone.');
    } finally {
      setBusy(null);
    }
  };

  const colCount = isAdmin ? 6 : 5;

  return (
    <div className="zones-layout">
      <Card title="Configured Zones" icon="fas fa-draw-polygon">
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Zone ID</th><th>Name</th><th>Camera</th><th>Type</th><th>Status</th>
                {isAdmin && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {zones.length === 0 ? (
                <tr><td colSpan={colCount} className="text-center">No zones configured</td></tr>
              ) : (
                zones.map(z => (
                  <tr key={z.zone_id}>
                    <td className="mono">{z.zone_id}</td>
                    <td>{z.name}</td>
                    <td>{z.camera_id}</td>
                    <td><span className={`zone-type-badge ${z.type}`}>{z.type}</span></td>
                    <td>
                      <span className={`status-dot ${z.enabled ? 'online' : 'offline'}`} />
                      {' '}{z.enabled ? 'Active' : 'Disabled'}
                    </td>
                    {isAdmin && (
                      <td>
                        <button
                          className="btn btn-xs btn-outline"
                          disabled={busy === z.zone_id}
                          onClick={() => removeZone(z.zone_id)}
                        >
                          <i className="fas fa-trash" /> Delete
                        </button>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
