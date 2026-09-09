import { cn } from '../../lib/cn';

interface IconProps {
  /** Font Awesome name without the family prefix, e.g. "video", "bell", "spinner" */
  name: string;
  className?: string;
  spin?: boolean;
  fixedWidth?: boolean;
  'aria-hidden'?: boolean;
}

/** Single wrapper so every icon in the app comes from one family (FA solid). */
export default function Icon({ name, className, spin, fixedWidth = true, ...rest }: IconProps) {
  return (
    <i
      className={cn('fa-solid', `fa-${name}`, fixedWidth && 'fa-fw', spin && 'fa-spin', className)}
      aria-hidden={rest['aria-hidden'] ?? true}
    />
  );
}
