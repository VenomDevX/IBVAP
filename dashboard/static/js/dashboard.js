/**
 * IBVAP — Dashboard JavaScript
 * Real-time dashboard updates, camera selection, and data polling.
 */

let currentCameraId = null;
let pollInterval = null;
let trendChart = null;
let typeChart = null;

// ======================== Init ========================

document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    loadDashboardData();
    loadCameraList();
    pollInterval = setInterval(loadDashboardData, 5000);

    // Listen for new alerts
    window.addEventListener('ibvap-alert', (e) => {
        loadDashboardData();
    });
});

// ======================== Summary Stats ========================

async function loadDashboardData() {
    try {
        // Summary stats
        const summaryRes = await apiFetch('/api/statistics/summary');
        const summary = await summaryRes.json();

        document.getElementById('stat-cameras').textContent = `${summary.online_cameras}/${summary.total_cameras}`;
        document.getElementById('stat-cameras').classList.remove('skeleton');
        
        document.getElementById('stat-alerts').textContent = summary.unreviewed_alerts || 0;
        document.getElementById('stat-alerts').classList.remove('skeleton');
        
        document.getElementById('stat-tracks').textContent = summary.active_tracks || 0;
        document.getElementById('stat-tracks').classList.remove('skeleton');
        
        document.getElementById('stat-critical').textContent = summary.critical_alerts || 0;
        document.getElementById('stat-critical').classList.remove('skeleton');

        // Load alerts
        loadRecentAlerts();

        // Load camera status
        loadCameraStatus();

        // Load events
        loadEventTimeline();

        // Update charts
        loadChartData();

    } catch (err) {
        console.error('Dashboard data error:', err);
    }
}

// ======================== Camera List ========================

async function loadCameraList() {
    try {
        const res = await apiFetch('/api/cameras');
        const cameras = await res.json();
        const select = document.getElementById('camera-select');

        cameras.forEach(cam => {
            const opt = document.createElement('option');
            opt.value = cam.camera_id;
            opt.textContent = `${cam.name} (${cam.camera_id})`;
            select.appendChild(opt);
        });

        // Auto-select first camera
        if (cameras.length > 0) {
            switchCamera(cameras[0].camera_id);
            select.value = cameras[0].camera_id;
        }
    } catch (err) {
        console.error('Camera list error:', err);
    }
}

function switchCamera(cameraId) {
    currentCameraId = cameraId;
    const feed = document.getElementById('video-feed');
    const placeholder = document.getElementById('video-placeholder');

    if (cameraId) {
        feed.src = `/api/stream/${cameraId}`;
        feed.style.display = 'block';
        placeholder.style.display = 'none';

        feed.onerror = () => {
            feed.style.display = 'none';
            placeholder.style.display = 'flex';
            placeholder.innerHTML = '<i class="fas fa-video-slash"></i><p>Camera feed unavailable</p>';
        };
    } else {
        feed.style.display = 'none';
        placeholder.style.display = 'flex';
    }
}

// ======================== Recent Alerts ========================

async function loadRecentAlerts() {
    try {
        const res = await apiFetch('/api/alerts/live');
        const alerts = await res.json();
        const list = document.getElementById('alert-list');

        if (!alerts || alerts.length === 0) {
            list.innerHTML = '<div class="empty-state"><i class="fas fa-check-circle"></i><p>No active alerts</p></div>';
            return;
        }

        list.innerHTML = alerts.slice(0, 10).map(a => `
            <div class="alert-item" onclick="window.location.href='/events/${a.event_id}'">
                <div class="alert-level ${a.risk_level}"></div>
                <div class="alert-content">
                    <div class="alert-title">${formatEventType(a.event_type)}</div>
                    <div class="alert-meta">${a.camera_id} • Score ${a.risk_score?.toFixed(0) || 0} • ${formatTime(a.timestamp)}</div>
                </div>
            </div>
        `).join('');
    } catch (err) {
        console.error('Alert load error:', err);
    }
}

// ======================== Camera Status ========================

