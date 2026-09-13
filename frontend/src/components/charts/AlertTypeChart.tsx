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
    chart: { type: 'donut', height: 280, background: 'transparent', fontFamily: 'inherit' },
    labels,
    colors: c.series,
    plotOptions: { pie: { donut: { size: '68%' } } },
    dataLabels: { enabled: false },
    stroke: { colors: [c.card], width: 2 },
    legend: { show: false }, // Disable built-in legend entirely
    tooltip: { theme: c.isLight ? 'light' : 'dark' },
  };

  return (
    <div className="flex w-full items-center justify-center gap-8 px-4 h-full">
      <div className="shrink-0">
        <ApexChart options={options} series={series} type="donut" width={260} height={280} />
      </div>
      <div className="max-h-[260px] overflow-y-auto">
        <ul className="flex flex-col gap-2.5">
          {labels.map((label, idx) => (
            <li key={label} className="flex items-center gap-2 text-[0.8rem] text-fg-muted">
              <span
                className="size-3 shrink-0 rounded-full"
                style={{ backgroundColor: c.series[idx % c.series.length] }}
              />
              <span className="truncate" title={label}>{label}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
