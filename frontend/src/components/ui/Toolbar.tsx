import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

/** Horizontal control strip used above lists and on page headers. */
export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('mb-4 flex flex-wrap items-center gap-3', className)}>{children}</div>
  );
}

export function Spacer() {
  return <div className="flex-1" />;
}
