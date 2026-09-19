'use client';

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/src/context/AuthContext';
import { useSessionTimeout } from '@/src/hooks/useSessionTimeout';
import Sidebar from '@/src/components/layout/Sidebar';
import Topbar from '@/src/components/layout/Topbar';
import Toasts from '@/src/components/layout/Toasts';
import { Loading } from '@/src/components/ui/States';

export default function AppLayout({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useSessionTimeout();

  useEffect(() => {
    if (!loading && !isAuthenticated) router.replace('/login');
  }, [loading, isAuthenticated, router]);

  if (loading || !isAuthenticated) {
    return <Loading label="Checking your session…" className="min-h-dvh" />;
  }

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[220px_minmax(0,1fr)]">
      <a href="#main"
        className="sr-only z-[70] rounded-md bg-surface px-3 py-2 text-sm shadow-pop focus:not-sr-only focus:fixed focus:left-4 focus:top-3">
        Skip to content
      </a>
      <Sidebar open={menuOpen} onClose={closeMenu} />
      <div className="flex min-h-dvh min-w-0 flex-col">
        <Topbar onMenu={() => setMenuOpen(true)} />
        <main id="main" className="flex-1 px-4 pb-10 pt-5 sm:px-6 lg:px-8">{children}</main>
      </div>
      <Toasts />
    </div>
  );
}
