import { useState, useCallback } from 'react';
import { getRiskEmoji, formatEventType } from '../../api/client';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { Alert } from '../../types';

interface Toast {
  id: number;
  alert: Alert;
}

let toastId = 0;

export default function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const handleAlert = useCallback((alert: Alert) => {
    const id = ++toastId;
    setToasts(prev => [...prev, { id, alert }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  }, []);

  useWebSocket(handleAlert);

  return (
    <div className="toast-container" id="toast-container">
      {toasts.map(({ id, alert }) => (
        <div key={id} className={`toast ${alert.risk_level}`}>
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
