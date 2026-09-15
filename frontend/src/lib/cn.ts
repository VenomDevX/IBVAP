export type ClassValue = string | number | false | null | undefined;

/** Tiny classlist joiner, no dependency. */
export function cn(...parts: ClassValue[]): string {
  return parts.filter(Boolean).join(' ');
}
