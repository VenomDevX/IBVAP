'use client';

import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useTheme } from '../../context/ThemeContext';
import Icon from '../ui/Icon';
import { useSystemHealth } from '../../hooks/useSystemHealth';

const PAGE_TITLES: Record<string, string> = {
  '/': 'Command Dashboard',
  '/cameras': 'Camera Management',
  '/multiview': 'Multi-Camera View',
  '/map': 'Global Map View',
  '/alerts': 'Alert Center',
  '/events': 'Event History',
  '/event': 'Event Detail',
  '/zones': 'Virtual Zone Configuration',
  '/settings': 'System Settings',
  '/audit': 'Audit Log',
};

export default function Topbar({ onMenuToggle }: { onMenuToggle: () => void }) {
  const rawPath = usePathname();
  const pathname = rawPath !== '/' ? rawPath.replace(/\/$/, '') : '/';
  const { isLight, toggleTheme } = useTheme();
  const { health, reachable } = useSystemHealth();
  const [now, setNow] = useState('');

  useEffect(() => {
    const tick = () =>
      setNow(new Date().toLocaleString('en-IN', {
        weekday: 'short', day: '2-digit', month: 'short',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
      }));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const title = PAGE_TITLES[pathname] ?? 'IBVAP';
  const state = !reachable
    ? { label: reachable == null ? 'Checking system' : 'Backend unreachable', dot: 'bg-danger' }
    : health?.ready
      ? { label: `Operational · ${health.cameras.online}/${health.cameras.total} cameras`, dot: 'bg-success' }
      : { label: `Degraded · ${health?.pipeline ?? 'starting'}`, dot: 'bg-warning' };

  return (
    <header className="sticky top-0 z-[50] flex h-16 items-center justify-between gap-4 border-b border-default bg-base px-4 sm:px-6">
      <div className="flex items-center gap-3">
        <button className="text-fg lg:hidden" onClick={onMenuToggle} aria-label="Toggle menu">
          <Icon name="bars" className="text-lg" />
        </button>
        <h1 className="text-[1.05rem] font-semibold text-fg">{title}</h1>
      </div>

      <div className="flex items-center gap-3 sm:gap-5">
        <button
          onClick={toggleTheme}
          title={isLight ? 'Switch to dark' : 'Switch to light'}
          className="rounded-sm p-2 text-fg-subtle transition-colors hover:bg-elevated hover:text-fg"
        >
          <Icon name={isLight ? 'sun' : 'moon'} />
        </button>
        <span className="hidden items-center gap-2 text-[0.78rem] font-medium text-fg-muted sm:flex">
          <span className={`size-2 rounded-full ${state.dot}`} aria-hidden />
          {state.label}
        </span>
        <span className="hidden text-[0.8rem] tabular-nums text-fg-subtle md:block">{now}</span>
      </div>
    </header>
  );
}
