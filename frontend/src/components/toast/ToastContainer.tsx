import { useState, useCallback } from 'react';
import { getRiskEmoji, formatEventType } from '../../api/client';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { Alert } from '../../types';

interface Toast {
  id: number;
  alert: Alert;
}

let toastId = 0;
const MAX_VISIBLE = 3;
const TTL_MS = 4000;

export default function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const handleAlert = useCallback((alert: Alert) => {
    const id = ++toastId;
    // keep only the most recent few so a burst of alerts can't blanket the screen
    setToasts(prev => [...prev, { id, alert }].slice(-MAX_VISIBLE));
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, TTL_MS);
  }, []);

  useWebSocket(handleAlert);

  const dismiss = (id: number) => setToasts(prev => prev.filter(t => t.id !== id));

  return (
    <div className="toast-container" id="toast-container">
      {toasts.map(({ id, alert }) => (
        <div key={id} className={`toast ${alert.risk_level}`} onClick={() => dismiss(id)} title="Dismiss">
          <div>
            <div className="toast-title">
              {getRiskEmoji(alert.risk_level)} {formatEventType(alert.event_type)}
            </div>
            <div className="toast-msg">
              {alert.camera_id} — Score: {alert.risk_score?.toFixed(0) || 0}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
