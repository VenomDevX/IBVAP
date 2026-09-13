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
  const cell = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`;
  let csv = 'Type,ID,Camera,Risk Level,Risk Score,Timestamp\n';
  
  // Add active threats
  report.active_threats.forEach(t => {
    csv += ['Threat', t.object_type, t.camera_id, t.risk_level, t.risk_score, 'Live'].map(cell).join(',') + '\n';
  });

  // Add alerts
  report.alerts.forEach(a => {
    csv += ['Alert', a.alert_id, a.camera_id, a.risk_level, a.risk_score, a.timestamp].map(cell).join(',') + '\n';
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
  URL.revokeObjectURL(url);
}

export async function generatePDF() {
  const response = await apiFetch('/api/reports/daily.pdf');
  if (!response.ok) throw new Error(`PDF request returned ${response.status}`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = `ibvap_report_${new Date().toISOString().split('T')[0]}.pdf`;
  link.click();
  URL.revokeObjectURL(url);
}
