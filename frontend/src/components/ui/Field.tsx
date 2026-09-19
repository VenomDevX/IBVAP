import type { InputHTMLAttributes, LabelHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { CaretDown, MagnifyingGlass } from '@phosphor-icons/react';
import { cn } from '../../lib/cn';

const CONTROL =
  'w-full rounded-md border border-line bg-surface px-2.5 text-sm text-fg placeholder:text-muted ' +
  'transition-[border-color] duration-150 hover:border-line-strong ' +
  'disabled:cursor-not-allowed disabled:opacity-60 aria-[invalid=true]:border-bad';

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(CONTROL, 'h-8', className)} {...rest} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(CONTROL, 'min-h-20 py-2 leading-relaxed', className)} {...rest} />;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  wrapperClassName?: string;
}

export function Select({ className, wrapperClassName, children, ...rest }: SelectProps) {
  return (
    <div className={cn('relative', wrapperClassName)}>
      <select className={cn(CONTROL, 'h-8 appearance-none pr-8', className)} {...rest}>
        {children}
      </select>
      <CaretDown size={13} aria-hidden className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted" />
    </div>
  );
}

interface SearchInputProps extends InputHTMLAttributes<HTMLInputElement> {
  wrapperClassName?: string;
}

export function SearchInput({ className, wrapperClassName, ...rest }: SearchInputProps) {
  return (
    <div className={cn('relative', wrapperClassName)}>
      <MagnifyingGlass size={14} aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
      <Input type="search" className={cn('pl-8', className)} {...rest} />
    </div>
  );
}

export function Label({ className, ...rest }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn('mb-1.5 block text-sm font-medium text-fg', className)} {...rest} />;
}

export function Field({ label, htmlFor, hint, error, children, className }: {
  label: string;
  htmlFor: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} className="mt-1.5 text-sm text-bad">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-sm text-muted">{hint}</p>
      ) : null}
    </div>
  );
}
