import type { RiskLevel } from '../types';

export interface ToastPayload {
  title: string;
  message?: string;
  level?: RiskLevel | 'unknown';
  eventKey?: string;
}

type Listener = (t: ToastPayload) => void;
const listeners = new Set<Listener>();

/** Fire a toast from anywhere (e.g. a failed export). */
export function pushToast(t: ToastPayload) {
  listeners.forEach(fn => fn(t));
}

export function onToast(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}
