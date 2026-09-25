'use client';

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from 'recharts';
import { formatNumber } from '../../api/client';
import { useChartColors } from '../../hooks/useChartColors';
import type { TimeseriesData } from '../../types';

const COMPACT = new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 });

function TrendTooltip({ active, payload, label }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload?.length) return null;
  const count = Number(payload[0].value ?? 0);
  return (
    <div className="rounded-md bg-surface px-2.5 py-1.5 text-sm shadow-pop">
      <span className="num font-medium text-fg">{formatNumber(count)}</span>
      <span className="text-muted"> {count === 1 ? 'alert' : 'alerts'} at {label}</span>
    </div>
  );
}

export default function AlertTrend({ data, height = 180 }: { data: TimeseriesData; height?: number }) {
  const colors = useChartColors();
  const labels = data?.labels ?? [];
  const values = data?.data ?? [];
  const rows = labels.map((label, index) => ({ label, count: values[index] ?? 0 }));
  const total = rows.reduce((sum, row) => sum + row.count, 0);

  return (
    <div role="img" aria-label={`Alerts per hour over the last 24 hours, ${total} in total`} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 4, right: 0, bottom: 0, left: 0 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke={colors.line} />
          <XAxis dataKey="label" tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={24}
            tick={{ fill: colors.muted, fontSize: 12 }} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={44}
            tickFormatter={(value: number) => COMPACT.format(value)}
            tick={{ fill: colors.muted, fontSize: 12 }} />
          <Tooltip content={<TrendTooltip />} cursor={{ fill: colors.line, opacity: 0.5 }} isAnimationActive={false} />
          <Bar dataKey="count" fill={colors.accent} radius={[2, 2, 0, 0]} maxBarSize={16} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
