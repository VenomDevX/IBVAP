'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { X } from '@phosphor-icons/react';
import { formatEventType, riskMeta } from '../../api/client';
import { useWebSocket } from '../../hooks/useWebSocket';
import { onToast, type ToastPayload } from '../../lib/toast';
import type { Alert } from '../../types';
import { IconButton } from '../ui/Button';
import { Dot } from '../ui/Indicators';

interface ToastItem extends ToastPayload {
  id: number;
}

let nextId = 0;
const MAX_VISIBLE = 3;
const TTL_MS = 6000;

function toastColor(level: ToastPayload['level']) {
  if (level === 'error') return 'var(--bad)';
  if (level === 'success') return 'var(--ok)';
  if (!level) return 'var(--accent)';
  return riskMeta(level).color;
}

export default function Toasts() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
  }, []);

  const add = useCallback((payload: ToastPayload) => {
    let assignedId = 0;
    setToasts(prev => {
      const existing = payload.eventKey ? prev.find(item => item.eventKey === payload.eventKey) : undefined;
      if (existing) {
        assignedId = existing.id;
        return prev.map(item => (item.id === existing.id ? { ...item, ...payload } : item));
      }
      assignedId = ++nextId;
      return [...prev, { id: assignedId, ...payload }].slice(-MAX_VISIBLE);
    });
    queueMicrotask(() => {
      const previous = timers.current.get(assignedId);
      if (previous) clearTimeout(previous);
      timers.current.set(assignedId, setTimeout(() => dismiss(assignedId), TTL_MS));
    });
  }, [dismiss]);

  const handleAlert = useCallback((alert: Alert) => {
    if (alert.risk_level !== 'high' && alert.risk_level !== 'critical') return;
    add({
      title: `${riskMeta(alert.risk_level).label}: ${formatEventType(alert.event_type)}`,
      message: `Camera ${alert.camera_id}, score ${Math.round(alert.risk_score ?? 0)}`,
      level: alert.risk_level,
      eventKey: alert.event_id,
      href: alert.event_id ? `/event?id=${alert.event_id}` : undefined,
    });
  }, [add]);

  useWebSocket(handleAlert);
  useEffect(() => onToast(add), [add]);
  useEffect(() => {
    const map = timers.current;
    return () => map.forEach(timer => clearTimeout(timer));
  }, []);

  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2">
      {toasts.map(t => (
        <div key={t.id} role={t.level === 'error' ? 'alert' : 'status'}
          className="pointer-events-auto flex animate-enter items-start gap-3 rounded-lg bg-surface py-3 pl-3.5 pr-2 shadow-pop">
          <Dot color={toastColor(t.level)} className="mt-1.5" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-fg">{t.title}</p>
            {t.message && <p className="mt-0.5 line-clamp-3 break-words text-sm text-muted">{t.message}</p>}
            {t.href && (
              <Link href={t.href} onClick={() => dismiss(t.id)} className="mt-1.5 inline-block text-sm font-medium text-accent hover:text-accent-hover">
                Open event
              </Link>
            )}
          </div>
          <IconButton label="Dismiss" size="sm" onClick={() => dismiss(t.id)}><X size={14} /></IconButton>
        </div>
      ))}
    </div>
  );
}
