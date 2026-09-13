'use client';

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { apiFetch, formatEventType, formatTime, mediaSrc } from '@/src/api/client';
import { useInterval } from '@/src/hooks/useInterval';
import { useAuth } from '@/src/context/AuthContext';
import { pushToast } from '@/src/lib/toast';
import StatCard from '@/src/components/ui/StatCard';
import Card from '@/src/components/ui/Card';
import Icon from '@/src/components/ui/Icon';
import { Button, ButtonLink } from '@/src/components/ui/Button';
import { Select } from '@/src/components/ui/Field';
import { EmptyState, Loading } from '@/src/components/ui/States';
import HeatmapOverlay from '@/src/components/camera/HeatmapOverlay';
import { RiskDot } from '@/src/components/ui/RiskBadge';
import StatusDot from '@/src/components/ui/StatusDot';
import AlertTrendChart from '@/src/components/charts/AlertTrendChart';
import AlertTypeChart from '@/src/components/charts/AlertTypeChart';
import ThreatScorePanel from '@/src/components/dashboard/ThreatScorePanel';
import type {
  DashboardSummary, Camera, Alert, Event, TimeseriesData, AlertStats,
} from '@/src/types';

interface DashboardData {
  summary: DashboardSummary | null;
  cameras: Camera[];
  alerts: Alert[];
  events: Event[];
  timeseries: TimeseriesData;
  byType: Record<string, number>;
}

const EMPTY: DashboardData = {
  summary: null, cameras: [], alerts: [], events: [],
  timeseries: { labels: [], data: [] }, byType: {},
};

