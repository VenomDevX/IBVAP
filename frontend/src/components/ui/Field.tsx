import type { InputHTMLAttributes, SelectHTMLAttributes, ReactNode } from 'react';
import { cn } from '../../lib/cn';
import Icon from './Icon';

const control =
  'rounded-lg border border-default bg-surface px-3 py-2.5 text-[0.85rem] text-fg ' +
  'outline-none transition-all duration-200 focus:border-accent focus:ring-1 focus:ring-accent/30 ' +
  'placeholder:text-fg-subtle hover:border-fg-muted/40 shadow-sm';

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  const hasWidth = typeof className === 'string' && className.includes('w-');
  return <input className={cn(control, !hasWidth && 'w-full', className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={cn('relative inline-flex', className)}>
      <select
        className={cn(
          control,
          'w-full cursor-pointer appearance-none pr-10',
        )}
        {...rest}
      >
        {children}
      </select>
      <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3 text-fg-muted">
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>
  );
}

export function SearchInput({
  className, ...rest
}: InputHTMLAttributes<HTMLInputElement> & { className?: string }) {
  return (
    <div
      className={cn(
        'flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-default bg-surface px-3 shadow-sm',
        'focus-within:border-accent focus-within:ring-1 focus-within:ring-accent/30 sm:max-w-xs',
        'transition-all duration-200 hover:border-fg-muted/40',
        className,
      )}
    >
      <Icon name="magnifying-glass" className="text-[0.75rem] text-fg-subtle" />
      <input
        className="w-full border-0 bg-transparent py-2.5 text-[0.82rem] text-fg outline-none placeholder:text-fg-subtle"
        {...rest}
      />
    </div>
  );
}

export function FieldLabel({ icon, children }: { icon?: string; children: ReactNode }) {
  return (
    <label className="mb-1.5 flex items-center gap-2 text-[0.82rem] font-medium text-fg-muted">
      {icon && <Icon name={icon} className="text-[0.72rem] text-fg-subtle" />}
      {children}
    </label>
  );
}
