import { cn } from '../../lib/cn';
import Icon from './Icon';

interface StatCardProps {
  icon: string;
  value: string | number;
  label: string;
  loading?: boolean;
  emphasis?: boolean;
}

export default function StatCard({ icon, value, label, loading, emphasis }: StatCardProps) {
  return (
    <div className="flex items-center gap-4 rounded-[3px] border border-default bg-card p-5">
      <div
        className={cn(
          'grid size-11 shrink-0 place-items-center rounded-sm text-sm',
          emphasis ? 'bg-danger/15 text-danger' : 'bg-elevated text-fg-muted',
        )}
      >
        <Icon name={icon} />
      </div>
      <div className="min-w-0">
        <span className={cn('block text-2xl font-semibold leading-none text-fg', loading && 'skeleton')}>
          {value}
        </span>
        <span className="mt-1.5 block text-[0.68rem] font-medium uppercase tracking-wider text-fg-subtle">
          {label}
        </span>
      </div>
    </div>
  );
}
