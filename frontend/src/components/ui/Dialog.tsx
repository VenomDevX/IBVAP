'use client';

import { useEffect, useId, useRef, type ReactNode } from 'react';
import { X } from '@phosphor-icons/react';
import { cn } from '../../lib/cn';
import { IconButton } from './Button';

/** Native <dialog>: focus trap, Escape and top-layer come for free. */
export default function Dialog({ open, onClose, title, description, children, footer, size = 'md' }: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: 'md' | 'lg';
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={event => { if (event.target === ref.current) onClose(); }}
      className={cn(
        'm-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] overscroll-contain rounded-lg bg-surface p-0 text-fg shadow-pop open:animate-enter',
        size === 'lg' ? 'max-w-2xl' : 'max-w-md',
      )}
    >
      {open && (
        <>
          <div className="flex items-start justify-between gap-4 px-5 pt-4">
            <div>
              <h2 id={titleId} className="text-lg font-medium">{title}</h2>
              {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
            </div>
            <IconButton label="Close" size="sm" onClick={onClose} className="-mr-2"><X size={16} /></IconButton>
          </div>
          <div className="px-5 pb-5 pt-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
        </>
      )}
    </dialog>
  );
}
