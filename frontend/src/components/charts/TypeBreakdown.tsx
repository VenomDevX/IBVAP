import { formatEventType, formatNumber } from '../../api/client';

/** Counts per event type as labelled bars; plain markup, readable without a legend. */
export default function TypeBreakdown({ counts, limit = 6 }: { counts: Record<string, number>; limit?: number }) {
  const rows = Object.entries(counts).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]).slice(0, limit);
  const max = rows[0]?.[1] ?? 0;

  if (rows.length === 0) return <p className="py-6 text-sm text-muted">No events recorded yet.</p>;

  return (
    <ul className="space-y-3">
      {rows.map(([type, count]) => (
        <li key={type}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate text-fg">{formatEventType(type)}</span>
            <span className="num shrink-0 text-muted">{formatNumber(count)}</span>
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-subtle">
            <div className="h-full rounded-full bg-accent" style={{ width: `${Math.max(2, (count / max) * 100)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
