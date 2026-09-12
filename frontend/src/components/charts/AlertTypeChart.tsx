'use client';

import type { ApexOptions } from 'apexcharts';
import ApexChart from './ApexChart';
import { useThemeColors } from '../../hooks/useThemeColors';
import { formatEventType } from '../../api/client';
import { EmptyState } from '../ui/States';

export default function AlertTypeChart({ byType }: { byType: Record<string, number> }) {
  const c = useThemeColors();
  const labels = Object.keys(byType).map(formatEventType);
  const series = Object.values(byType);

  if (series.length === 0) {
    return <EmptyState icon="chart-pie" message="No alert data yet" />;
  }

  const options: ApexOptions = {
    chart: { type: 'donut', height: 260, background: 'transparent', fontFamily: 'inherit' },
    labels,
    colors: c.series,
    plotOptions: { pie: { donut: { size: '72%' } } },
    dataLabels: { enabled: false },
    stroke: { colors: [c.card], width: 2 },
    legend: { position: 'right', labels: { colors: c.fgMuted }, fontSize: '12px' },
    tooltip: { theme: c.isLight ? 'light' : 'dark' },
  };

  return <ApexChart options={options} series={series} type="donut" height={260} />;
}
