import { formatStatus, riskMeta, toDate } from '../../api/client';
import { cn } from '../../lib/cn';

export function Dot({ color, className }: { color: string; className?: string }) {
  return <span aria-hidden className={cn('inline-block size-2 shrink-0 rounded-full', className)} style={{ background: color }} />;
}

export function RiskDot({ level, className }: { level: string | null | undefined; className?: string }) {
  return <Dot color={riskMeta(level).color} className={className} />;
}

/** Colour is never the only signal: the level is always written out. */
export function RiskLabel({ level, score, className }: { level: string | null | undefined; score?: number | null; className?: string }) {
  const meta = riskMeta(level);
  return (
    <span className={cn('inline-flex items-center gap-2 whitespace-nowrap', className)}>
      <Dot color={meta.color} />
      <span className="text-fg">{meta.label}</span>
      {score != null && <span className="num text-muted">{Math.round(score)}</span>}
    </span>
  );
}

interface CameraLike { status: string; enabled?: boolean; last_frame_at?: string | null }

/** An "online" camera with no frame for this long is treated as stalled. */
export const STALE_AFTER_MS = 60_000;

/**
 * The backend keeps reporting "online" when a capture thread dies (e.g. after
 * running out of memory), so the last frame time is the real signal.
 */
export function isCameraStalled(camera: CameraLike, now = Date.now()): boolean {
  if (camera.enabled === false || camera.status !== 'online' || !camera.last_frame_at) return false;
  const last = toDate(camera.last_frame_at);
  return !!last && now - last.getTime() > STALE_AFTER_MS;
}

/** Disabled beats the reported status; a frozen "online" camera shows as stalled. */
export function cameraDisplayStatus(camera: CameraLike, now = Date.now()): string {
  if (camera.enabled === false) return 'disabled';
  if (isCameraStalled(camera, now)) return 'stalled';
  return camera.status;
}

export function isCameraLive(camera: CameraLike, now = Date.now()): boolean {
  return camera.enabled !== false && camera.status === 'online' && !isCameraStalled(camera, now);
}

export function statusColor(status: string | null | undefined): string {
  switch (status) {
    case 'online': return 'var(--ok)';
    case 'connecting':
    case 'stalled': return 'var(--warn)';
    case 'error': return 'var(--bad)';
    default: return 'var(--faint)';
  }
}

export function StatusLabel({ status, className }: { status: string | null | undefined; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 whitespace-nowrap', className)}>
      <Dot color={statusColor(status)} />
      <span>{formatStatus(status || 'unknown')}</span>
    </span>
  );
}

const ALERT_STATUS_COLOR: Record<string, string> = {
  open: 'var(--warn)',
  reopened: 'var(--warn)',
  acknowledged: 'var(--accent)',
  investigating: 'var(--accent)',
  resolved: 'var(--ok)',
  false_positive: 'var(--faint)',
};

export function AlertStatusLabel({ status }: { status: string | null | undefined }) {
  const value = status ?? 'open';
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <Dot color={ALERT_STATUS_COLOR[value] ?? 'var(--faint)'} className="size-1.5" />
      <span>{formatStatus(value)}</span>
    </span>
  );
}

export function Tag({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex h-5 items-center rounded-sm bg-subtle px-1.5 text-xs text-muted', className)}>
      {children}
    </span>
  );
}
