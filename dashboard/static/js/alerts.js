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
        const tbody = document.getElementById('alerts-tbody');

        if (!alerts.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center" style="padding:40px;color:var(--text-muted)">No alerts found</td></tr>';
            return;
        }

        tbody.innerHTML = alerts.map(a => `
            <tr>
                <td><span class="risk-badge ${a.risk_level}">${getRiskEmoji(a.risk_level)} ${a.risk_level}</span></td>
                <td class="mono">${a.alert_id}</td>
                <td>${formatEventType(a.event_type)}</td>
                <td>${a.camera_id}</td>
                <td>${formatTime(a.timestamp)}</td>
                <td><strong>${a.risk_score?.toFixed(0) || 0}</strong></td>
                <td>${a.reviewed
                    ? '<span style="color:var(--success)"><i class="fas fa-check"></i> Reviewed</span>'
                    : '<span style="color:var(--warning)"><i class="fas fa-clock"></i> Pending</span>'
                }</td>
                <td>
                    <a href="/events/${a.event_id}" class="btn btn-xs">View</a>
                    ${!a.reviewed ? `<button class="btn btn-xs btn-success" onclick="reviewAlert('${a.alert_id}')">Review</button>` : ''}
                </td>
            </tr>
        `).join('');
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
