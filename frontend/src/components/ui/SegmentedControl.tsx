'use client';

import { useRef, type KeyboardEvent } from 'react';
import { cn } from '../../lib/cn';

interface Option<T extends string> {
  value: T;
  label: string;
}

export default function SegmentedControl<T extends string>({ options, value, onChange, ariaLabel, className }: {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const index = options.findIndex(o => o.value === value);
    const step = event.key === 'ArrowRight' ? 1 : -1;
    const next = options[(index + step + options.length) % options.length];
    onChange(next.value);
    ref.current?.querySelector<HTMLButtonElement>(`[data-value="${next.value}"]`)?.focus();
  };

  return (
    <div ref={ref} role="radiogroup" aria-label={ariaLabel} onKeyDown={onKeyDown}
      className={cn('inline-flex h-8 items-center gap-0.5 rounded-md bg-subtle p-0.5', className)}>
      {options.map(option => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            data-value={option.value}
            onClick={() => onChange(option.value)}
            className={cn(
              'h-7 rounded-[5px] px-2.5 text-sm transition-[background-color,color] duration-150',
              active ? 'bg-surface font-medium text-fg shadow-[0_0_0_1px_var(--line)]' : 'text-muted hover:text-fg',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
