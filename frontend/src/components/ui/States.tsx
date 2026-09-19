import type { ReactNode } from 'react';
import { CircleNotch } from '@phosphor-icons/react';
import { cn } from '../../lib/cn';

export function Loading({ label = 'Loading…', className }: { label?: string; className?: string }) {
  return (
    <div role="status" aria-live="polite" className={cn('flex items-center justify-center gap-2 py-12 text-sm text-muted', className)}>
      <CircleNotch size={16} className="animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function EmptyState({ icon, title, description, action, className, compact }: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center text-center', compact ? 'py-8' : 'py-16', className)}>
      {icon && <div className="mb-3 text-faint" aria-hidden>{icon}</div>}
      <p className="text-base font-medium text-fg">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-muted text-pretty">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('animate-pulse rounded-md bg-subtle', className)} />;
}

export function InlineError({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded-md bg-bad/8 px-3 py-2 text-sm text-bad">
      {children}
    </p>
  );
}
