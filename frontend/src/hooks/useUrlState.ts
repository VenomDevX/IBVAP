'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';

/**
 * Page state (filters, tabs, selected row) kept in the query string so it
 * survives reloads and can be shared as a link. Values equal to the default
 * are dropped from the URL.
 */
export function useUrlState<K extends string>(defaults: Record<K, string>) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const defaultsKey = JSON.stringify(defaults);

  const values = useMemo(() => {
    const base = JSON.parse(defaultsKey) as Record<K, string>;
    const out = {} as Record<K, string>;
    (Object.keys(base) as K[]).forEach(key => {
      out[key] = params.get(key) ?? base[key];
    });
    return out;
  }, [params, defaultsKey]);

  const setValues = useCallback((patch: Partial<Record<K, string | null>>) => {
    const base = JSON.parse(defaultsKey) as Record<string, string>;
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(patch) as [string, string | null | undefined][]) {
      if (value == null || value === '' || value === base[key]) next.delete(key);
      else next.set(key, value);
    }
    const query = next.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [params, router, pathname, defaultsKey]);

  return [values, setValues] as const;
}

export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
