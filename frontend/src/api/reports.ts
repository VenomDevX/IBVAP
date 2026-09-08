import { apiFetch } from './client';

export interface DailyReport {
  generated_at: string;
  report_period: string;
  summary: {
    total_alerts_24h: number;
    critical_alerts_24h: number;
    current_active_threats: number;
  };
  alerts: any[];
  active_threats: any[];
}

export async function fetchDailyReport(): Promise<DailyReport> {
  const res = await apiFetch('/api/reports/daily');
  return res.json();
}

export function generateCSV(report: DailyReport) {
  // Simple CSV generation
  let csv = 'Type,ID,Camera,Risk Level,Risk Score,Timestamp\n';
  
  // Add active threats
  report.active_threats.forEach(t => {
    csv += `Threat,${t.object_type},${t.camera_id},${t.risk_level},${t.risk_score},Live\n`;
  });

  // Add alerts
  report.alerts.forEach(a => {
    csv += `Alert,${a.alert_id},${a.camera_id},${a.risk_level},${a.risk_score},${a.timestamp}\n`;
  });

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', `ibvap_report_${new Date().toISOString().split('T')[0]}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function generatePDF(report: DailyReport) {
  // A simple way to generate PDF without heavy libraries is to construct a printable HTML string 
  // and open it in a new window, triggering window.print()
  
  const printWindow = window.open('', '_blank');
  if (!printWindow) return;

  const html = `
    <html>
      <head>
        <title>IBVAP Daily Report</title>
        <style>
          body { font-family: system-ui, sans-serif; padding: 2rem; color: #333; }
          h1 { border-bottom: 2px solid #0052cc; padding-bottom: 1rem; }
          .summary { display: flex; gap: 2rem; margin: 2rem 0; }
          .stat-box { background: #f4f5f7; padding: 1rem; border-radius: 8px; flex: 1; text-align: center; }
          .stat-value { font-size: 2rem; font-weight: bold; color: #0052cc; }
          table { width: 100%; border-collapse: collapse; margin-top: 2rem; }
          th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
          th { background-color: #f4f5f7; }
          .risk-critical { color: #d32f2f; font-weight: bold; }
          .risk-high { color: #f57c00; font-weight: bold; }
        </style>
      </head>
      <body>
        <h1>IBVAP Security Report</h1>
        <p><strong>Generated At:</strong> ${new Date(report.generated_at).toLocaleString()}</p>
        <p><strong>Period:</strong> ${report.report_period}</p>
        
        <div class="summary">
          <div class="stat-box">
            <div class="stat-value">${report.summary.total_alerts_24h}</div>
            <div>Total Alerts (24h)</div>
          </div>
          <div class="stat-box">
            <div class="stat-value" style="color: #d32f2f;">${report.summary.critical_alerts_24h}</div>
            <div>Critical Alerts (24h)</div>
          </div>
          <div class="stat-box">
            <div class="stat-value" style="color: #f57c00;">${report.summary.current_active_threats}</div>
            <div>Active Threats</div>
          </div>
        </div>

        <h2>Active Threats</h2>
        <table>
          <thead><tr><th>Type</th><th>Camera</th><th>Risk Level</th><th>Score</th></tr></thead>
          <tbody>
            ${report.active_threats.map(t => `
              <tr>
                <td>${t.object_type}</td>
                <td>${t.camera_id}</td>
                <td class="risk-${t.risk_level}">${t.risk_level}</td>
                <td>${t.risk_score.toFixed(1)}</td>
              </tr>
            `).join('')}
            ${report.active_threats.length === 0 ? '<tr><td colspan="4">No active threats</td></tr>' : ''}
          </tbody>
        </table>

        <h2>Recent Alerts (Top 20)</h2>
        <table>
          <thead><tr><th>ID</th><th>Camera</th><th>Type</th><th>Risk</th><th>Time</th></tr></thead>
          <tbody>
            ${report.alerts.slice(0, 20).map(a => `
              <tr>
                <td>${a.alert_id}</td>
                <td>${a.camera_id}</td>
                <td>${a.event_type}</td>
                <td class="risk-${a.risk_level}">${a.risk_level}</td>
                <td>${new Date(a.timestamp).toLocaleString()}</td>
              </tr>
            `).join('')}
            ${report.alerts.length === 0 ? '<tr><td colspan="5">No alerts in last 24h</td></tr>' : ''}
          </tbody>
        </table>

        <script>
          window.onload = function() { window.print(); window.onafterprint = function() { window.close(); } }
        </script>
      </body>
    </html>
  `;

  printWindow.document.write(html);
  printWindow.document.close();
}
