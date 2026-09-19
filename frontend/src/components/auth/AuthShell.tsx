import type { ReactNode } from 'react';

export default function AuthShell({ title, description, children, footer }: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas px-4 py-5 sm:px-8">
      <div className="flex items-center gap-2.5">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/ibvap-logo.svg" alt="" width={20} height={20} className="size-5" />
        <span className="text-base font-semibold tracking-tight" translate="no">IBVAP</span>
      </div>
      <main className="flex flex-1 items-center justify-center py-10">
        <div className="w-full max-w-[22rem]">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {description && <p className="mt-1 text-sm text-muted">{description}</p>}
          <div className="mt-7">{children}</div>
          {footer && <div className="mt-6 text-sm text-muted">{footer}</div>}
        </div>
      </main>
      <p className="text-xs text-muted">Intelligent Border Video Analytics Platform</p>
    </div>
  );
}
