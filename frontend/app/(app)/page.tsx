'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowClockwise, FileCsv, FilePdf, Fire } from '@phosphor-icons/react';
import {
  apiJson, formatDuration, formatEventType, formatNumber, formatRelative, formatTime, riskMeta, toDate,
} from '@/src/api/client';
import { useInterval } from '@/src/hooks/useInterval';
import { pushToast } from '@/src/lib/toast';
import { cn } from '@/src/lib/cn';
import { Button } from '@/src/components/ui/Button';
import { Select } from '@/src/components/ui/Field';
import Section from '@/src/components/ui/Section';
import { EmptyState, Loading, Skeleton } from '@/src/components/ui/States';
import { cameraDisplayStatus, isCameraLive, RiskDot, StatusLabel } from '@/src/components/ui/Indicators';
import StreamView from '@/src/components/video/StreamView';
import HeatmapLayer from '@/src/components/video/HeatmapLayer';
import AlertTrend from '@/src/components/charts/AlertTrend';
import TypeBreakdown from '@/src/components/charts/TypeBreakdown';
import type { Alert, AlertStats, Camera, DashboardSummary, Event, Paged, Threat, ThreatsData, TimeseriesData } from '@/src/types';

interface DashboardData {
  summary: DashboardSummary | null;
  cameras: Camera[];
  alerts: Alert[];
  events: Event[];
  timeseries: TimeseriesData;
  byType: Record<string, number>;
  threats: Threat[];
}

type Key = keyof DashboardData;

const EMPTY: DashboardData = {
  summary: null, cameras: [], alerts: [], events: [], timeseries: { labels: [], data: [] }, byType: {}, threats: [],
};

/**
 * Each request fills its own section as soon as it returns, so one slow
 * endpoint never blanks the page. A poll is skipped while the previous one is
 * still running, so a struggling backend is not buried under queued requests.
 */
function useDashboardData() {
  const [data, setData] = useState<DashboardData>(EMPTY);
  const [loaded, setLoaded] = useState<Partial<Record<Key, boolean>>>({});
  const [summaryFailed, setSummaryFailed] = useState(false);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    const put = <K extends Key>(key: K, value: DashboardData[K]) => {
      setData(previous => ({ ...previous, [key]: value }));
      setLoaded(previous => (previous[key] ? previous : { ...previous, [key]: true }));
    };
    const settle = (key: Key) => () => setLoaded(previous => (previous[key] ? previous : { ...previous, [key]: true }));

    await Promise.allSettled([
      apiJson<DashboardSummary>('/api/statistics/summary')
        .then(summary => { put('summary', summary); setSummaryFailed(false); })
        .catch(() => { setSummaryFailed(true); settle('summary')(); }),
      apiJson<Camera[]>('/api/cameras').then(rows => put('cameras', rows)).catch(settle('cameras')),
      apiJson<Paged<Alert>>('/api/alerts/query?status=open&active_only=true&page_size=10&sort_by=priority&sort_order=desc')
        .then(page => put('alerts', page.items)).catch(settle('alerts')),
      apiJson<Event[]>('/api/events?limit=8').then(rows => put('events', rows)).catch(settle('events')),
      apiJson<TimeseriesData>('/api/statistics/timeseries').then(series => put('timeseries', series)).catch(settle('timeseries')),
      apiJson<{ alert_stats?: AlertStats; database?: { event_distribution?: Record<string, number> } }>('/api/statistics')
        .then(stats => put('byType', stats.database?.event_distribution ?? stats.alert_stats?.by_type ?? {}))
        .catch(settle('byType')),
      apiJson<ThreatsData>('/api/statistics/threats').then(result => put('threats', result.top_threats ?? [])).catch(settle('threats')),
    ]);
    inFlight.current = false;
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useInterval(refresh, 5000);

  return { data, loaded, summaryFailed, refresh };
}

function Stat({ label, value, emphasis }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className={cn('num mt-0.5 text-2xl font-semibold tracking-tight', emphasis ? 'text-critical' : 'text-fg')}>{value}</dd>
    </div>
  );
}

function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-hidden>
      {Array.from({ length: rows }).map((_, index) => <Skeleton key={index} className="h-9" />)}
    </div>
  );
}

