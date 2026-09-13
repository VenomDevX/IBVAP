import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import Icon from './Icon';

interface CardProps {
  title?: string;
  icon?: string;
  iconColor?: 'accent' | 'danger' | 'success' | 'warning' | 'info' | 'purple' | 'neutral';
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

const colorMap = {
  accent: 'bg-accent/10 text-accent',
  danger: 'bg-danger/10 text-danger',
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  info: 'bg-info/10 text-info',
  purple: 'bg-purple-500/10 text-purple-400',
  neutral: 'bg-elevated text-fg-muted',
};

export default function Card({ title, icon, iconColor = 'accent', actions, className, bodyClassName, children }: CardProps) {
  return (
    <section className={cn('flex flex-col rounded border border-default bg-surface shadow-sm', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 px-6 pt-6 pb-2">
          <div className="flex items-center gap-3">
            {icon && (
              <div className={cn('w-10 h-10 rounded-full flex items-center justify-center shrink-0', colorMap[iconColor])}>
                <Icon name={icon} className="text-lg" />
              </div>
            )}
            <h2 className="text-lg font-medium text-fg">{title}</h2>
          </div>
          {actions && <div>{actions}</div>}
        </header>
      )}
      <div className={cn('p-6', bodyClassName)}>{children}</div>
    </section>
  );
}
