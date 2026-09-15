'use client';

import { useMemo, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp } from '@phosphor-icons/react';
import { cn } from '../../lib/cn';
import { EmptyState, Loading } from './States';
import Pagination from './Pagination';

export interface Column<T> {
  key: string;
  header: string;
  /** value for sorting and search; defaults to row[key] */
  accessor?: (row: T) => string | number;
  render?: (row: T) => ReactNode;
  sortable?: boolean;
  align?: 'left' | 'right';
  className?: string;
  /** hide on narrow screens to keep the essentials readable */
  hideBelow?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
}

export type SortState = { key: string; dir: 'asc' | 'desc' } | null;

interface Props<T> {
  /** accessible table caption */
  label: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /**
   * Server mode: pass onSortChange (and paginate outside). Rows are shown as
   * given. Client mode: the table sorts, searches and paginates itself.
   */
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
  search?: string;
  pageSize?: number;
  loading?: boolean;
  emptyTitle?: string;
  emptyDescription?: ReactNode;
  /** CSS colour for a thin left rule, e.g. critical rows */
  rowAccent?: (row: T) => string | undefined;
  selectedKey?: string | null;
}

const HIDE: Record<NonNullable<Column<unknown>['hideBelow']>, string> = {
  sm: 'max-sm:hidden', md: 'max-md:hidden', lg: 'max-lg:hidden', xl: 'max-xl:hidden', '2xl': 'max-2xl:hidden',
};

function valueOf<T>(column: Column<T>, row: T): string | number {
  if (column.accessor) return column.accessor(row);
  const value = (row as Record<string, unknown>)[column.key];
  return value == null ? '' : (value as string | number);
}

export default function DataTable<T>({
  label, columns, rows, rowKey, sort, onSortChange, search = '', pageSize = 25, loading,
  emptyTitle = 'Nothing to show', emptyDescription, rowAccent, selectedKey,
}: Props<T>) {
  const server = !!onSortChange;
  const [localSort, setLocalSort] = useState<SortState>(null);
  const [page, setPage] = useState(1);
  const activeSort = server ? sort ?? null : localSort;

  const visible = useMemo(() => {
    if (server) return rows;
    const q = search.trim().toLowerCase();
    let out = q ? rows.filter(row => columns.some(c => String(valueOf(c, row)).toLowerCase().includes(q))) : rows;
    const column = localSort && columns.find(c => c.key === localSort.key);
    if (localSort && column) {
      const dir = localSort.dir === 'asc' ? 1 : -1;
      out = [...out].sort((a, b) => {
        const av = valueOf(column, a);
        const bv = valueOf(column, b);
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
        return String(av).localeCompare(String(bv), undefined, { numeric: true }) * dir;
      });
    }
    return out;
  }, [server, rows, columns, search, localSort]);

  const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));
  const current = Math.min(page, pageCount);
  const shown = server ? visible : visible.slice((current - 1) * pageSize, current * pageSize);

  const toggle = (key: string) => {
    const next: SortState = activeSort?.key === key
      ? { key, dir: activeSort.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: 'asc' };
    if (server) onSortChange?.(next);
    else { setLocalSort(next); setPage(1); }
  };

  return (
    <div aria-busy={loading || undefined}>
      <div className="-mx-3 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">{label}</caption>
          <thead>
            <tr className="border-b border-line">
              {columns.map(column => {
                const dir = activeSort?.key === column.key ? activeSort.dir : null;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={column.sortable ? (dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none') : undefined}
                    className={cn(
                      'whitespace-nowrap px-3 py-2 text-xs font-medium text-muted',
                      column.align === 'right' ? 'text-right' : 'text-left',
                      column.hideBelow && HIDE[column.hideBelow],
                    )}
                  >
                    {column.sortable ? (
                      <button type="button" onClick={() => toggle(column.key)}
                        className={cn('inline-flex items-center gap-1 rounded-sm transition-colors duration-150 hover:text-fg', dir && 'text-fg')}>
                        {column.header}
                        {dir === 'asc' ? <ArrowUp size={11} aria-hidden /> : dir === 'desc' ? <ArrowDown size={11} aria-hidden /> : null}
                      </button>
                    ) : column.header}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 ? (
              <tr><td colSpan={columns.length}><Loading /></td></tr>
            ) : shown.length === 0 ? (
              <tr><td colSpan={columns.length}><EmptyState compact title={emptyTitle} description={emptyDescription} /></td></tr>
            ) : shown.map(row => {
              const key = rowKey(row);
              const accent = rowAccent?.(row);
              return (
                <tr key={key} className={cn(
                  'border-b border-line/70 transition-colors duration-150 last:border-0 hover:bg-subtle/60',
                  selectedKey === key && 'bg-subtle hover:bg-subtle',
                )}>
                  {columns.map((column, index) => (
                    <td
                      key={column.key}
                      className={cn(
                        'px-3 py-2.5 align-middle text-fg',
                        column.align === 'right' ? 'text-right' : 'text-left',
                        column.hideBelow && HIDE[column.hideBelow],
                        column.className,
                      )}
                      style={index === 0 && accent ? { boxShadow: `inset 2px 0 0 ${accent}` } : undefined}
                    >
                      {column.render ? column.render(row) : String(valueOf(column, row))}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!server && visible.length > pageSize && (
        <Pagination page={current} pageSize={pageSize} total={visible.length} onPageChange={setPage} />
      )}
    </div>
  );
}
