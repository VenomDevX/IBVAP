import { riskMeta } from '../../api/client';
import { cn } from '../../lib/cn';

interface RiskBadgeProps {
  level: string | null | undefined;
  /** show the text label next to the dot (default true) */
  showLabel?: boolean;
  /** render inside a bordered pill (default true) */
  pill?: boolean;
  className?: string;
}

/** The coded colour indicator that replaces the risk emoji everywhere. */
export default function RiskBadge({ level, showLabel = true, pill = true, className }: RiskBadgeProps) {
  const meta = riskMeta(level);
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 text-[0.72rem] font-medium',
        pill && 'rounded-sm border border-default bg-card px-2 py-0.5',
        className,
      )}
    >
      <span className="size-2 shrink-0 rounded-full" style={{ background: meta.color }} aria-hidden />
      {showLabel && <span style={{ color: meta.color }}>{meta.label}</span>}
    </span>
  );
}

export function RiskDot({ level, className }: { level: string | null | undefined; className?: string }) {
  const meta = riskMeta(level);
  return (
    <span
      className={cn('inline-block size-2 shrink-0 rounded-full', className)}
      style={{ background: meta.color }}
      title={meta.label}
      aria-label={`${meta.label} risk`}
    />
  );
}
