import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  icon?: string;
  headerRight?: ReactNode;
  className?: string;
  children: ReactNode;
}

export default function Card({ title, icon, headerRight, className = '', children }: CardProps) {
  return (
    <div className={`card ${className}`}>
      {title && (
        <div className="card-header">
          <h3>
            {icon && <i className={icon} />} {title}
          </h3>
          {headerRight}
        </div>
      )}
      <div className="card-body">{children}</div>
    </div>
  );
}
