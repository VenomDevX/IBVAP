'use client';

import Link from 'next/link';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, DownloadSimple, ShieldCheck } from '@phosphor-icons/react';
import {
  ApiError, apiJson, errorMessage, formatDuration, formatEventType, formatStatus, formatTime, mediaSrc,
} from '@/src/api/client';
import { downloadAuthenticated } from '@/src/api/reports';
import { useAuth } from '@/src/context/AuthContext';
import { pushToast } from '@/src/lib/toast';
import { Button, ButtonLink } from '@/src/components/ui/Button';
import Section, { DetailRow } from '@/src/components/ui/Section';
import { EmptyState, Loading } from '@/src/components/ui/States';
import { RiskLabel, Tag } from '@/src/components/ui/Indicators';
import type { Event } from '@/src/types';

const yesNo = (value: boolean | undefined) => (value ? 'Yes' : 'No');

function ScoreBreakdown({ breakdown }: { breakdown: NonNullable<Event['score_breakdown']> }) {
  const entries = Object.entries(breakdown).sort((a, b) => b[1].contribution - a[1].contribution);
  const max = Math.max(1, ...entries.map(([, item]) => item.contribution));
  return (
    <ul className="space-y-4">
      {entries.map(([category, item]) => (
        <li key={category}>
          <div className="flex items-baseline justify-between gap-4 text-sm">
            <span className="text-fg">{formatStatus(category)}</span>
            <span className="num text-fg">
              +{item.contribution.toFixed(1)}
              <span className="ml-2 text-muted">{item.raw_score.toFixed(0)} × {item.weight}</span>
            </span>
          </div>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-subtle">
            <div className="h-full rounded-full bg-accent" style={{ width: `${(item.contribution / max) * 100}%` }} />
          </div>
          {item.reasons?.length > 0 && <p className="mt-1.5 text-xs text-muted">{item.reasons.join(', ')}</p>}
        </li>
      ))}
    </ul>
  );
}

