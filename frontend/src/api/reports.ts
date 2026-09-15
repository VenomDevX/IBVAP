import { apiFetch, apiJson } from './client';

type Row = Record<string, string | number | null | undefined>;

export interface DailyReport {
  generated_at: string;
  report_period: string;
  summary: {
    total_alerts_24h: number;
    critical_alerts_24h: number;
    current_active_threats: number;
  };
  alerts: Row[];
  active_threats: Row[];
}

export function fetchDailyReport(): Promise<DailyReport> {
  return apiJson<DailyReport>('/api/reports/daily');
}

function download(url: string, filename: string) {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

const today = () => new Date().toISOString().split('T')[0];

export function generateCSV(report: DailyReport) {
  const cell = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`;
  let csv = 'Type,ID,Camera,Risk Level,Risk Score,Timestamp\n';
  report.active_threats.forEach(t => {
    csv += ['Threat', t.object_type, t.camera_id, t.risk_level, t.risk_score, 'Live'].map(cell).join(',') + '\n';
  });
  report.alerts.forEach(a => {
    csv += ['Alert', a.alert_id, a.camera_id, a.risk_level, a.risk_score, a.timestamp].map(cell).join(',') + '\n';
  });
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  download(URL.createObjectURL(blob), `ibvap_report_${today()}.csv`);
}

export async function generatePDF() {
  const response = await apiFetch('/api/reports/daily.pdf');
  if (!response.ok) throw new Error(`PDF request returned ${response.status}`);
  download(URL.createObjectURL(await response.blob()), `ibvap_report_${today()}.pdf`);
}

/** Download an authenticated file (evidence) through a blob URL. */
export async function downloadAuthenticated(path: string, filename: string) {
  const response = await apiFetch(path);
  if (!response.ok) throw new Error(`Download returned ${response.status}`);
  download(URL.createObjectURL(await response.blob()), filename);
}
