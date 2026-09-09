import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import Icon from './Icon';

interface CardProps {
  title?: string;
  icon?: string;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

export default function Card({ title, icon, actions, className, bodyClassName, children }: CardProps) {
  return (
    <section className={cn('flex flex-col rounded-[3px] border border-default bg-card', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-default px-4 py-3">
          <h3 className="flex items-center gap-2 text-[0.8rem] font-semibold text-fg">
            {icon && <Icon name={icon} className="text-[0.72rem] text-fg-subtle" />}
            {title}
          </h3>
          {actions}
        </header>
      )}
      <div className={cn('p-4', bodyClassName)}>{children}</div>
    </section>
  );
}
