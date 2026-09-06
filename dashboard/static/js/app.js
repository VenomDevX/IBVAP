/**
 * IBVAP — Main Application JavaScript
 * Core utilities, auth, and WebSocket connection.
 */

// ======================== Auth ========================

function getToken() {
    return localStorage.getItem('ibvap_token');
}

function checkAuth() {
    if (!getToken() && !window.location.pathname.includes('/login')) {
        window.location.href = '/login';
    }
}

function logout() {
    localStorage.removeItem('ibvap_token');
    localStorage.removeItem('ibvap_user');
    localStorage.removeItem('ibvap_role');
    window.location.href = '/login';
}

// Authenticated fetch wrapper
async function apiFetch(url, options = {}) {
    const token = getToken();
    const headers = { ...options.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
        logout();
        throw new Error('Unauthorized');
    }
    return res;
}

// ======================== WebSocket ========================

let ws = null;
let wsReconnectInterval = null;

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/alerts`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('WebSocket connected');
        if (wsReconnectInterval) {
            clearInterval(wsReconnectInterval);
            wsReconnectInterval = null;
        }
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'alert') {
                handleNewAlert(msg.data);
            }
        } catch (e) {
            console.error('WS message parse error:', e);
        }
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        if (!wsReconnectInterval) {
            wsReconnectInterval = setInterval(connectWebSocket, 5000);
        }
    };

    ws.onerror = (err) => {
        console.error('WebSocket error:', err);
    };
}

function handleNewAlert(alert) {
    showToast(alert);
    updateAlertBadge();

    // Dispatch custom event for dashboard
    window.dispatchEvent(new CustomEvent('ibvap-alert', { detail: alert }));
}

// ======================== Toast Notifications ========================

function showToast(alert) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${alert.risk_level}`;
    toast.innerHTML = `
        <div>
            <div class="toast-title">${getRiskEmoji(alert.risk_level)} ${formatEventType(alert.event_type)}</div>
            <div class="toast-msg">${alert.camera_id} — Score: ${alert.risk_score?.toFixed(0) || 0}</div>
        </div>
    `;

    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

// ======================== Utilities ========================

function getRiskEmoji(level) {
    return { low: '🟢', medium: '🟡', high: '🟠', critical: '🔴' }[level] || '⚪';
}

function formatEventType(type) {
    if (!type) return 'Unknown';
    return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatTime(timestamp) {
    if (!timestamp) return '—';
    try {
        const date = new Date(timestamp);
        if (isNaN(date)) return timestamp;
        return date.toLocaleString('en-IN', {
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            day: '2-digit', month: 'short',
            hour12: false,
        });
    } catch { return timestamp; }
}

function updateAlertBadge() {
    const badge = document.getElementById('alert-badge');
    if (!badge) return;

    apiFetch('/api/statistics/summary')
        .then(r => r.json())
        .then(data => {
            const count = data.unreviewed_alerts || 0;
            badge.textContent = count;
            badge.style.display = count > 0 ? 'inline' : 'none';
        })
        .catch(() => {});
}

// Sidebar toggle
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    const overlay = document.getElementById('sidebar-overlay');
    if (overlay) overlay.classList.toggle('active');
}

// Update datetime
function updateDateTime() {
    const el = document.getElementById('datetime');
    if (el) {
        el.textContent = new Date().toLocaleString('en-IN', {
            weekday: 'short', day: '2-digit', month: 'short',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false,
        });
    }
}

// Set current user
function setCurrentUser() {
    const el = document.getElementById('current-user');
    if (el) {
        el.textContent = localStorage.getItem('ibvap_user') || 'User';
    }
}

// ======================== Theme ========================

function toggleTheme() {
    const isLight = document.documentElement.classList.toggle('light-theme');
    localStorage.setItem('ibvap_theme', isLight ? 'light' : 'dark');
    updateThemeIcon(isLight);
}

function updateThemeIcon(isLight) {
    const icon = document.querySelector('#theme-toggle i');
    if (icon) {
        icon.className = isLight ? 'fas fa-sun' : 'fas fa-moon';
    }
}

function loadTheme() {
    const theme = localStorage.getItem('ibvap_theme') || 'dark'; // Dark default
    const isLight = theme === 'light';
    if (isLight) {
        document.documentElement.classList.add('light-theme');
    }
    updateThemeIcon(isLight);
}

// ======================== Init ========================

document.addEventListener('DOMContentLoaded', () => {
    loadTheme();
    checkAuth();
    setCurrentUser();
    updateDateTime();
    setInterval(updateDateTime, 1000);
    updateAlertBadge();
    connectWebSocket();
});
