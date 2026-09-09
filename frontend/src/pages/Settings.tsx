import { useState, useEffect, type ReactNode } from 'react';
import { apiFetch } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import Card from '../components/ui/Card';
import type { DashboardSummary } from '../types';

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="setting-row">
      <span className="setting-label">{label}</span>
      <span className="setting-value">{children}</span>
    </div>
  );
}

export default function Settings() {
  const { user, role, logout } = useAuth();
  const { isLight, toggleTheme } = useTheme();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  const username = user?.email?.split('@')[0] || 'User';

  useEffect(() => {
    apiFetch('/api/statistics/summary').then(r => r.json()).then(setSummary).catch(() => setSummary(null));
    apiFetch('/api/health').then(r => setBackendOk(r.ok)).catch(() => setBackendOk(false));
  }, []);

  const online = summary?.online_cameras ?? 0;
  const total = summary?.total_cameras ?? 0;
  const camPct = total ? Math.round((online / total) * 100) : 0;

  return (
    <div className="settings-page">
      <div className="settings-grid">
        <Card title="Profile" icon="fas fa-id-badge">
          <div className="setting-list">
            <Row label="Name">{username}</Row>
            <Row label="Email">{user?.email || '—'}</Row>
            <Row label="Role">
              <span className={`role-badge role-${role ?? 'unknown'}`}>{role ?? 'unknown'}</span>
            </Row>
            <Row label="Assigned areas">
              {user ? 'All areas' : '—'}
            </Row>
          </div>
        </Card>

        <Card title="System Health" icon="fas fa-heart-pulse">
          <div className="setting-list">
            <Row label="Backend">
              <span className={`status-pill ${backendOk ? 'ok' : backendOk === false ? 'down' : ''}`}>
                <span className={`status-dot ${backendOk ? 'online' : 'offline'}`} />
                {backendOk == null ? 'Checking…' : backendOk ? 'Online' : 'Unreachable'}
              </span>
            </Row>
            <div className="setting-row">
              <span className="setting-label">Cameras online</span>
              <span className="setting-value" style={{ minWidth: 0, flex: 1 }}>
                <span className="health-bar"><span className="health-bar-fill" style={{ width: `${camPct}%` }} /></span>
                <span className="health-bar-text">{online}/{total}</span>
              </span>
            </div>
            <Row label="Active alerts">{summary?.unreviewed_alerts ?? 0}</Row>
            <Row label="Active tracks">{summary?.active_tracks ?? 0}</Row>
            <Row label="Total alerts (24h)">{summary?.total_alerts ?? 0}</Row>
          </div>
        </Card>

        <Card title="Appearance" icon="fas fa-palette">
          <div className="setting-list">
            <div className="setting-row">
              <span className="setting-label">Theme</span>
              <span className="setting-value">
                <div className="seg-control" role="group" aria-label="Theme">
                  <button className={`seg ${!isLight ? 'seg-active' : ''}`} onClick={() => { if (isLight) toggleTheme(); }}>
                    <i className="fas fa-moon" /> Dark
                  </button>
                  <button className={`seg ${isLight ? 'seg-active' : ''}`} onClick={() => { if (!isLight) toggleTheme(); }}>
                    <i className="fas fa-sun" /> Light
                  </button>
                </div>
              </span>
            </div>
          </div>
        </Card>

        <Card title="Session" icon="fas fa-right-from-bracket">
          <div className="setting-list">
            <Row label="Signed in as">{user?.email || username}</Row>
            <p className="setting-note">Sessions expire automatically after inactivity. Sign out on shared machines.</p>
            <button className="btn btn-danger btn-sm" onClick={logout}>
              <i className="fas fa-power-off" /> Sign out
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}
