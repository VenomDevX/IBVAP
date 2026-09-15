'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState, type ComponentType } from 'react';
import {
  Bell, ClipboardText, GearSix, GridFour, ListBullets, MapTrifold, Polygon, SignOut, SquaresFour, VideoCamera, X,
  type IconProps,
} from '@phosphor-icons/react';
import { apiFetch, formatStatus } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { useInterval } from '../../hooks/useInterval';
import { cn } from '../../lib/cn';
import type { DashboardSummary } from '../../types';
import { IconButton } from '../ui/Button';

interface NavItem {
  href: string;
  label: string;
  icon: ComponentType<IconProps>;
  countsAlerts?: boolean;
}

// Grouped by task: watch, investigate, configure, administer.
const GROUPS: NavItem[][] = [
  [
    { href: '/', label: 'Dashboard', icon: SquaresFour },
    { href: '/multiview', label: 'Multi-View', icon: GridFour },
    { href: '/map', label: 'Map View', icon: MapTrifold },
  ],
  [
    { href: '/alerts', label: 'Alerts', icon: Bell, countsAlerts: true },
    { href: '/events', label: 'Events', icon: ListBullets },
  ],
  [
    { href: '/cameras', label: 'Cameras', icon: VideoCamera },
    { href: '/zones', label: 'Zones', icon: Polygon },
  ],
  [
    { href: '/audit', label: 'Audit Log', icon: ClipboardText },
    { href: '/settings', label: 'Settings', icon: GearSix },
  ],
];

export function normalizePath(path: string) {
  return path.length > 1 ? path.replace(/\/+$/, '') : path;
}

function isActive(pathname: string, href: string) {
  const path = normalizePath(pathname);
  if (href === '/') return path === '/';
  if (href === '/events') return path === '/events' || path === '/event';
  return path === href || path.startsWith(`${href}/`);
}

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, role, logout } = useAuth();
  const [openAlerts, setOpenAlerts] = useState<number | null>(null);

  const loadCount = useCallback(async () => {
    try {
      const res = await apiFetch('/api/statistics/summary');
      if (!res.ok) return;
      const summary: DashboardSummary = await res.json();
      setOpenAlerts(summary.open_incidents ?? summary.unreviewed_alerts ?? 0);
    } catch {
      /* the topbar health indicator reports connectivity */
    }
  }, []);

  useEffect(() => { void loadCount(); }, [loadCount]);
  useInterval(loadCount, 15_000);

  // Close the mobile drawer after navigating.
  useEffect(() => { onClose(); }, [pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  const name = user?.email?.split('@')[0] ?? 'User';

  const signOut = async () => {
    await logout();
    router.replace('/login');
  };

  return (
    <>
      <div aria-hidden onClick={onClose}
        className={cn('fixed inset-0 z-40 bg-black/30 lg:hidden', open ? 'block' : 'hidden')} />
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[220px] flex-col border-r border-line bg-canvas transition-transform duration-150',
          'lg:sticky lg:top-0 lg:z-auto lg:h-dvh lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full max-lg:invisible',
        )}
      >
        <div className="flex h-14 items-center gap-2.5 px-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/ibvap-logo.svg" alt="" width={20} height={20} className="size-5" />
          <span className="text-base font-semibold tracking-tight" translate="no">IBVAP</span>
          <IconButton label="Close menu" size="sm" onClick={onClose} className="ml-auto lg:hidden"><X size={16} /></IconButton>
        </div>

        <nav aria-label="Primary" className="flex-1 space-y-5 overflow-y-auto px-2 py-3">
          {GROUPS.map((group, index) => (
            <ul key={index} className="space-y-0.5">
              {group.map(item => {
                const active = isActive(pathname, item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? 'page' : undefined}
                      className={cn(
                        'relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-[background-color,color] duration-150',
                        active
                          ? 'bg-subtle font-medium text-fg before:absolute before:inset-y-2 before:-left-2 before:w-0.5 before:rounded-full before:bg-accent'
                          : 'text-muted hover:bg-subtle/70 hover:text-fg',
                      )}
                    >
                      <Icon size={17} weight={active ? 'fill' : 'regular'} aria-hidden className={active ? 'text-accent' : undefined} />
                      {item.label}
                      {item.countsAlerts && !!openAlerts && (
                        <span className="num ml-auto text-xs text-muted">{openAlerts > 999 ? '999+' : openAlerts}</span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          ))}
        </nav>

        <div className="flex items-center gap-2 border-t border-line px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-fg">{name}</p>
            <p className="truncate text-xs text-muted">{role ? formatStatus(role) : 'Loading role…'}</p>
          </div>
          <IconButton label="Sign out" size="sm" onClick={signOut}><SignOut size={16} /></IconButton>
        </div>
      </aside>
    </>
  );
}
