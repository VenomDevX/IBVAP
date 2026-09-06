/**
 * IBVAP — Alerts Page JavaScript
 * Alert listing, filtering, and review functionality.
 */

document.addEventListener('DOMContentLoaded', () => {
    loadAlertCameras();
    loadAlerts();
});

async function loadAlertCameras() {
    try {
        const res = await apiFetch('/api/cameras');
        const cameras = await res.json();
        const select = document.getElementById('filter-camera');
        cameras.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.camera_id;
            opt.textContent = c.name;
            select.appendChild(opt);
        });
    } catch (err) { console.error(err); }
}

let gridInstance = null;

async function loadAlerts() {
    const level = document.getElementById('filter-level')?.value || '';
    const reviewed = document.getElementById('filter-reviewed')?.value || '';
    const camera = document.getElementById('filter-camera')?.value || '';

    let url = '/api/alerts?limit=200';
    if (level) url += `&risk_level=${level}`;
    if (reviewed !== '') url += `&reviewed=${reviewed}`;
    if (camera) url += `&camera_id=${camera}`;

    try {
        const res = await apiFetch(url);
        const alerts = await res.json();
        
        const mappedData = alerts.map(a => [
            gridjs.html(`<span class="risk-badge ${a.risk_level}">${getRiskEmoji(a.risk_level)} ${a.risk_level}</span>`),
            a.alert_id,
            formatEventType(a.event_type),
            a.camera_id,
            formatTime(a.timestamp),
            a.risk_score?.toFixed(0) || 0,
            gridjs.html(a.reviewed
                ? '<span style="color:var(--success)"><i class="fas fa-check"></i> Reviewed</span>'
                : '<span style="color:var(--warning)"><i class="fas fa-clock"></i> Pending</span>'),
            gridjs.html(`
                <a href="/events/${a.event_id}" class="btn btn-xs">View</a>
                ${!a.reviewed ? `<button class="btn btn-xs btn-success" onclick="reviewAlert('${a.alert_id}')">Review</button>` : ''}
            `)
        ]);

        if (gridInstance) {
            gridInstance.updateConfig({ data: mappedData }).forceRender();
        } else {
            gridInstance = new gridjs.Grid({
                columns: ["Level", "Alert ID", "Event Type", "Camera", "Time", "Score", "Status", "Actions"],
                data: mappedData,
                search: true,
                sort: true,
                pagination: { enabled: true, limit: 15 },
                className: { table: 'data-table' }
            }).render(document.getElementById('alerts-grid-wrapper'));
        }
    } catch (err) {
        console.error('Failed to load alerts:', err);
    }
}

function filterAlerts() {
    loadAlerts();
}

async function reviewAlert(alertId) {
    try {
        await apiFetch(`/api/alerts/${alertId}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reviewed_by: localStorage.getItem('ibvap_user') || 'operator' }),
        });
        loadAlerts();
    } catch (err) {
        console.error('Review error:', err);
    }
}
