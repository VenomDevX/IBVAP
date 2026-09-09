import { cn } from '../../lib/cn';
import Icon from './Icon';

interface Option<T extends string> {
  value: T;
  label: string;
  icon?: string;
}

interface Props<T extends string> {
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel?: string;
}

export default function SegmentedControl<T extends string>({ options, value, onChange, ariaLabel }: Props<T>) {
  return (
    <div className="inline-flex overflow-hidden rounded-sm border border-default" role="group" aria-label={ariaLabel}>
      {options.map(opt => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-1.5 text-[0.78rem] transition-colors',
              'border-l border-default first:border-l-0',
              active ? 'bg-accent text-white' : 'bg-input text-fg-muted hover:bg-elevated hover:text-fg',
            )}
          >
            {opt.icon && <Icon name={opt.icon} />}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