async function loadCameraStatus() {
    try {
        const res = await apiFetch('/api/cameras');
        const cameras = await res.json();
        const list = document.getElementById('camera-status-list');

        if (!cameras || cameras.length === 0) {
            list.innerHTML = '<div class="empty-state"><i class="fas fa-video-slash"></i><p>No cameras configured</p></div>';
            return;
        }

        list.innerHTML = cameras.map(c => `
            <div class="camera-status-item">
                <div>
                    <strong>${c.name}</strong>
                    <span class="camera-id" style="margin-left:8px">${c.camera_id}</span>
                </div>
                <div style="display:flex;align-items:center;gap:8px">
                    ${c.fps ? `<span class="fps-badge">${c.fps} FPS</span>` : ''}
                    <span class="status-dot ${c.status === 'online' ? 'online' : 'offline'}"></span>
                    <span>${c.status || 'unknown'}</span>
                </div>
            </div>
        `).join('');
    } catch (err) {
        console.error('Camera status error:', err);
    }
}

// ======================== Event Timeline ========================

async function loadEventTimeline() {
    try {
        const res = await apiFetch('/api/events?limit=10');
        const events = await res.json();
        const timeline = document.getElementById('event-timeline');

        if (!events || events.length === 0) {
            timeline.innerHTML = '<div class="empty-state"><i class="fas fa-clock"></i><p>No recent events</p></div>';
            return;
        }

        timeline.innerHTML = events.map(e => `
            <div class="timeline-item">
                <span class="risk-badge ${e.risk_level}">${getRiskEmoji(e.risk_level)}</span>
                <div style="flex:1">
                    <strong>${formatEventType(e.event_type)}</strong>
                    <div class="alert-meta">${e.camera_id} • ${e.object_type}</div>
                </div>
                <span class="timeline-time">${formatTime(e.timestamp)}</span>
            </div>
        `).join('');
    } catch (err) {
        console.error('Timeline error:', err);
    }
}

// ======================== Charts ========================

function initCharts() {
    // 1. Alert Trend Chart (Line/Area)
    const trendOptions = {
        series: [{ name: 'Alerts', data: [] }],
        chart: { type: 'area', height: 260, toolbar: { show: false }, background: 'transparent', fontFamily: 'Inter, sans-serif' },
        colors: ['#2563eb'],
        fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05, stops: [0, 90, 100] } },
        dataLabels: { enabled: false },
        stroke: { curve: 'smooth', width: 2 },
        xaxis: { categories: [], labels: { style: { colors: '#94a3b8' } }, axisBorder: { show: false }, axisTicks: { show: false } },
        yaxis: { labels: { style: { colors: '#94a3b8' } } },
        grid: { borderColor: 'rgba(148, 163, 184, 0.1)', strokeDashArray: 4 },
        tooltip: { theme: 'dark' }
    };
    trendChart = new ApexCharts(document.querySelector("#alert-trend-chart"), trendOptions);
    trendChart.render();

    // 2. Alert Type Breakdown (Donut)
    const typeOptions = {
        series: [],
        labels: [],
        chart: { type: 'donut', height: 260, background: 'transparent', fontFamily: 'Inter, sans-serif' },
        colors: ['#2563eb', '#16a34a', '#d97706', '#dc2626', '#0891b2', '#9333ea'],
        plotOptions: { pie: { donut: { size: '75%' } } },
        dataLabels: { enabled: false },
        stroke: { show: false },
        legend: { position: 'right', labels: { colors: '#94a3b8' } },
        tooltip: { theme: 'dark' }
    };
    typeChart = new ApexCharts(document.querySelector("#alert-type-chart"), typeOptions);
    typeChart.render();
}

async function loadChartData() {
    try {
        // Fetch timeseries
        const tsRes = await apiFetch('/api/statistics/timeseries');
        const tsData = await tsRes.json();
        if (trendChart && tsData.data.length > 0) {
            trendChart.updateSeries([{ name: 'Alerts', data: tsData.data }]);
            trendChart.updateOptions({ xaxis: { categories: tsData.labels } });
        }

        // Fetch types
        const statRes = await apiFetch('/api/statistics');
        const statData = await statRes.json();
        const types = statData.alert_stats?.by_type || {};
        const typeLabels = Object.keys(types).map(formatEventType);
        const typeSeries = Object.values(types);
        
        if (typeChart && typeSeries.length > 0) {
            typeChart.updateSeries(typeSeries);
            typeChart.updateOptions({ labels: typeLabels });
        }
    } catch (err) {
        console.error('Chart load error:', err);
    }
}
