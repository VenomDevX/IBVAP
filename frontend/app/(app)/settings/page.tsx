'use client';

import { Suspense, useEffect, useState, type ReactNode } from 'react';
import { SignOut } from '@phosphor-icons/react';
import { useRouter } from 'next/navigation';
import { apiJson, formatNumber, formatStatus } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { useTheme, type ThemePreference } from '@/src/context/ThemeContext';
import { useSystemHealth } from '@/src/hooks/useSystemHealth';
import { useUrlState } from '@/src/hooks/useUrlState';
import { cn } from '@/src/lib/cn';
import { Button } from '@/src/components/ui/Button';
import Section from '@/src/components/ui/Section';
import { Dot } from '@/src/components/ui/Indicators';
import { Loading } from '@/src/components/ui/States';
import type { DashboardSummary } from '@/src/types';

const TABS = [
  { id: 'profile', label: 'Profile' },
  { id: 'appearance', label: 'Appearance' },
  { id: 'health', label: 'System health' },
] as const;

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 border-b border-line/70 py-3 text-sm last:border-0 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-6">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-fg">{children}</dd>
    </div>
  );
}

function Health({ ok, children, tone }: { ok: boolean; children: ReactNode; tone?: 'warn' }) {
  return (
    <span className="inline-flex items-center gap-2">
      <Dot color={ok ? 'var(--ok)' : tone === 'warn' ? 'var(--warn)' : 'var(--bad)'} />
      {children}
    </span>
  );
}

function ProfileTab() {
  const router = useRouter();
  const { user, role, allowedAreas, profileError, logout } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  const access = profileError
    ? 'Your permissions could not be loaded. Try signing in again.'
    : role === 'admin'
      ? 'All cameras'
      : allowedAreas?.length
        ? allowedAreas.join(', ')
        : 'No cameras assigned. Ask an administrator for access.';

  return (
    <div className="space-y-10">
      <Section title="Account">
        <dl>
          <Row label="Username">{user?.email?.split('@')[0] ?? 'Unknown'}</Row>
          <Row label="Email">{user?.email ?? 'Unknown'}</Row>
          <Row label="Role">{role ? formatStatus(role) : profileError ? 'Unavailable' : 'Loading…'}</Row>
          <Row label="Camera access">{access}</Row>
        </dl>
      </Section>
      <Section title="Session" description="You are signed out automatically after 30 minutes without activity.">
        <Button variant="danger" icon={<SignOut size={14} />} loading={signingOut}
          onClick={async () => { setSigningOut(true); await logout(); router.replace('/login'); }}>
          Sign out
        </Button>
      </Section>
    </div>
  );
}

const THEME_OPTIONS: { value: ThemePreference; label: string; hint: string }[] = [
  { value: 'system', label: 'System', hint: 'Follows your device setting' },
  { value: 'light', label: 'Light', hint: 'For bright rooms' },
  { value: 'dark', label: 'Dark', hint: 'For control rooms and night shifts' },
];

function ThemePreview({ kind }: { kind: ThemePreference }) {
  const pane = (bg: string, line: string, accent: string) => (
    <div className="flex h-full flex-col justify-end gap-1.5 p-2.5" style={{ background: bg }}>
      <span className="block h-1.5 w-3/4 rounded-full" style={{ background: line }} />
      <span className="block h-1.5 w-1/2 rounded-full" style={{ background: line }} />
      <span className="block h-1.5 w-1/4 rounded-full" style={{ background: accent }} />
    </div>
  );
  const light = pane('#fafaf9', '#e7e5e2', '#0f766e');
  const dark = pane('#161514', '#2e2c2a', '#5eb8ae');
  return (
    <div aria-hidden className="grid h-16 overflow-hidden rounded-md" style={{ gridTemplateColumns: kind === 'system' ? '1fr 1fr' : '1fr' }}>
      {kind === 'dark' ? dark : light}
      {kind === 'system' && dark}
    </div>
  );
}

