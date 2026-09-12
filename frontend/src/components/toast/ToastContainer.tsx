'use client';

import { useCallback, useEffect, useState } from 'react';
import { formatEventType, riskMeta } from '../../api/client';
import { useWebSocket } from '../../hooks/useWebSocket';
import { onToast, type ToastPayload } from '../../lib/toast';
import type { Alert } from '../../types';

interface ToastItem extends ToastPayload {
  id: number;
}

let nextId = 0;
const MAX_VISIBLE = 3;
const TTL_MS = 4500;

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const add = useCallback((payload: ToastPayload) => {
    const id = ++nextId;
    setToasts(prev => [...prev, { id, ...payload }].slice(-MAX_VISIBLE));
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), TTL_MS);
  }, []);

  const handleAlert = useCallback((alert: Alert) => {
    add({
      title: formatEventType(alert.event_type),
      message: `${alert.camera_id} · score ${alert.risk_score?.toFixed(0) ?? 0}`,
      level: alert.risk_level,
    });
  }, [add]);

  useWebSocket(handleAlert);
  useEffect(() => onToast(add), [add]);

  const dismiss = (id: number) => setToasts(prev => prev.filter(t => t.id !== id));

  return (
    <div
      className="pointer-events-none fixed bottom-6 right-6 z-[1000] flex max-h-[calc(100vh-8rem)] flex-col-reverse gap-2 overflow-hidden"
    >
      {toasts.map(t => {
        const meta = riskMeta(t.level);
        return (
          <button
            key={t.id}
            onClick={() => dismiss(t.id)}
            className="pointer-events-auto flex w-72 items-start gap-3 rounded-sm border border-default bg-card px-4 py-3 text-left [animation:slide-in_0.25s_ease]"
          >
            <span className="mt-1 size-2 shrink-0 rounded-full" style={{ background: meta.color }} aria-hidden />
            <span className="min-w-0">
              <span className="block text-[0.82rem] font-semibold text-fg">{t.title}</span>
              {t.message && <span className="mt-0.5 block truncate text-[0.75rem] text-fg-muted">{t.message}</span>}
            </span>
          </button>
        );
      })}
    </div>
  );
}
