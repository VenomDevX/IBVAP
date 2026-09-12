'use client';

import type { ApexOptions } from 'apexcharts';
import ApexChart from './ApexChart';
import { useThemeColors } from '../../hooks/useThemeColors';
import type { TimeseriesData } from '../../types';

export default function AlertTrendChart({ data }: { data: TimeseriesData }) {
  const c = useThemeColors();

  const options: ApexOptions = {
    chart: { type: 'area', height: 260, toolbar: { show: false }, background: 'transparent', fontFamily: 'inherit' },
    colors: [c.accent],
    fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.25, opacityTo: 0.02, stops: [0, 90, 100] } },
    dataLabels: { enabled: false },
    stroke: { curve: 'smooth', width: 2 },
    xaxis: {
      categories: data.labels,
      labels: { style: { colors: c.fgMuted } },
      axisBorder: { show: false },
      axisTicks: { show: false },
    },
    yaxis: { labels: { style: { colors: c.fgMuted } } },
    grid: { borderColor: c.border, strokeDashArray: 4 },
    tooltip: { theme: c.isLight ? 'light' : 'dark' },
  };

  return <ApexChart options={options} series={[{ name: 'Alerts', data: data.data }]} type="area" height={260} />;
}
