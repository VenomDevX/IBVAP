import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../context/AuthContext';

const TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes

export function useSessionTimeout() {
  const { isAuthenticated, logout } = useAuth();
  const router = useRouter();
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;

    const reset = () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        logout().finally(() => router.replace('/login?timeout=1'));
      }, TIMEOUT_MS);
    };

    const events = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll'];
    events.forEach(e => window.addEventListener(e, reset, { passive: true }));
    reset();

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      events.forEach(e => window.removeEventListener(e, reset));
    };
  }, [isAuthenticated, logout, router]);
}