function ReportButtons() {
  const [busy, setBusy] = useState<'csv' | 'pdf' | null>(null);
  const run = async (kind: 'csv' | 'pdf') => {
    setBusy(kind);
    try {
      const { fetchDailyReport, generateCSV, generatePDF } = await import('@/src/api/reports');
      if (kind === 'csv') generateCSV(await fetchDailyReport());
      else await generatePDF();
    } catch {
      pushToast({ title: 'Export failed', message: 'The daily report could not be generated. Try again shortly.', level: 'error' });
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="flex gap-2">
      <Button size="sm" icon={<FileCsv size={15} />} loading={busy === 'csv'} disabled={!!busy} onClick={() => run('csv')}>Export CSV</Button>
      <Button size="sm" icon={<FilePdf size={15} />} loading={busy === 'pdf'} disabled={!!busy} onClick={() => run('pdf')}>Export PDF</Button>
    </div>
  );
}

function LiveFeed({ cameras, ready }: { cameras: Camera[]; ready: boolean }) {
  const [selected, setSelected] = useState('');
  const [heatmap, setHeatmap] = useState(false);
  const fallback = cameras.find(isCameraLive) ?? cameras.find(c => c.enabled !== false);
  const cameraId = selected || fallback?.camera_id || '';
  const camera = cameras.find(c => c.camera_id === cameraId);
  const disabled = camera?.enabled === false;
  const live = !!cameraId && !disabled;

  return (
    <Section
      title="Live feed"
      action={
        <>
          <Button size="sm" variant={heatmap ? 'secondary' : 'ghost'} aria-pressed={heatmap} disabled={!live}
            icon={<Fire size={14} />} onClick={() => setHeatmap(v => !v)}>
            Heatmap
          </Button>
          <Select aria-label="Camera shown in live feed" value={cameraId} onChange={e => setSelected(e.target.value)} wrapperClassName="w-44">
            {cameras.length === 0 && <option value="">{ready ? 'No cameras' : 'Loading…'}</option>}
            {cameras.map(c => (
              <option key={c.camera_id} value={c.camera_id} disabled={c.enabled === false}>
                {c.name}{c.enabled === false ? ' (disabled)' : ''}
              </option>
            ))}
          </Select>
        </>
      }
    >
      <StreamView
        path={live ? `/api/stream/${cameraId}` : null}
        alt={camera ? `Live feed from ${camera.name}` : 'Live feed'}
        idleLabel={!ready ? 'Loading cameras…' : disabled ? 'This camera is disabled' : 'Select a camera'}
        className="aspect-video rounded-lg"
      >
        {heatmap && live && <HeatmapLayer cameraId={cameraId} />}
      </StreamView>
      {camera && (
        <p className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          <StatusLabel status={cameraDisplayStatus(camera)} />
          <span className="truncate">{camera.location || camera.camera_id}</span>
          {!!camera.fps && <span className="num">{camera.fps.toFixed(0)} fps</span>}
          {camera.active_tracks != null && <span className="num">{camera.active_tracks} active tracks</span>}
        </p>
      )}
    </Section>
  );
}

function NeedsAttention({ alerts, ready }: { alerts: Alert[]; ready: boolean }) {
  const now = Date.now();
  return (
    <Section title="Needs attention" action={<Link href="/alerts" className="text-sm font-medium text-accent hover:text-accent-hover">All alerts</Link>}>
      {!ready ? <ListSkeleton rows={6} /> : alerts.length === 0 ? (
        <EmptyState compact title="No open alerts" description="High and critical alerts also appear as notifications as they happen." />
      ) : (
        <ul className="-mx-3">
          {alerts.slice(0, 8).map(alert => (
            <li key={alert.alert_id}>
              <Link
                href={`/event?id=${encodeURIComponent(alert.event_id)}`}
                className="flex items-center gap-3 rounded-md px-3 py-2 transition-colors duration-150 hover:bg-subtle"
                style={alert.risk_level === 'critical' ? { boxShadow: `inset 2px 0 0 ${riskMeta('critical').color}` } : undefined}
              >
                <RiskDot level={alert.risk_level} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-fg">{formatEventType(alert.event_type)}</span>
                  <span className="block truncate text-xs text-muted">
                    {riskMeta(alert.risk_level).label}, camera {alert.camera_id}
                  </span>
                </span>
                <time className="num shrink-0 text-xs text-muted" dateTime={toDate(alert.timestamp)?.toISOString()} title={formatTime(alert.timestamp)}>
                  {formatRelative(alert.timestamp, now)}
                </time>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function ActiveThreats({ threats, ready }: { threats: Threat[]; ready: boolean }) {
  return (
    <Section title="Active threats">
      {!ready ? <ListSkeleton rows={4} /> : threats.length === 0 ? (
        <EmptyState compact title="No active threats" description="Tracked objects appear here when the risk engine scores them." />
      ) : (
        <ul>
          {threats.slice(0, 6).map(threat => {
            const meta = riskMeta(threat.risk_level);
            return (
              <li key={`${threat.camera_id}-${threat.track_id}`} className="border-b border-line/70 py-3 first:pt-0 last:border-0">
                <div className="flex items-center gap-3 text-sm">
                  <RiskDot level={threat.risk_level} />
                  <span className="font-medium capitalize text-fg">{threat.object_type}</span>
                  <span className="truncate text-muted">camera {threat.camera_id}, {formatDuration(threat.duration)}</span>
                  <span className="num ml-auto shrink-0 text-fg">{Math.round(threat.risk_score)}</span>
                </div>
                <div className="ml-5 mt-2 h-1 overflow-hidden rounded-full bg-subtle">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(100, threat.risk_score)}%`, background: meta.color }} />
                </div>
                {threat.risk_factors.length > 0 && (
                  <p className="ml-5 mt-1.5 line-clamp-2 text-xs text-muted">{threat.risk_factors.join(', ')}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}

function RecentEvents({ events, ready }: { events: Event[]; ready: boolean }) {
  const now = Date.now();
  return (
    <Section title="Recent events" action={<Link href="/events" className="text-sm font-medium text-accent hover:text-accent-hover">All events</Link>}>
      {!ready ? <ListSkeleton rows={6} /> : events.length === 0 ? (
        <EmptyState compact title="No events yet" />
      ) : (
        <ul className="-mx-3">
          {events.map(event => (
            <li key={event.event_id}>
              <Link href={`/event?id=${encodeURIComponent(event.event_id)}`}
                className="flex items-center gap-3 rounded-md px-3 py-2 transition-colors duration-150 hover:bg-subtle">
                <RiskDot level={event.risk_level} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-fg">{formatEventType(event.event_type)}</span>
                  <span className="block truncate text-xs capitalize text-muted">{event.object_type}, camera {event.camera_id}</span>
                </span>
                <time className="num shrink-0 text-xs text-muted" title={formatTime(event.timestamp)}>{formatRelative(event.timestamp, now)}</time>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function CameraList({ cameras, ready }: { cameras: Camera[]; ready: boolean }) {
  return (
    <Section title="Cameras" action={<Link href="/cameras" className="text-sm font-medium text-accent hover:text-accent-hover">Manage cameras</Link>}>
      {!ready ? <ListSkeleton rows={3} /> : cameras.length === 0 ? (
        <EmptyState compact title="No cameras configured" />
      ) : (
        <ul className="grid gap-x-10 sm:grid-cols-2 xl:grid-cols-3">
          {cameras.map(camera => (
            <li key={camera.camera_id} className="flex items-center justify-between gap-3 border-b border-line/70 py-2 text-sm">
              <span className="min-w-0 truncate text-fg">{camera.name}</span>
              <span className="flex shrink-0 items-center gap-4 text-muted">
                {!!camera.fps && isCameraLive(camera) && <span className="num">{camera.fps.toFixed(0)} fps</span>}
                <StatusLabel status={cameraDisplayStatus(camera)} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export default function DashboardPage() {
  const { data, loaded, summaryFailed, refresh } = useDashboardData();

  if (!loaded.summary) return <Loading label="Loading dashboard…" />;

  if (!data.summary) {
    return (
      <EmptyState
        title={summaryFailed ? 'Cannot reach the IBVAP API' : 'No data yet'}
        description={summaryFailed ? 'The dashboard retries every 5 seconds. Check that the backend service is running.' : undefined}
        action={<Button icon={<ArrowClockwise size={14} />} onClick={() => void refresh()}>Retry now</Button>}
      />
    );
  }

  const s = data.summary;
  const criticalHigh = s.critical_high_incidents ?? s.critical_alerts ?? 0;

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <dl className="grid grid-cols-2 gap-x-12 gap-y-4 sm:flex sm:flex-wrap">
          <Stat label="Cameras online" value={`${s.online_cameras} of ${s.total_cameras}`} />
          <Stat label="Open incidents" value={formatNumber(s.open_incidents ?? s.unreviewed_alerts ?? 0)} />
          <Stat label="Active tracks" value={formatNumber(s.active_tracks || 0)} />
          <Stat label="Critical or high" value={formatNumber(criticalHigh)} emphasis={criticalHigh > 0} />
        </dl>
        <ReportButtons />
      </div>

      <div className="grid gap-10 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
        <LiveFeed cameras={data.cameras} ready={!!loaded.cameras} />
        <NeedsAttention alerts={data.alerts} ready={!!loaded.alerts} />
      </div>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
        <Section title="Alerts in the last 24 hours">
          {loaded.timeseries ? <AlertTrend data={data.timeseries} /> : <Skeleton className="h-[180px]" />}
        </Section>
        <Section title="Events by type">
          {loaded.byType ? <TypeBreakdown counts={data.byType} /> : <ListSkeleton rows={4} />}
        </Section>
      </div>

      <div className="grid gap-10 lg:grid-cols-2">
        <ActiveThreats threats={data.threats} ready={!!loaded.threats} />
        <RecentEvents events={data.events} ready={!!loaded.events} />
      </div>

      <CameraList cameras={data.cameras} ready={!!loaded.cameras} />
    </div>
  );
}