function useDashboardData() {
  const [data, setData] = useState<DashboardData>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    const responses = await Promise.allSettled([
        apiFetch('/api/statistics/summary'),
        apiFetch('/api/cameras'),
        apiFetch('/api/alerts/query?status=open&page_size=10'),
        apiFetch('/api/events?limit=10'),
        apiFetch('/api/statistics/timeseries'),
        apiFetch('/api/statistics'),
      ]);
    const json = async <T,>(index: number): Promise<T | null> => {
      const result = responses[index];
      if (result.status !== 'fulfilled' || !result.value.ok) return null;
      return result.value.json() as Promise<T>;
    };
    try {
      const [summary, cameras, alertsPage, events, timeseries, statistics] = await Promise.all([
        json<DashboardSummary>(0), json<Camera[]>(1), json<{ items: Alert[] }>(2),
        json<Event[]>(3), json<TimeseriesData>(4),
        json<{ alert_stats?: AlertStats; database?: { event_distribution?: Record<string, number> } }>(5),
      ]);
      setData(previous => ({
        summary: summary ?? previous.summary,
        cameras: cameras ?? previous.cameras,
        alerts: alertsPage?.items ?? previous.alerts,
        events: events ?? previous.events,
        timeseries: timeseries ?? previous.timeseries,
        byType: statistics?.database?.event_distribution ?? statistics?.alert_stats?.by_type ?? previous.byType,
      }));
      setError(!summary);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useInterval(refresh, 5000);

  return { data, loading, error, refresh };
}

function ReportButtons() {
  const [busy, setBusy] = useState(false);
  const run = async (kind: 'csv' | 'pdf') => {
    setBusy(true);
    try {
      const { fetchDailyReport, generateCSV, generatePDF } = await import('@/src/api/reports');
      const report = await fetchDailyReport();
      if (kind === 'csv') generateCSV(report);
      else await generatePDF();
    } catch (e) {
      console.error(e);
      pushToast({ title: 'Export failed', message: 'Could not build the daily report.', level: 'high' });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mb-4 flex justify-end gap-2">
      <Button icon="file-csv" variant="outline" disabled={busy} onClick={() => run('csv')}>CSV Report</Button>
      <Button icon="file-pdf" variant="primary" disabled={busy} onClick={() => run('pdf')}>PDF Report</Button>
    </div>
  );
}

function LiveFeed({ cameras }: { cameras: Camera[] }) {
  const { mediaTicket } = useAuth();
  const [selected, setSelected] = useState('');
  const [heatmap, setHeatmap] = useState(false);

  useEffect(() => {
    if (!selected && cameras.length > 0) setSelected(cameras[0].camera_id);
  }, [cameras, selected]);

  const controls = (
    <div className="flex items-center gap-2">
      <Button
        size="xs"
        variant={heatmap ? 'primary' : 'outline'}
        icon="fire"
        onClick={() => setHeatmap(v => !v)}
      >
        Heatmap
      </Button>
      <Select value={selected} onChange={e => setSelected(e.target.value)} className="w-44">
        <option value="">Select camera</option>
        {cameras.map(c => <option key={c.camera_id} value={c.camera_id}>{c.name}</option>)}
      </Select>
    </div>
  );
  return (
    <Card title="Live Feed" icon="video" iconColor="accent" actions={controls} bodyClassName="p-6 pt-2">
      <div className="relative aspect-video w-full overflow-hidden rounded bg-black border border-default shadow-sm">
        {selected ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={mediaSrc(`/api/stream/${selected}`, mediaTicket)}
              alt="Live camera feed"
              className="size-full object-contain"
              onError={e => { (e.target as HTMLImageElement).style.opacity = '0.15'; }}
            />
            <HeatmapOverlay cameraId={selected} isVisible={heatmap} windowMinutes={5} />
          </>
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-2 text-fg-subtle">
            <Icon name="video-slash" className="text-2xl opacity-60" />
            <p className="text-[0.85rem]">Select a camera to view its feed</p>
          </div>
        )}
      </div>
    </Card>
  );
}

function RecentAlerts({ alerts }: { alerts: Alert[] }) {
  return (
    <Card
      title="Recent Alerts"
      icon="bell"
      iconColor="danger"
      actions={<ButtonLink href="/alerts" size="xs" variant="ghost">View all</ButtonLink>}
      bodyClassName="p-0"
    >
      {alerts.length === 0 ? (
        <EmptyState icon="circle-check" message="No active alerts" />
      ) : (
        <ul className="max-h-96 divide-y divide-default overflow-y-auto">
          {alerts.slice(0, 10).map(a => (
            <li key={a.alert_id}>
              <Link href={`/event?id=${a.event_id}`} className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-elevated">
                <RiskDot level={a.risk_level} />
                <span className="min-w-0 flex-1">
                  <span className="block text-[0.82rem] font-semibold text-fg">{formatEventType(a.event_type)}</span>
                  <span className="mt-0.5 block truncate text-[0.72rem] text-fg-subtle">
                    {a.camera_id} · score {a.risk_score?.toFixed(0) || 0} · {formatTime(a.timestamp)}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function EventTimeline({ events }: { events: Event[] }) {
  return (
    <Card
      title="Event Timeline"
      icon="timeline"
      iconColor="purple"
      actions={<ButtonLink href="/events" size="xs" variant="ghost">View all</ButtonLink>}
      bodyClassName="p-0"
    >
      {events.length === 0 ? (
        <EmptyState icon="clock" message="No recent events" />
      ) : (
        <ul className="max-h-96 divide-y divide-default overflow-y-auto">
          {events.map(e => (
            <li key={e.event_id} className="flex items-center gap-3 px-4 py-3 text-[0.82rem]">
              <RiskDot level={e.risk_level} />
              <span className="min-w-0 flex-1">
                <span className="font-semibold text-fg">{formatEventType(e.event_type)}</span>
                <span className="mt-0.5 block truncate text-[0.72rem] text-fg-subtle">{e.camera_id} · {e.object_type}</span>
              </span>
              <span className="shrink-0 text-[0.72rem] tabular-nums text-fg-subtle">{formatTime(e.timestamp)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function CameraStatus({ cameras }: { cameras: Camera[] }) {
  return (
    <Card title="Camera Status" icon="signal" iconColor="info" bodyClassName="p-0">
      {cameras.length === 0 ? (
        <EmptyState icon="video-slash" message="No cameras configured" />
      ) : (
        <ul className="max-h-96 divide-y divide-default overflow-y-auto">
          {cameras.map(c => (
            <li key={c.camera_id} className="flex items-center justify-between gap-3 px-4 py-3 text-[0.82rem]">
              <span className="min-w-0">
                <span className="font-semibold text-fg">{c.name}</span>
                <span className="ml-2 font-mono text-[0.72rem] text-fg-subtle">{c.camera_id}</span>
              </span>
              <span className="flex shrink-0 items-center gap-2 text-fg-muted">
                {c.fps ? <span className="rounded-sm border border-default px-1.5 py-0.5 text-[0.68rem] tabular-nums">{c.fps} fps</span> : null}
                <StatusDot status={c.status} />
                <span className="capitalize">{c.status || 'unknown'}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function DashboardPage() {
  const { data, loading, error, refresh } = useDashboardData();

  if (loading) return <Loading label="Loading dashboard…" />;

  if (!data.summary) {
    return (
      <EmptyState icon="triangle-exclamation" message={error ? "Can't reach the backend. Retrying every 5s…" : 'No data yet'}>
        <Button size="sm" icon="rotate-right" onClick={refresh}>Retry now</Button>
      </EmptyState>
    );
  }

  const s = data.summary;

  return (
    <div>
      <ReportButtons />

      {/* Stat Cards */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard icon="video" value={`${s.online_cameras}/${s.total_cameras}`} label="Cameras online" />
        <StatCard icon="bell" value={s.unreviewed_alerts || 0} label="Active alerts" />
        <StatCard icon="route" value={s.active_tracks || 0} label="Active tracks" />
        <StatCard icon="triangle-exclamation" value={s.critical_alerts || 0} label="Critical alerts" emphasis />
      </div>

      {/* Live Feed + Pie Chart — above Threat Assessment */}
      <div className="mb-6 grid gap-4 lg:grid-cols-2 items-stretch">
        <LiveFeed cameras={data.cameras} />
        <Card title="Alert Breakdown" icon="chart-pie" iconColor="warning" bodyClassName="flex-1 flex flex-col justify-center">
          <div className="flex items-center justify-center w-full min-h-[280px]">
            <AlertTypeChart byType={data.byType} />
          </div>
        </Card>
      </div>

      {/* Threat Score */}
      <ThreatScorePanel />

      {/* Alert Trend — full width */}
      <div className="mb-6">
        <Card title="Alert Trend — last 24h" icon="chart-line">
          <AlertTrendChart data={data.timeseries} />
        </Card>
      </div>

      {/* Bottom grid */}
      <div className="grid gap-4 xl:grid-cols-2">
        <RecentAlerts alerts={data.alerts} />
        <EventTimeline events={data.events} />
        <CameraStatus cameras={data.cameras} />
      </div>
    </div>
  );
}
