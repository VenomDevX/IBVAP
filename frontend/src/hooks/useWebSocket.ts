import { useEffect, useRef, useCallback } from 'react';
import type { Alert } from '../types';
import { supabase } from '../api/supabase';

export function useWebSocket(onAlert: (alert: Alert) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const closedRef = useRef(false);

  const connect = useCallback(async () => {
    if (closedRef.current) return;

    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;
    if (!token) {
      // not signed in yet — retry shortly without hammering
      reconnectRef.current = setTimeout(connect, 3000);
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/alerts?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      attemptRef.current = 0;
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'alert') onAlert(msg.data);
      } catch (e) {
        console.error('WS message parse error:', e);
      }
    };

    ws.onclose = () => {
      if (closedRef.current) return;
      // exponential backoff, capped at 30s — no fixed 5s storm
      const delay = Math.min(30000, 1000 * 2 ** attemptRef.current);
      attemptRef.current += 1;
      reconnectRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      /* onclose will handle reconnect */
    };

    wsRef.current = ws;
  }, [onAlert]);

  useEffect(() => {
    closedRef.current = false;
    connect();
    return () => {
      closedRef.current = true;
      wsRef.current?.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, [connect]);
}
