'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '../../context/AuthContext';
import { useInterval } from '../../hooks/useInterval';
import { apiFetch } from '../../api/client';
import { cn } from '../../lib/cn';
import Icon from '../ui/Icon';
import type { DashboardSummary } from '../../types';

interface NavItem {
  href: string;
  label: string;
  icon: string;
  badge?: 'alerts';
}

const NAV: NavItem[] = [
  { href: '/', label: 'Dashboard', icon: 'gauge-high' },
  { href: '/cameras', label: 'Cameras', icon: 'video' },
  { href: '/multiview', label: 'Multi-View', icon: 'table-cells-large' },
  { href: '/map', label: 'Map View', icon: 'map-location-dot' },
  { href: '/alerts', label: 'Alerts', icon: 'bell', badge: 'alerts' },
  { href: '/events', label: 'Events', icon: 'list' },
  { href: '/zones', label: 'Zones', icon: 'draw-polygon' },
  { href: '/audit', label: 'Audit Log', icon: 'clipboard-list' },
  { href: '/settings', label: 'Settings', icon: 'gear' },
];

function isActive(pathname: string, href: string) {
  return href === '/' ? pathname === '/' : pathname.startsWith(href);
}

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [unreviewed, setUnreviewed] = useState(0);

  const poll = async () => {
    try {
      const r = await apiFetch('/api/statistics/summary');
      const s: DashboardSummary = await r.json();
      setUnreviewed(s.unreviewed_alerts ?? 0);
    } catch {
      /* transient — keep the last known count */
    }
  };
  useInterval(poll, 15000);

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-[90] bg-black/50 lg:hidden" onClick={onClose} aria-hidden />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-[100] flex w-60 flex-col border-r border-default bg-surface transition-transform duration-200',
          'lg:sticky lg:top-0 lg:h-screen lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex items-center gap-2.5 border-b border-default px-5 py-4">
          <Icon name="shield-halved" className="text-lg text-accent" />
          <div className="leading-tight">
            <div className="text-base font-bold text-fg">IBVAP</div>
            <div className="text-[0.68rem] font-medium text-fg-subtle">Border Surveillance AI</div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-3">
          {NAV.map(item => {
            const active = isActive(pathname, item.href);
            const showBadge = item.badge === 'alerts' && unreviewed > 0;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onClose}
                className={cn(
                  'mb-1 flex items-center gap-3 rounded-sm px-4 py-2.5 text-[0.85rem] font-medium transition-colors',
                  active
                    ? 'border-l-2 border-accent bg-elevated text-accent'
                    : 'text-fg-muted hover:bg-elevated hover:text-fg',
                )}
              >
                <Icon name={item.icon} className="w-5 text-center" />
                <span className="flex-1">{item.label}</span>
                {showBadge && (
                  <span className="rounded-sm bg-danger px-1.5 py-0.5 text-[0.65rem] font-semibold text-white tabular-nums">
                    {unreviewed > 99 ? '99+' : unreviewed}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center justify-between border-t border-default px-5 py-3.5">
          <span className="flex items-center gap-2 text-[0.8rem] text-fg-muted">
            <Icon name="circle-user" />
            {user?.email?.split('@')[0] || 'Operator'}
          </span>
          <button
            onClick={logout}
            title="Sign out"
            className="rounded-sm p-1.5 text-fg-subtle transition-colors hover:bg-elevated hover:text-danger"
          >
            <Icon name="power-off" />
          </button>
        </div>
      </aside>
    </>
  );
}
