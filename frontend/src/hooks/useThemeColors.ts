'use client';

import { useEffect, useState } from 'react';
import { useTheme } from '../context/ThemeContext';

export interface ThemeColors {
  accent: string;
  fgMuted: string;
  border: string;
  card: string;
  series: string[];
  isLight: boolean;
}

function read(): ThemeColors {
  const s = typeof window !== 'undefined' ? getComputedStyle(document.documentElement) : null;
  const v = (name: string, fallback: string) => (s ? s.getPropertyValue(name).trim() || fallback : fallback);
  return {
    accent: v('--accent-primary', '#2563eb'),
    fgMuted: v('--text-secondary', '#a0a0a0'),
    border: v('--border-color', '#333333'),
    card: v('--bg-card', '#222222'),
    series: [
      v('--accent-primary', '#2563eb'),
      v('--success', '#16a34a'),
      v('--warning', '#d97706'),
      v('--danger', '#dc2626'),
      v('--info', '#0891b2'),
      '#9333ea',
    ],
    isLight: typeof document !== 'undefined' && document.documentElement.classList.contains('light-theme'),
  };
}

/** Resolved CSS-variable colours for charts, refreshed on theme change. */
export function useThemeColors(): ThemeColors {
  const { isLight } = useTheme();
  const [colors, setColors] = useState<ThemeColors>(read);
  useEffect(() => {
    setColors(read());
  }, [isLight]);
  return colors;
}
