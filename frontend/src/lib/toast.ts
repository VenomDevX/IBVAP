import type { RiskLevel } from '../types';

export interface ToastPayload {
  title: string;
  message?: string;
  /** risk colour for alert toasts; 'error' for failed actions */
  level?: RiskLevel | 'unknown' | 'error' | 'success';
  /** dedupe key: a second toast with the same key updates the first */
  eventKey?: string;
  href?: string;
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
