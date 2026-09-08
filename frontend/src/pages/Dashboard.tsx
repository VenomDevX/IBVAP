import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch, formatEventType, formatTime, getRiskEmoji, mediaSrc } from '../api/client';
import { useInterval } from '../hooks/useInterval';
import { useAuth } from '../context/AuthContext';
import StatCard from '../components/ui/StatCard';
import Card from '../components/ui/Card';
import AlertTrendChart from '../components/charts/AlertTrendChart';
import AlertTypeChart from '../components/charts/AlertTypeChart';
import ThreatScorePanel from '../components/dashboard/ThreatScorePanel';
import HeatmapOverlay from '../components/camera/HeatmapOverlay';
import type {
  DashboardSummary, Camera, Alert, Event, TimeseriesData, AlertStats,
} from '../types';

// ────────────────────────────── data ──────────────────────────────

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

  const refresh = useCallback(async () => {
    try {
      const [sum, cam, alert, event, ts, stat] = await Promise.all([
        apiFetch('/api/statistics/summary'),
        apiFetch('/api/cameras'),
        apiFetch('/api/alerts/live'),
        apiFetch('/api/events?limit=10'),
        apiFetch('/api/statistics/timeseries'),
        apiFetch('/api/statistics'),
      ]);
      const statData: { alert_stats?: AlertStats } = await stat.json();
      setData({
        summary: await sum.json(),
        cameras: await cam.json(),
        alerts: await alert.json(),
        events: await event.json(),
        timeseries: await ts.json(),
        byType: statData.alert_stats?.by_type ?? {},
      });
      setLoading(false);
    } catch (err) {
      console.error('Dashboard data error:', err);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useInterval(refresh, 5000);

  return { data, loading, refresh };
}

// ────────────────────────────── small pieces ──────────────────────────────

function EmptyState({ icon, message }: { icon: string; message: string }) {
  return <div className="empty-state"><i className={icon} /><p>{message}</p></div>;
}

function ReportButtons() {
  const [busy, setBusy] = useState(false);
  const run = async (kind: 'csv' | 'pdf') => {
    setBusy(true);
    try {
      const { fetchDailyReport, generateCSV, generatePDF } = await import('../api/reports');
      const report = await fetchDailyReport();
      (kind === 'csv' ? generateCSV : generatePDF)(report);
    } catch (e) {
      console.error(e);
      alert('Export failed.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="dashboard-actions">
      <button className="btn btn-outline btn-sm" onClick={() => run('csv')} disabled={busy}>
        <i className="fas fa-file-csv" />CSV Report
      </button>
      <button className="btn btn-primary btn-sm" onClick={() => run('pdf')} disabled={busy}>
        <i className="fas fa-file-pdf" />PDF Report
      </button>
    </div>
  );
}

function SummaryStats({ s }: { s: DashboardSummary }) {
  return (
    <div className="stats-grid">
      <StatCard icon="fas fa-video" iconClass="cameras" value={`${s.online_cameras}/${s.total_cameras}`} label="Cameras Online" />
      <StatCard icon="fas fa-bell" iconClass="alerts" value={s.unreviewed_alerts || 0} label="Active Alerts" />
      <StatCard icon="fas fa-route" iconClass="tracks" value={s.active_tracks || 0} label="Active Tracks" />
      <StatCard icon="fas fa-exclamation-triangle" iconClass="critical-icon" value={s.critical_alerts || 0} label="Critical Alerts" className="critical" />
    </div>
  );
}

function ChartsRow({ timeseries, byType }: { timeseries: TimeseriesData; byType: Record<string, number> }) {
  return (
    <div className="charts-grid">
      <Card title="Alert Trend (Last 24h)" icon="fas fa-chart-line" className="chart-card">
        <AlertTrendChart data={timeseries} />
      </Card>
      <Card title="Alert Breakdown" icon="fas fa-chart-pie" className="chart-card">
        <AlertTypeChart byType={byType} />
      </Card>
    </div>
  );
}

function LiveFeedCard({ cameras }: { cameras: Camera[] }) {
  const { session } = useAuth();
  const token = session?.access_token;
  const [selected, setSelected] = useState('');
  const [showHeatmap, setShowHeatmap] = useState(false);

  useEffect(() => {
    if (!selected && cameras.length > 0) setSelected(cameras[0].camera_id);
  }, [cameras, selected]);

  const controls: ReactNode = (
    <div className="feed-controls">
      <button
        className={`btn btn-sm ${showHeatmap ? 'btn-primary' : 'btn-outline'}`}
        onClick={() => setShowHeatmap(v => !v)}
        title="Toggle Heatmap"
      >
        <i className="fas fa-fire" />
      </button>
      <select className="select-small" value={selected} onChange={e => setSelected(e.target.value)}>
        <option value="">Select Camera</option>
        {cameras.map(c => (
          <option key={c.camera_id} value={c.camera_id}>{c.name} ({c.camera_id})</option>
        ))}
      </select>
    </div>
  );

  return (
    <Card title="Live Feed" icon="fas fa-video" className="camera-card" headerRight={controls}>
      <div className="video-container">
        {selected ? (
          <>
            <img
              src={mediaSrc(`/api/stream/${selected}`, token)}
              alt="Camera Feed"
              className="video-feed"
              onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
            <HeatmapOverlay cameraId={selected} isVisible={showHeatmap} windowMinutes={5} />
          </>
        ) : (
          <div className="video-placeholder">
            <i className="fas fa-video-slash" />
            <p>Select a camera to view feed</p>
          </div>
        )}
      </div>
    </Card>
  );
}

function RecentAlertsCard({ alerts }: { alerts: Alert[] }) {
  return (
    <Card
      title="Recent Alerts" icon="fas fa-bell" className="alerts-card"
      headerRight={<Link to="/alerts" className="btn btn-sm">View All</Link>}
    >
      <div className="alert-list">
        {alerts.length === 0 ? (
          <EmptyState icon="fas fa-check-circle" message="No active alerts" />
        ) : (
          alerts.slice(0, 10).map(a => (
            <Link
              to={`/events/${a.event_id}`} key={a.alert_id} className="alert-item"
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <div className={`alert-level ${a.risk_level}`} />
              <div className="alert-content">
                <div className="alert-title">{formatEventType(a.event_type)}</div>
                <div className="alert-meta">
                  {a.camera_id} • Score {a.risk_score?.toFixed(0) || 0} • {formatTime(a.timestamp)}
                </div>
              </div>
            </Link>
          ))
        )}
      </div>
    </Card>
  );
}

function EventTimelineCard({ events }: { events: Event[] }) {
  return (
    <Card
      title="Event Timeline" icon="fas fa-list-timeline" className="timeline-card"
      headerRight={<Link to="/events" className="btn btn-sm">View All</Link>}
    >
      <div className="timeline">
        {events.length === 0 ? (
          <EmptyState icon="fas fa-clock" message="No recent events" />
        ) : (
          events.map(e => (
            <div className="timeline-item" key={e.event_id}>
              <span className={`risk-badge ${e.risk_level}`}>{getRiskEmoji(e.risk_level)}</span>
              <div className="timeline-item-body">
                <strong>{formatEventType(e.event_type)}</strong>
                <div className="alert-meta">{e.camera_id} • {e.object_type}</div>
              </div>
              <span className="timeline-time">{formatTime(e.timestamp)}</span>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}

function CameraStatusCard({ cameras }: { cameras: Camera[] }) {
  return (
    <Card title="Camera Status" icon="fas fa-signal" className="status-card">
      <div className="camera-status-list">
        {cameras.length === 0 ? (
          <EmptyState icon="fas fa-video-slash" message="No cameras configured" />
        ) : (
          cameras.map(c => (
            <div className="camera-status-item" key={c.camera_id}>
              <div>
                <strong>{c.name}</strong>
                <span className="camera-id" style={{ marginLeft: 8 }}>{c.camera_id}</span>
              </div>
              <div className="camera-status-meta">
                {c.fps ? <span className="fps-badge">{c.fps} FPS</span> : null}
                <span className={`status-dot ${c.status === 'online' ? 'online' : 'offline'}`} />
                <span>{c.status || 'unknown'}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}

// ────────────────────────────── page ──────────────────────────────

export default function Dashboard() {
  const { data, loading } = useDashboardData();

  if (loading || !data.summary) {
    return <div className="loading"><i className="fas fa-spinner fa-spin" /> Loading Dashboard...</div>;
  }

  return (
    <div className="dashboard">
      <ReportButtons />
      <SummaryStats s={data.summary} />
      <ChartsRow timeseries={data.timeseries} byType={data.byType} />
      <ThreatScorePanel />
      <div className="dashboard-grid">
        <LiveFeedCard cameras={data.cameras} />
        <RecentAlertsCard alerts={data.alerts} />
        <EventTimelineCard events={data.events} />
        <CameraStatusCard cameras={data.cameras} />
      </div>
    </div>
  );
}
