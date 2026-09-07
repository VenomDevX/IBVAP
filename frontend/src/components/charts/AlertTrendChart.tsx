import ReactApexChart from 'react-apexcharts';
import type { ApexOptions } from 'apexcharts';
import type { TimeseriesData } from '../../types';

interface AlertTrendChartProps {
  data: TimeseriesData;
}

export default function AlertTrendChart({ data }: AlertTrendChartProps) {
  const options: ApexOptions = {
    chart: { type: 'area', height: 260, toolbar: { show: false }, background: 'transparent', fontFamily: 'Inter, sans-serif' },
    colors: ['#2563eb'],
    fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05, stops: [0, 90, 100] } },
    dataLabels: { enabled: false },
    stroke: { curve: 'smooth', width: 2 },
    xaxis: { categories: data.labels, labels: { style: { colors: '#94a3b8' } }, axisBorder: { show: false }, axisTicks: { show: false } },
    yaxis: { labels: { style: { colors: '#94a3b8' } } },
    grid: { borderColor: 'rgba(148, 163, 184, 0.1)', strokeDashArray: 4 },
    tooltip: { theme: 'dark' },
  };

  const series = [{ name: 'Alerts', data: data.data }];

  return <ReactApexChart options={options} series={series} type="area" height={260} />;
}
