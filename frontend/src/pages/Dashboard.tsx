import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch, formatEventType, formatTime, getRiskEmoji } from '../api/client';
import { useInterval } from '../hooks/useInterval';
import StatCard from '../components/ui/StatCard';
import Card from '../components/ui/Card';
import AlertTrendChart from '../components/charts/AlertTrendChart';
import AlertTypeChart from '../components/charts/AlertTypeChart';
import ThreatScorePanel from '../components/dashboard/ThreatScorePanel';
import HeatmapOverlay from '../components/camera/HeatmapOverlay';
import type { DashboardSummary, Camera, Alert, Event, TimeseriesData, AlertStats } from '../types';

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [timeseries, setTimeseries] = useState<TimeseriesData>({ labels: [], data: [] });
  const [byType, setByType] = useState<Record<string, number>>({});
  const [selectedCamera, setSelectedCamera] = useState('');
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const handleExportCSV = async () => {
    setExporting(true);
    try {
      const { fetchDailyReport, generateCSV } = await import('../api/reports');
      const data = await fetchDailyReport();
      generateCSV(data);
    } catch (e) {
      console.error(e);
      alert('Export failed.');
    } finally {
      setExporting(false);
    }
  };

  const handleExportPDF = async () => {
    setExporting(true);
    try {
      const { fetchDailyReport, generatePDF } = await import('../api/reports');
      const data = await fetchDailyReport();
      generatePDF(data);
    } catch (e) {
      console.error(e);
      alert('Export failed.');
    } finally {
      setExporting(false);
    }
  };

  const fetchData = useCallback(async () => {
    try {
      const [sumRes, camRes, alertRes, eventRes, tsRes, statRes] = await Promise.all([
        apiFetch('/api/statistics/summary'),
        apiFetch('/api/cameras'),
        apiFetch('/api/alerts/live'),
        apiFetch('/api/events?limit=10'),
        apiFetch('/api/statistics/timeseries'),
        apiFetch('/api/statistics'),
      ]);

      const sumData: DashboardSummary = await sumRes.json();
      const camData: Camera[] = await camRes.json();
      const alertData: Alert[] = await alertRes.json();
      const eventData: Event[] = await eventRes.json();
      const tsData: TimeseriesData = await tsRes.json();
      const statData: { alert_stats: AlertStats } = await statRes.json();

      setSummary(sumData);
      setCameras(camData);
      setAlerts(alertData);
      setEvents(eventData);
      setTimeseries(tsData);
      setByType(statData.alert_stats?.by_type || {});
      setLoading(false);

      if (!selectedCamera && camData.length > 0) {
        setSelectedCamera(camData[0].camera_id);
      }
    } catch (err) {
      console.error('Dashboard data error:', err);
    }
  }, [selectedCamera]);

  useEffect(() => { fetchData(); }, [fetchData]);
  useInterval(fetchData, 5000);

  if (loading || !summary) {
    return <div className="loading"><i className="fas fa-spinner fa-spin" /> Loading Dashboard...</div>;
  }

  return (
    <div className="dashboard">
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginBottom: '15px' }}>
        <button className="btn btn-outline btn-sm" onClick={handleExportCSV} disabled={exporting}>
          <i className="fas fa-file-csv" style={{ marginRight: '5px' }}></i>
          CSV Report
        </button>
        <button className="btn btn-primary btn-sm" onClick={handleExportPDF} disabled={exporting}>
          <i className="fas fa-file-pdf" style={{ marginRight: '5px' }}></i>
          PDF Report
        </button>
      </div>

      {/* Summary Stats */}
      <div className="stats-grid">
        <StatCard icon="fas fa-video" iconClass="cameras" value={summary ? `${summary.online_cameras}/${summary.total_cameras}` : '0/0'} label="Cameras Online" loading={loading} />
        <StatCard icon="fas fa-bell" iconClass="alerts" value={summary?.unreviewed_alerts || 0} label="Active Alerts" loading={loading} />
        <StatCard icon="fas fa-route" iconClass="tracks" value={summary?.active_tracks || 0} label="Active Tracks" loading={loading} />
        <StatCard icon="fas fa-exclamation-triangle" iconClass="critical-icon" value={summary?.critical_alerts || 0} label="Critical Alerts" loading={loading} className="critical" />
      </div>

      {/* Charts Grid */}
      <div className="charts-grid" style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '16px', marginBottom: '24px' }}>
        <Card title="Alert Trend (Last 24h)" icon="fas fa-chart-line" className="chart-card">
          <AlertTrendChart data={timeseries} />
        </Card>
        <Card title="Alert Breakdown" icon="fas fa-chart-pie" className="chart-card">
          <AlertTypeChart byType={byType} />
        </Card>
      </div>

      {/* Threat Dashboard */}
      <ThreatScorePanel />

      {/* Main Grid */}
      <div className="dashboard-grid">
        {/* Camera Feed */}
        <Card title="Live Feed" icon="fas fa-video" className="camera-card"
          headerRight={
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <button 
                className={`btn btn-sm ${showHeatmap ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setShowHeatmap(!showHeatmap)}
                title="Toggle Heatmap"
              >
                <i className="fas fa-fire"></i>
              </button>
              <select className="select-small" value={selectedCamera} onChange={e => setSelectedCamera(e.target.value)}>
                <option value="">Select Camera</option>
                {cameras.map(c => (
                  <option key={c.camera_id} value={c.camera_id}>{c.name} ({c.camera_id})</option>
                ))}
              </select>
            </div>
          }
        >
          <div className="video-container" style={{ position: 'relative' }}>
            {selectedCamera ? (
              <>
                <img
                  src={`/api/stream/${selectedCamera}`}
                  alt="Camera Feed"
                  className="video-feed"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
                <HeatmapOverlay cameraId={selectedCamera} isVisible={showHeatmap} windowMinutes={5} />
              </>
            ) : (
              <div className="video-placeholder">
                <i className="fas fa-video-slash" />
                <p>Select a camera to view feed</p>
              </div>
            )}
          </div>
        </Card>

        {/* Recent Alerts */}
        <Card title="Recent Alerts" icon="fas fa-bell" className="alerts-card"
          headerRight={<Link to="/alerts" className="btn btn-sm">View All</Link>}
        >
          <div className="alert-list">
            {alerts.length === 0 ? (
              <div className="empty-state"><i className="fas fa-check-circle" /><p>No active alerts</p></div>
            ) : (
              alerts.slice(0, 10).map(a => (
                <Link to={`/events/${a.event_id}`} key={a.alert_id} className="alert-item" style={{ textDecoration: 'none', color: 'inherit' }}>
                  <div className={`alert-level ${a.risk_level}`} />
                  <div className="alert-content">
                    <div className="alert-title">{formatEventType(a.event_type)}</div>
                    <div className="alert-meta">{a.camera_id} • Score {a.risk_score?.toFixed(0) || 0} • {formatTime(a.timestamp)}</div>
                  </div>
                </Link>
              ))
            )}
          </div>
        </Card>

        {/* Event Timeline */}
        <Card title="Event Timeline" icon="fas fa-list-timeline" className="timeline-card"
          headerRight={<Link to="/events" className="btn btn-sm">View All</Link>}
        >
          <div className="timeline">
            {events.length === 0 ? (
              <div className="empty-state"><i className="fas fa-clock" /><p>No recent events</p></div>
            ) : (
              events.map(e => (
                <div className="timeline-item" key={e.event_id}>
                  <span className={`risk-badge ${e.risk_level}`}>{getRiskEmoji(e.risk_level)}</span>
                  <div style={{ flex: 1 }}>
                    <strong>{formatEventType(e.event_type)}</strong>
                    <div className="alert-meta">{e.camera_id} • {e.object_type}</div>
                  </div>
                  <span className="timeline-time">{formatTime(e.timestamp)}</span>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Camera Status */}
        <Card title="Camera Status" icon="fas fa-signal" className="status-card">
          <div className="camera-status-list">
            {cameras.length === 0 ? (
              <div className="empty-state"><i className="fas fa-video-slash" /><p>No cameras configured</p></div>
            ) : (
              cameras.map(c => (
                <div className="camera-status-item" key={c.camera_id}>
                  <div>
                    <strong>{c.name}</strong>
                    <span className="camera-id" style={{ marginLeft: 8 }}>{c.camera_id}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {c.fps && <span className="fps-badge">{c.fps} FPS</span>}
                    <span className={`status-dot ${c.status === 'online' ? 'online' : 'offline'}`} />
                    <span>{c.status || 'unknown'}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
