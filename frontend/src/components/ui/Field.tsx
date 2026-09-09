import type { InputHTMLAttributes, SelectHTMLAttributes, ReactNode } from 'react';
import { cn } from '../../lib/cn';
import Icon from './Icon';

const control =
  'rounded-sm border border-default bg-input px-3 py-2 text-[0.85rem] text-fg ' +
  'outline-none transition-colors focus:border-accent placeholder:text-fg-subtle';

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(control, 'w-full', className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(control, 'cursor-pointer pr-8', className)} {...rest}>
      {children}
    </select>
  );
}

export function SearchInput({
  className, ...rest
}: InputHTMLAttributes<HTMLInputElement> & { className?: string }) {
  return (
    <div
      className={cn(
        'flex min-w-0 flex-1 items-center gap-2 rounded-sm border border-default bg-input px-3',
        'focus-within:border-accent sm:max-w-xs',
        className,
      )}
    >
      <Icon name="magnifying-glass" className="text-[0.75rem] text-fg-subtle" />
      <input
        className="w-full border-0 bg-transparent py-2 text-[0.82rem] text-fg outline-none placeholder:text-fg-subtle"
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
