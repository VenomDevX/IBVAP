import type { ReactNode } from 'react';
import Icon from '../ui/Icon';

export default function AuthShell({ subtitle, children, footer }: {
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-base p-5">
      <div className="w-full max-w-sm">
        <div className="rounded border border-default bg-card p-9">
          <div className="mb-8 text-center">
            <div className="mx-auto mb-4 grid size-14 place-items-center rounded-sm border border-default bg-elevated text-xl text-accent">
              <Icon name="shield-halved" />
            </div>
            <h1 className="text-xl font-bold text-fg">IBVAP</h1>
            <p className="mt-1 text-[0.82rem] text-fg-subtle">{subtitle}</p>
          </div>
          {children}
        </div>
        {footer && <div className="mt-6 text-center text-[0.75rem] text-fg-subtle">{footer}</div>}
      </div>
    </div>
  );
}
