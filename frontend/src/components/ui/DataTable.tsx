'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { cn } from '../../lib/cn';
import Icon from './Icon';
import { Button } from './Button';
import { EmptyState } from './States';

export interface Column<T> {
  key: string;
  header: string;
  /** value used for sorting + built-in search; defaults to row[key] */
  accessor?: (row: T) => string | number;
  render?: (row: T) => ReactNode;
  sortable?: boolean;
  className?: string;
  align?: 'left' | 'right' | 'center';
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  /** stable row id */
  rowKey: (row: T) => string;
  /** free-text filter across these accessors; omit to disable search */
  search?: string;
  pageSize?: number;
  emptyMessage?: string;
}

function defaultAccessor<T>(col: Column<T>, row: T): string | number {
  if (col.accessor) return col.accessor(row);
  const v = (row as Record<string, unknown>)[col.key];
  return v == null ? '' : (v as string | number);
}

export default function DataTable<T>({
  columns, rows, rowKey, search = '', pageSize = 15, emptyMessage = 'Nothing to show',
}: Props<T>) {
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' } | null>(null);
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(row =>
      columns.some(col => String(defaultAccessor(col, row)).toLowerCase().includes(q)),
    );
  }, [rows, columns, search]);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const col = columns.find(c => c.key === sort.key);
    if (!col) return filtered;
    const dir = sort.dir === 'asc' ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = defaultAccessor(col, a);
      const bv = defaultAccessor(col, b);
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv), undefined, { numeric: true }) * dir;
    });
  }, [filtered, sort, columns]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const current = Math.min(page, pageCount - 1);
  const slice = sorted.slice(current * pageSize, current * pageSize + pageSize);

  const toggleSort = (key: string) => {
    setPage(0);
    setSort(prev =>
      prev?.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' },
    );
  };

  const alignCls = (a?: string) =>
    a === 'right' ? 'text-right' : a === 'center' ? 'text-center' : 'text-left';

  return (
    <div className="overflow-hidden rounded-[3px] border border-default">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[0.82rem]">
          <thead>
            <tr className="bg-surface">
              {columns.map(col => (
                <th
                  key={col.key}
                  className={cn(
                    'border-b border-default px-4 py-2.5 text-[0.68rem] font-semibold uppercase tracking-wider text-fg-subtle',
                    alignCls(col.align),
                    col.sortable && 'cursor-pointer select-none hover:text-fg',
                  )}
                  onClick={col.sortable ? () => toggleSort(col.key) : undefined}
                >
                  <span className="inline-flex items-center gap-1.5">
                    {col.header}
                    {col.sortable && sort?.key === col.key && (
                      <Icon name={sort.dir === 'asc' ? 'arrow-up-short-wide' : 'arrow-down-wide-short'} className="text-[0.6rem]" />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.length === 0 ? (
              <tr>
                <td colSpan={columns.length}>
                  <EmptyState message={emptyMessage} />
                </td>
              </tr>
            ) : (
              slice.map(row => (
                <tr key={rowKey(row)} className="transition-colors hover:bg-elevated">
                  {columns.map(col => (
                    <td
                      key={col.key}
                      className={cn('border-b border-default px-4 py-2.5 text-fg', alignCls(col.align), col.className)}
                    >
                      {col.render ? col.render(row) : String(defaultAccessor(col, row))}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {sorted.length > pageSize && (
        <div className="flex items-center justify-between gap-3 border-t border-default bg-card px-4 py-2.5 text-[0.75rem] text-fg-subtle">
          <span>
            {current * pageSize + 1}–{Math.min((current + 1) * pageSize, sorted.length)} of {sorted.length}
          </span>
          <div className="flex gap-1.5">
            <Button size="xs" variant="outline" icon="chevron-left" disabled={current === 0} onClick={() => setPage(current - 1)}>
              Prev
            </Button>
            <Button size="xs" variant="outline" disabled={current >= pageCount - 1} onClick={() => setPage(current + 1)}>
              Next <Icon name="chevron-right" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
