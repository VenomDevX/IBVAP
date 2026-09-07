import { useState, useEffect } from 'react';
import { apiFetch } from '../api/client';
import Card from '../components/ui/Card';
import type { Zone } from '../types';

export default function Zones() {
  const [zones, setZones] = useState<Zone[]>([]);

  useEffect(() => {
    apiFetch('/api/zones')
      .then(r => r.json())
      .then(setZones)
      .catch(err => console.error('Failed to load zones:', err));
  }, []);

  return (
    <div className="zones-layout">
      <Card title="Configured Zones" icon="fas fa-draw-polygon">
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr><th>Zone ID</th><th>Name</th><th>Camera</th><th>Type</th><th>Status</th></tr>
            </thead>
            <tbody>
              {zones.length === 0 ? (
                <tr><td colSpan={5} className="text-center">No zones configured</td></tr>
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
