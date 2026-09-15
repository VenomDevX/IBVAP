import { formatNumber } from '../../api/client';
import { Button } from './Button';

export default function Pagination({ page, pageSize, total, onPageChange }: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  if (total <= 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return (
    <div className="flex items-center justify-between gap-3 pt-3 text-sm text-muted">
      <span className="num">{formatNumber(from)}–{formatNumber(to)} of {formatNumber(total)}</span>
      <div className="flex gap-1.5">
        <Button size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>Previous</Button>
        <Button size="sm" disabled={to >= total} onClick={() => onPageChange(page + 1)}>Next</Button>
      </div>
    </div>
  );
}
