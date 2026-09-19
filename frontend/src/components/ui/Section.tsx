import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

/** A titled region of a page. Separated by whitespace, not a box. */
export default function Section({ title, description, action, children, className }: {
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('min-w-0', className)}>
      {(title || action) && (
        <div className="mb-3 flex min-h-8 items-center justify-between gap-4">
          <div className="min-w-0">
            {title && <h2 className="text-base font-medium text-fg">{title}</h2>}
            {description && <p className="text-sm text-muted">{description}</p>}
          </div>
          {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('mb-4 flex flex-wrap items-center gap-2', className)}>{children}</div>;
}

export function DetailRow({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-6 py-2 text-sm">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 text-right text-fg break-words">{children}</dd>
    </div>
  );
}
