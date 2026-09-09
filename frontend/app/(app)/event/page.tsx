'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/src/context/AuthContext';
import { apiFetch, formatEventType, formatTime, mediaSrc, riskMeta } from '@/src/api/client';
import Card from '@/src/components/ui/Card';
import Icon from '@/src/components/ui/Icon';
import { ButtonLink } from '@/src/components/ui/Button';
import { EmptyState, Loading } from '@/src/components/ui/States';
import type { Event } from '@/src/types';

function yesNo(v: boolean | undefined) {
  return v ? 'Yes' : 'No';
}

function ContextRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-default py-2.5 text-[0.85rem] last:border-0">
      <span className="text-fg-muted">{label}</span>
      <span className="text-fg">{value}</span>
    </div>
  );
}

function EventDetail() {
  const params = useSearchParams();
  const eventId = params.get('id');
  const { session } = useAuth();
  const [event, setEvent] = useState<Event | null>(null);
  const [error, setError] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => {
    if (!eventId) { setError(true); return; }
    apiFetch(`/api/events/${eventId}`)
      .then(r => r.json())
      .then(setEvent)
      .catch(() => setError(true));
  }, [eventId]);

  if (error) return <EmptyState icon="circle-exclamation" message="Event not found" />;
  if (!event) return <Loading label="Loading event…" />;

  const meta = riskMeta(event.risk_level);
  const evidenceFile = event.evidence_path?.replace(/\\/g, '/').split('/').pop();

  return (
    <div>
      <header className="mb-6">
        <span
          className="mb-3 inline-flex items-center gap-3 rounded-sm border px-4 py-2 text-[0.85rem] font-semibold"
          style={{ borderColor: meta.color, color: meta.color }}
        >
          <span className="size-2 rounded-full" style={{ background: meta.color }} aria-hidden />
          {meta.label}
          <span className="tabular-nums opacity-80">{event.risk_score?.toFixed(0) || 0}/100</span>
        </span>
        <h2 className="text-xl font-semibold text-fg">{formatEventType(event.event_type)}</h2>
        <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[0.82rem] text-fg-subtle">
          <span className="flex items-center gap-1.5"><Icon name="video" /> {event.camera_id}</span>
          <span className="flex items-center gap-1.5"><Icon name="clock" /> {formatTime(event.timestamp)}</span>
          <span className="flex items-center gap-1.5"><Icon name="person" /> {event.object_type} · track {event.track_id}</span>
        </p>
      </header>

      {event.temporal_context?.semantic_description && (
        <Card title="Scene Description" icon="align-left" className="mb-6">
          <p className="text-[0.9rem] leading-relaxed text-fg">{event.temporal_context.semantic_description}</p>
        </Card>
      )}

      <div className="mb-6 grid items-start gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card title="Contributing Factors" icon="list">
          {(event.contributing_factors ?? []).length === 0 ? (
            <p className="text-[0.85rem] text-fg-subtle">None recorded</p>
          ) : (
            <ul className="space-y-2.5">
              {event.contributing_factors.map((f, i) => (
                <li key={i} className="flex items-center gap-2 text-[0.85rem] text-fg">
                  <Icon name="circle-check" className="text-fg-subtle" /> {f}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Spatial Context" icon="location-dot">
          <ContextRow label="In restricted zone" value={yesNo(event.spatial_context?.in_restricted)} />
          <ContextRow label="Fence crossed" value={yesNo(event.spatial_context?.fence_crossed)} />
          <ContextRow label="Zones" value={(event.spatial_context?.zones ?? []).join(', ') || 'None'} />
        </Card>

        <Card title="Temporal Context" icon="clock">
          <ContextRow label="Night time" value={yesNo(event.temporal_context?.is_night)} />
          <ContextRow label="Loitering" value={yesNo(event.temporal_context?.is_loitering)} />
          <ContextRow label="Duration" value={`${event.duration?.toFixed(1) || 0}s`} />
        </Card>

        {evidenceFile && (
          <Card title="Evidence" icon="image" className="md:col-span-2 xl:col-span-1">
            {imgFailed ? (
              <EmptyState icon="image" message="Evidence image unavailable" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={mediaSrc(`/snapshots/${evidenceFile}`, session?.access_token)}
                alt="Evidence snapshot"
                className="w-full rounded-sm border border-default"
                onError={() => setImgFailed(true)}
              />
            )}
            {event.evidence_hash && (
              <p className="mt-2.5 break-all text-[0.72rem] text-fg-subtle">
                <span className="font-medium text-fg-muted">SHA-256</span> {event.evidence_hash}
              </p>
            )}
          </Card>
        )}
      </div>

      <ButtonLink href="/events" icon="arrow-left">Back to events</ButtonLink>
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