function AppearanceTab() {
  const { preference, setPreference } = useTheme();
  return (
    <fieldset>
      <legend className="text-base font-medium">Theme</legend>
      <p className="text-sm text-muted">Saved in this browser only.</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {THEME_OPTIONS.map(option => {
          const checked = preference === option.value;
          return (
            <label
              key={option.value}
              className={cn(
                'cursor-pointer rounded-lg p-2.5 transition-shadow duration-150',
                'has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-accent',
                checked ? 'shadow-[0_0_0_2px_var(--accent)]' : 'shadow-[0_0_0_1px_var(--line)] hover:shadow-[0_0_0_1px_var(--line-strong)]',
              )}
            >
              <input type="radio" name="theme" value={option.value} checked={checked}
                onChange={() => setPreference(option.value)} className="sr-only" />
              <ThemePreview kind={option.value} />
              <span className="mt-2.5 block text-sm font-medium text-fg">{option.label}</span>
              <span className="block text-xs text-muted">{option.hint}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function HealthTab() {
  const { health, reachable } = useSystemHealth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    apiJson<DashboardSummary>('/api/statistics/summary').then(setSummary).catch(() => setSummary(null));
  }, []);

  if (reachable === null) return <Loading label="Checking services…" />;

  const storage = health?.storage;
  const overLimit = storage?.snapshot_storage_mb != null && storage.snapshot_storage_mb > storage.snapshot_storage_limit_mb;

  return (
    <div className="space-y-10">
      <Section title="Services">
        <dl>
          <Row label="API">
            {reachable === false
              ? <Health ok={false}>Unreachable</Health>
              : <Health ok={!!health?.ready} tone="warn">{health?.ready ? 'Operational' : 'Degraded'}</Health>}
          </Row>
          <Row label="Video pipeline">
            <Health ok={health?.pipeline === 'ready'} tone={health?.pipeline === 'starting' ? 'warn' : undefined}>
              {formatStatus(health?.pipeline ?? 'unknown')}
            </Health>
          </Row>
          <Row label="Object detector"><Health ok={!!health?.models?.detector}>{health?.models?.detector ? 'Loaded' : 'Not loaded'}</Health></Row>
          <Row label="Fine classifier"><Health ok={!!health?.models?.fine_classifier} tone="warn">{health?.models?.fine_classifier ? 'Loaded' : 'Not loaded'}</Health></Row>
          <Row label="Face recognition"><Health ok={!!health?.models?.face_recognition} tone="warn">{health?.models?.face_recognition ? 'Loaded' : 'Disabled'}</Health></Row>
        </dl>
      </Section>

      <Section title="Operations">
        <dl>
          <Row label="Cameras online">
            <span className="num">{health ? `${health.cameras.online} of ${health.cameras.total}` : 'Unknown'}</span>
          </Row>
          <Row label="Open incidents"><span className="num">{formatNumber(summary?.open_incidents ?? summary?.unreviewed_alerts ?? 0)}</span></Row>
          <Row label="Active tracks"><span className="num">{formatNumber(summary?.active_tracks ?? 0)}</span></Row>
          <Row label="Event persistence">{health?.persistence_enabled ? 'Enabled' : 'Disabled'}</Row>
        </dl>
      </Section>

      <Section title="Evidence storage">
        <dl>
          <Row label="Snapshot capture">
            <Health ok={!!storage?.capture_enabled} tone="warn">{storage?.capture_enabled ? 'Recording' : 'Paused'}</Health>
          </Row>
          <Row label="Used">
            {storage?.snapshot_storage_mb == null
              ? 'Not measured'
              : <span className="num">{formatNumber(Math.round(storage.snapshot_storage_mb))} MB of {formatNumber(storage.snapshot_storage_limit_mb)} MB</span>}
          </Row>
          {storage && <Row label="Free disk space"><span className="num">{formatNumber(Math.round(storage.free_storage_mb))} MB</span></Row>}
        </dl>
        {overLimit && (
          <p className="mt-3 max-w-[65ch] text-sm text-warn">
            Snapshots use more than the configured limit, so new evidence is not being captured. Free space or raise the limit in the backend configuration.
          </p>
        )}
      </Section>
    </div>
  );
}

function SettingsInner() {
  const [{ tab }, setUrl] = useUrlState({ tab: 'profile' });
  const active = TABS.some(t => t.id === tab) ? tab : 'profile';

  return (
    <div className="max-w-3xl">
      <div role="tablist" aria-label="Settings sections" className="flex gap-6 overflow-x-auto border-b border-line">
        {TABS.map(item => (
          <button
            key={item.id}
            id={`tab-${item.id}`}
            role="tab"
            type="button"
            aria-selected={active === item.id}
            aria-controls={`panel-${item.id}`}
            onClick={() => setUrl({ tab: item.id })}
            className={cn(
              '-mb-px whitespace-nowrap border-b-2 pb-2.5 text-sm transition-colors duration-150',
              active === item.id ? 'border-accent font-medium text-fg' : 'border-transparent text-muted hover:text-fg',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${active}`} aria-labelledby={`tab-${active}`} className="pt-8">
        {active === 'profile' && <ProfileTab />}
        {active === 'appearance' && <AppearanceTab />}
        {active === 'health' && <HealthTab />}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <SettingsInner />
    </Suspense>
  );
}
