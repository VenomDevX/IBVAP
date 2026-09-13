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
    <div className="flex items-center gap-5 rounded border border-default bg-surface shadow-sm p-6">
      <div
        className={cn(
          'grid size-12 shrink-0 place-items-center rounded-full text-lg shadow-sm',
          emphasis ? 'bg-danger/15 text-danger' : 'bg-accent/10 text-accent',
        )}
      >
        <Icon name={icon} />
      </div>
      <div className="min-w-0">
        <span className={cn('block text-3xl font-bold leading-none text-fg', loading && 'skeleton')}>
          {value}
        </span>
        <span className="mt-2 block text-xs font-semibold uppercase tracking-wider text-fg-muted">
          {label}
        </span>
      </div>
    </div>
  );
}
