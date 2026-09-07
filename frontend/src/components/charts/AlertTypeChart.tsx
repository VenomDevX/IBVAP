import ReactApexChart from 'react-apexcharts';
import type { ApexOptions } from 'apexcharts';
import { formatEventType } from '../../api/client';

interface AlertTypeChartProps {
  byType: Record<string, number>;
}

export default function AlertTypeChart({ byType }: AlertTypeChartProps) {
  const labels = Object.keys(byType).map(formatEventType);
  const series = Object.values(byType);

  const options: ApexOptions = {
    chart: { type: 'donut', height: 260, background: 'transparent', fontFamily: 'Inter, sans-serif' },
    labels,
    colors: ['#2563eb', '#16a34a', '#d97706', '#dc2626', '#0891b2', '#9333ea'],
    plotOptions: { pie: { donut: { size: '75%' } } },
    dataLabels: { enabled: false },
    stroke: { show: false },
    legend: { position: 'right', labels: { colors: '#94a3b8' } },
    tooltip: { theme: 'dark' },
  };

  if (series.length === 0) {
    return <div className="empty-state"><i className="fas fa-chart-pie" /><p>No data</p></div>;
  }

  return <ReactApexChart options={options} series={series} type="donut" height={260} />;
}
