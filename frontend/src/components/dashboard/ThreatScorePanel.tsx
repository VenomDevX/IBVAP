'use client';

import { useEffect, useState } from 'react';
import { apiFetch, riskMeta } from '../../api/client';
import { useInterval } from '../../hooks/useInterval';
import Card from '../ui/Card';
import Icon from '../ui/Icon';
import { EmptyState, Loading } from '../ui/States';
import type { Threat, ThreatsData } from '../../types';

function severity(score: number) {
  if (score > 75) return { color: 'var(--risk-critical)' };
  if (score > 50) return { color: 'var(--risk-medium)' };
  return { color: 'var(--risk-low)' };
}

function ThreatRow({ threat }: { threat: Threat }) {
  const sev = severity(threat.risk_score);
  const meta = riskMeta(threat.risk_level);
  return (
    <div className="rounded-lg border-l-4 bg-elevated shadow-sm px-4 py-3" style={{ borderColor: meta.color }}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="size-2 shrink-0 rounded-full" style={{ background: meta.color }} aria-hidden />
          <strong className="text-[0.9rem] font-semibold capitalize text-fg">{threat.object_type}</strong>
          <span className="rounded border border-default bg-input px-2 py-0.5 text-[0.68rem] tracking-wide text-fg-subtle">
            {threat.camera_id}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="h-1.5 w-24 overflow-hidden rounded-full bg-default">
            <span className="block h-full transition-[width] duration-500" style={{ width: `${threat.risk_score}%`, background: sev.color }} />
          </span>
          <span className="text-[0.8rem] font-bold tabular-nums" style={{ color: sev.color }}>
            {threat.risk_score}/100
          </span>
        </div>
      </div>
      {threat.risk_factors.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {threat.risk_factors.map((factor, i) => (
            <span key={i} className="inline-flex items-center gap-1.5 rounded border border-default bg-card px-2 py-0.5 text-[0.72rem] text-fg-muted shadow-sm">
              <Icon name="triangle-exclamation" className="text-[0.6rem] text-warning" />
              {factor}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ThreatScorePanel() {
  const [threats, setThreats] = useState<Threat[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchThreats = async () => {
    try {
      const res = await apiFetch('/api/statistics/threats');
      const data: ThreatsData = await res.json();
      setThreats(data?.top_threats ?? []);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load threats:', err);
    }
  };

  useEffect(() => { fetchThreats(); }, []);
  useInterval(fetchThreats, 3000);

  return (
    <Card title="Live Threat Assessment" icon="shield-halved" iconColor="danger" className="mb-6">
      {loading ? (
        <Loading label="Loading threat scores…" />
      ) : threats.length === 0 ? (
        <EmptyState icon="circle-check" message="No active threats detected" />
      ) : (
        <div className="flex max-h-[26rem] flex-col gap-3 overflow-y-auto pr-1">
          {threats.map(t => <ThreatRow key={t.track_id} threat={t} />)}
        </div>
      )}
    </Card>
  );
}