function EventDetail() {
  const eventId = useSearchParams().get('id');
  const { mediaTicket } = useAuth();
  const [event, setEvent] = useState<Event | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const [downloading, setDownloading] = useState<number | null>(null);

  useEffect(() => {
    if (!eventId) { setError('No event was specified in the link.'); return; }
    let cancelled = false;
    setEvent(null);
    setError(null);
    apiJson<Event>(`/api/events/${encodeURIComponent(eventId)}`)
      .then(result => { if (!cancelled) setEvent(result); })
      .catch(err => {
        if (cancelled) return;
        setError(err instanceof ApiError && err.status === 404 ? 'This event does not exist or you do not have access to its camera.' : errorMessage(err));
      });
    return () => { cancelled = true; };
  }, [eventId]);

  if (error) {
    return <EmptyState title="Event unavailable" description={error} action={<ButtonLink href="/events">Back to events</ButtonLink>} />;
  }
  if (!event) return <Loading label="Loading event…" />;

  const evidenceFile = event.evidence_path?.replace(/\\/g, '/').split('/').pop();
  const factors = event.contributing_factors ?? [];
  const breakdown = event.score_breakdown && Object.keys(event.score_breakdown).length > 0 ? event.score_breakdown : null;

  const download = async (url: string, evidenceId: number) => {
    setDownloading(evidenceId);
    try {
      await downloadAuthenticated(url, `${event.event_id}-evidence-${evidenceId}`);
    } catch (err) {
      pushToast({ title: 'Download failed', message: errorMessage(err), level: 'error' });
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="mx-auto max-w-6xl">
      <Link href="/events" className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors duration-150 hover:text-fg">
        <ArrowLeft size={14} aria-hidden /> Events
      </Link>

      <header className="mt-4 border-b border-line pb-6">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <RiskLabel level={event.risk_level} />
          <span className="num text-muted">Score {Math.round(event.risk_score ?? 0)} of 100</span>
          {event.state && <Tag>{formatStatus(event.state.toLowerCase())}</Tag>}
        </div>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">{formatEventType(event.event_type)}</h2>
        <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
          <span>Camera {event.camera_id}</span>
          <span className="num">{formatTime(event.timestamp)}</span>
          <span><span className="capitalize">{event.object_type}</span>, Track #{event.track_id}</span>
          {event.track_uuid && <span className="font-mono text-xs leading-5" translate="no">{event.track_uuid}</span>}
        </p>
      </header>

      <div className="grid gap-10 pt-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-10">
          {event.temporal_context?.semantic_description && (
            <Section title="Scene description">
              <p className="max-w-[65ch] text-base leading-relaxed text-fg">{event.temporal_context.semantic_description}</p>
            </Section>
          )}

          <Section title="Evidence">
            {!evidenceFile ? (
              <p className="text-sm text-muted">No snapshot was captured for this event.</p>
            ) : imageFailed || !mediaTicket ? (
              imageFailed
                ? <EmptyState compact title="Snapshot unavailable" description="The image has expired under the storage limit or was never written." />
                : <Loading label="Loading snapshot…" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={mediaSrc(`/snapshots/${evidenceFile}`, mediaTicket)}
                alt={`Evidence snapshot for ${formatEventType(event.event_type)} on camera ${event.camera_id}`}
                width={1280}
                height={720}
                className="h-auto w-full rounded-lg bg-video"
                onError={() => setImageFailed(true)}
              />
            )}
            {event.evidence_hash && (
              <div className="mt-3 flex items-start gap-2 text-sm">
                <ShieldCheck size={16} className="mt-0.5 shrink-0 text-ok" aria-hidden />
                <div className="min-w-0">
                  <p className="text-muted">SHA-256 checksum</p>
                  <p className="break-all font-mono text-xs text-fg" translate="no">{event.evidence_hash}</p>
                </div>
              </div>
            )}
            {!!event.evidence?.length && (
              <div className="mt-4 flex flex-wrap gap-2">
                {event.evidence.map(item => (
                  <Button key={item.evidence_id} size="sm" icon={<DownloadSimple size={14} />}
                    loading={downloading === item.evidence_id} onClick={() => void download(item.download_url, item.evidence_id)}>
                    Download {item.type.replaceAll('_', ' ')}
                  </Button>
                ))}
              </div>
            )}
          </Section>

          {breakdown && (
            <Section title="Score breakdown">
              <ScoreBreakdown breakdown={breakdown} />
            </Section>
          )}
        </div>

        <div className="min-w-0 space-y-10">
          <Section title="Why it was flagged">
            {factors.length === 0 ? (
              <p className="text-sm text-muted">No contributing factors were recorded.</p>
            ) : (
              <ul className="space-y-2">
                {factors.map((factor, index) => (
                  <li key={index} className="flex gap-2.5 text-sm text-fg">
                    <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-muted" />
                    {factor}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Where">
            <dl className="divide-y divide-line/70">
              <DetailRow label="Inside a restricted zone">{yesNo(event.spatial_context?.in_restricted)}</DetailRow>
              <DetailRow label="Fence crossed">{yesNo(event.spatial_context?.fence_crossed)}</DetailRow>
              <DetailRow label="Zones">{(event.spatial_context?.zones ?? []).join(', ') || 'None'}</DetailRow>
            </dl>
          </Section>

          <Section title="When">
            <dl className="divide-y divide-line/70">
              <DetailRow label="At night">{yesNo(event.temporal_context?.is_night)}</DetailRow>
              <DetailRow label="Loitering">{yesNo(event.temporal_context?.is_loitering)}</DetailRow>
              <DetailRow label="Duration"><span className="num">{formatDuration(event.duration)}</span></DetailRow>
              {event.opened_at && <DetailRow label="Opened"><span className="num">{formatTime(event.opened_at)}</span></DetailRow>}
              {event.closed_at && <DetailRow label="Closed"><span className="num">{formatTime(event.closed_at)}</span></DetailRow>}
            </dl>
          </Section>
        </div>
      </div>
    </div>
  );
}

export default function EventDetailPage() {
  return (
    <Suspense fallback={<Loading label="Loading event…" />}>
      <EventDetail />
    </Suspense>
  );
}
