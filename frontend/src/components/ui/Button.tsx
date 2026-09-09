import type { ButtonHTMLAttributes, ReactNode } from 'react';
import Link from 'next/link';
import { cn } from '../../lib/cn';
import Icon from './Icon';

type Variant = 'default' | 'primary' | 'outline' | 'ghost' | 'danger' | 'success';
type Size = 'xs' | 'sm' | 'md';

const VARIANTS: Record<Variant, string> = {
  default: 'border-default bg-card text-fg hover:bg-elevated hover:border-strong',
  primary: 'border-transparent bg-accent text-white hover:bg-accent-hover',
  outline: 'border-default bg-transparent text-fg-muted hover:bg-elevated hover:text-fg',
  ghost: 'border-transparent bg-transparent text-fg-muted hover:bg-elevated hover:text-fg',
  danger: 'border-transparent bg-danger text-white hover:opacity-90',
  success: 'border-transparent bg-success text-white hover:opacity-90',
};

const SIZES: Record<Size, string> = {
  xs: 'px-2 py-1 text-[0.7rem] gap-1.5',
  sm: 'px-3 py-1.5 text-[0.78rem] gap-1.5',
  md: 'px-4 py-2 text-[0.82rem] gap-2',
};

const base =
  'inline-flex items-center justify-center rounded-sm border font-medium ' +
  'transition-colors disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap';

interface CommonProps {
  variant?: Variant;
  size?: Size;
  icon?: string;
  block?: boolean;
  children?: ReactNode;
  className?: string;
}

export function Button({
  variant = 'default', size = 'sm', icon, block, className, children, ...rest
}: CommonProps & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={cn(base, VARIANTS[variant], SIZES[size], block && 'w-full', className)} {...rest}>
      {icon && <Icon name={icon} />}
      {children}
    </button>
  );
}

export function ButtonLink({
  variant = 'default', size = 'sm', icon, block, className, children, href,
}: CommonProps & { href: string }) {
  return (
    <Link href={href} className={cn(base, VARIANTS[variant], SIZES[size], block && 'w-full', className)}>
      {icon && <Icon name={icon} />}
      {children}
    </Link>
  );
}
