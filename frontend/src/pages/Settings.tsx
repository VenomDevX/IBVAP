import { useState, useEffect } from 'react';
import { apiFetch } from '../api/client';
import { useAuth } from '../context/AuthContext';
import Card from '../components/ui/Card';
import type { DashboardSummary } from '../types';

export default function Settings() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const { user, role } = useAuth();
  const username = user?.email?.split('@')[0] || 'User';

  useEffect(() => {
    apiFetch('/api/statistics/summary').then(r => r.json()).then(setSummary).catch(() => {});
  }, []);

  return (
    <div className="settings-grid">
      <Card title="User Info" icon="fas fa-user-cog">
        <div className="context-info">
          <p><strong>Username:</strong> {username}</p>
          <p><strong>Role:</strong> <span className="mono">{role ?? '—'}</span></p>
          <p><strong>Email:</strong> {user?.email || '—'}</p>
        </div>
      </Card>
      <Card title="System Info" icon="fas fa-server">
        <div className="context-info">
          {summary ? (
            <>
              <p><strong>Total Cameras:</strong> {summary.total_cameras || 0}</p>
              <p><strong>Online Cameras:</strong> {summary.online_cameras || 0}</p>
              <p><strong>Total Alerts:</strong> {summary.total_alerts || 0}</p>
              <p><strong>Active Tracks:</strong> {summary.active_tracks || 0}</p>
            </>
          ) : <p>Loading…</p>}
        </div>
      </Card>
    </div>
  );
}
