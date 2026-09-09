import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';

type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';

const TONES: Record<Tone, string> = {
  neutral: 'border-default text-fg-muted',
  accent: 'border-accent/35 text-accent',
  success: 'border-success/35 text-success',
  warning: 'border-warning/35 text-warning',
  danger: 'border-danger/35 text-danger',
  info: 'border-info/35 text-info',
};

export default function Badge({
  tone = 'neutral', children, className,
}: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-sm border bg-card px-2 py-0.5',
        'text-[0.68rem] font-medium capitalize tabular-nums',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
