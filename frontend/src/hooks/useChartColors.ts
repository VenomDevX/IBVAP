'use client';

import { useEffect, useState } from 'react';
import { useTheme } from '../context/ThemeContext';

export interface ChartColors {
  accent: string;
  fg: string;
  muted: string;
  faint: string;
  line: string;
  lineStrong: string;
  surface: string;
  critical: string;
  ok: string;
}

const FALLBACK: ChartColors = {
  accent: '#0f766e', fg: '#1c1917', muted: '#6b6660', faint: '#9c968f', line: '#e7e5e2',
  lineStrong: '#d6d3cf', surface: '#ffffff', critical: '#b42318', ok: '#3f7d58',
};

function read(): ChartColors {
  if (typeof window === 'undefined') return FALLBACK;
  const style = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    accent: v('--accent', FALLBACK.accent),
    fg: v('--fg', FALLBACK.fg),
    muted: v('--muted', FALLBACK.muted),
    faint: v('--faint', FALLBACK.faint),
    line: v('--line', FALLBACK.line),
    lineStrong: v('--line-strong', FALLBACK.lineStrong),
    surface: v('--surface', FALLBACK.surface),
    critical: v('--risk-critical', FALLBACK.critical),
    ok: v('--ok', FALLBACK.ok),
  };
}

/**
 * Resolved hex values for libraries that write SVG attributes directly
 * (Recharts, Leaflet), where var(--x) does not work. Refreshes on theme change.
 */
export function useChartColors(): ChartColors {
  const { resolved } = useTheme();
  const [colors, setColors] = useState<ChartColors>(read);
  useEffect(() => {
    setColors(read());
  }, [resolved]);
  return colors;
}
