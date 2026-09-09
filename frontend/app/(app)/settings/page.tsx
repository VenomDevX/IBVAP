'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { apiFetch } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { useTheme } from '@/src/context/ThemeContext';
import { cn } from '@/src/lib/cn';
import Card from '@/src/components/ui/Card';
import Badge from '@/src/components/ui/Badge';
import StatusDot from '@/src/components/ui/StatusDot';
import SegmentedControl from '@/src/components/ui/SegmentedControl';
import { Button } from '@/src/components/ui/Button';
import type { DashboardSummary } from '@/src/types';

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-default py-2.5 text-[0.85rem] last:border-0">
      <span className="text-fg-muted">{label}</span>
      <span className="flex items-center gap-2 text-right text-fg">{children}</span>
    </div>
  );
}

const ROLE_TONE = { admin: 'accent', operator: 'info', auditor: 'warning' } as const;

export default function SettingsPage() {
  const { user, role, logout } = useAuth();
  const { isLight, setTheme } = useTheme();
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
    <div className="grid items-start gap-4 md:grid-cols-2">
      <Card title="Profile" icon="id-badge">
        <Row label="Name">{username}</Row>
        <Row label="Email">{user?.email || '—'}</Row>
        <Row label="Role">
          <Badge tone={ROLE_TONE[(role ?? 'operator') as keyof typeof ROLE_TONE] ?? 'neutral'}>{role ?? 'unknown'}</Badge>
        </Row>
        <Row label="Assigned areas">{user ? 'All areas' : '—'}</Row>
      </Card>

      <Card title="System Health" icon="heart-pulse">
        <Row label="Backend">
          <StatusDot status={backendOk ? 'online' : 'offline'} />
          <span className={cn(backendOk ? 'text-success' : backendOk === false ? 'text-danger' : 'text-fg-muted')}>
            {backendOk == null ? 'Checking…' : backendOk ? 'Online' : 'Unreachable'}
          </span>
        </Row>
        <div className="flex items-center justify-between gap-4 border-b border-default py-2.5 text-[0.85rem]">
          <span className="text-fg-muted">Cameras online</span>
          <span className="flex items-center gap-2">
            <span className="inline-block h-1.5 w-24 overflow-hidden rounded-full bg-default">
              <span className="block h-full bg-success" style={{ width: `${camPct}%` }} />
            </span>
            <span className="tabular-nums text-fg">{online}/{total}</span>
          </span>
        </div>
        <Row label="Active alerts">{summary?.unreviewed_alerts ?? 0}</Row>
        <Row label="Active tracks">{summary?.active_tracks ?? 0}</Row>
        <Row label="Total alerts (24h)">{summary?.total_alerts ?? 0}</Row>
      </Card>

      <Card title="Appearance" icon="palette">
        <Row label="Theme">
          <SegmentedControl
            ariaLabel="Theme"
            value={isLight ? 'light' : 'dark'}
            onChange={v => setTheme(v === 'light')}
            options={[
              { value: 'dark', label: 'Dark', icon: 'moon' },
              { value: 'light', label: 'Light', icon: 'sun' },
            ]}
          />
        </Row>
      </Card>

      <Card title="Session" icon="right-from-bracket">
        <Row label="Signed in as">{user?.email || username}</Row>
        <p className="py-2.5 text-[0.8rem] leading-relaxed text-fg-subtle">
          Sessions expire automatically after inactivity. Sign out on shared machines.
        </p>
        <Button variant="danger" icon="power-off" onClick={logout}>Sign out</Button>
      </Card>
    </div>
  );
}
