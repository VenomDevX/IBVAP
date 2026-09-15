'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { List, Moon, Sun } from '@phosphor-icons/react';
import { formatClock } from '../../api/client';
import { useTheme } from '../../context/ThemeContext';
import { useSystemHealth } from '../../hooks/useSystemHealth';
import { IconButton } from '../ui/Button';
import { Dot } from '../ui/Indicators';
import { normalizePath } from './Sidebar';

const TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/cameras': 'Cameras',
  '/multiview': 'Multi-View',
  '/map': 'Map',
  '/alerts': 'Alerts',
  '/events': 'Events',
  '/event': 'Event',
  '/zones': 'Zones',
  '/audit': 'Audit log',
  '/settings': 'Settings',
};

function HealthIndicator() {
  const { health, reachable } = useSystemHealth(15_000);
  let color = 'var(--faint)';
  let text = 'Checking backend…';
  if (reachable === false) {
    color = 'var(--bad)';
    text = 'Backend unreachable';
  } else if (health && health.pipeline !== 'ready') {
    color = 'var(--warn)';
    text = health.pipeline === 'starting' ? 'Pipeline starting' : 'Pipeline unavailable';
  } else if (health) {
    color = health.cameras.online < health.cameras.total ? 'var(--warn)' : 'var(--ok)';
    text = `${health.cameras.online} of ${health.cameras.total} cameras online`;
  }
  return (
    <Link href="/settings?tab=health" aria-live="polite"
      className="hidden items-center gap-2 rounded-md px-2 py-1 text-sm text-muted transition-colors duration-150 hover:bg-subtle hover:text-fg md:inline-flex">
      <Dot color={color} />
      <span className="num">{text}</span>
    </Link>
  );
}

function Clock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = window.setInterval(() => setNow(new Date()), 15_000);
    return () => window.clearInterval(id);
  }, []);
  if (!now) return null;
  return <time dateTime={now.toISOString()} className="num hidden text-sm text-muted sm:block">{formatClock(now)}</time>;
}

export default function Topbar({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const { resolved, toggle } = useTheme();
  const title = TITLES[normalizePath(pathname)] ?? 'IBVAP';

  useEffect(() => {
    document.title = title === 'IBVAP' ? 'IBVAP' : `${title} | IBVAP`;
  }, [title]);

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-canvas/90 px-4 backdrop-blur-sm sm:px-6 lg:px-8">
      <IconButton label="Open menu" onClick={onMenu} className="-ml-2 lg:hidden"><List size={18} /></IconButton>
      <h1 className="truncate text-lg font-semibold tracking-tight">{title}</h1>
      <div className="ml-auto flex items-center gap-1 sm:gap-2">
        <HealthIndicator />
        <IconButton label={resolved === 'dark' ? 'Use light theme' : 'Use dark theme'} onClick={toggle}>
          {resolved === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
        </IconButton>
        <Clock />
      </div>
    </header>
  );
}
