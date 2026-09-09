import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import Icon from './Icon';

export function Loading({ label = 'Loading…', className }: { label?: string; className?: string }) {
  return (
    <div className={cn('flex items-center justify-center gap-2 py-16 text-[0.85rem] text-fg-subtle', className)}>
      <Icon name="spinner" spin />
      {label}
    </div>
  );
}

export function EmptyState({
  icon = 'inbox', message, children,
}: { icon?: string; message: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-fg-subtle">
      <Icon name={icon} className="text-2xl opacity-50" />
      <p className="text-[0.85rem]">{message}</p>
      {children}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton h-4 w-full rounded-sm', className)} />;
}
