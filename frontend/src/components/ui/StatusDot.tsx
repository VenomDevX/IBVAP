import { cn } from '../../lib/cn';

type Status = 'online' | 'offline' | 'connecting' | string;

const COLOR: Record<string, string> = {
  online: 'bg-success',
  offline: 'bg-danger',
  connecting: 'bg-warning',
};

export default function StatusDot({ status, className }: { status: Status; className?: string }) {
  return (
    <span
      className={cn('inline-block size-2 shrink-0 rounded-full', COLOR[status] ?? 'bg-danger', className)}
      aria-label={status}
    />
  );
}
