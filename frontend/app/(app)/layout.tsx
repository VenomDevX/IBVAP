'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/src/context/AuthContext';
import { useSessionTimeout } from '@/src/hooks/useSessionTimeout';
import Sidebar from '@/src/components/layout/Sidebar';
import Topbar from '@/src/components/layout/Topbar';
import ToastContainer from '@/src/components/toast/ToastContainer';
import { Loading } from '@/src/components/ui/States';

export default function AppLayout({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  useSessionTimeout();

  useEffect(() => {
    if (!loading && !isAuthenticated) router.replace('/login');
  }, [loading, isAuthenticated, router]);

  if (loading || !isAuthenticated) {
    return <Loading label="Authorising session…" className="min-h-screen" />;
  }

  return (
    <div className="lg:grid lg:grid-cols-[15rem_1fr]">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex min-h-screen min-w-0 flex-col">
        <Topbar onMenuToggle={() => setMenuOpen(v => !v)} />
        <main className="flex-1 p-4 sm:p-6">{children}</main>
      </div>
      <ToastContainer />
    </div>
  );
}
