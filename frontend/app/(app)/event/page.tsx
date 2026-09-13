'use client';

import { Suspense, useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/src/context/AuthContext';
import { apiFetch, formatEventType, formatTime, mediaSrc, riskMeta } from '@/src/api/client';
import Icon from '@/src/components/ui/Icon';
import { ButtonLink } from '@/src/components/ui/Button';
import { EmptyState, Loading } from '@/src/components/ui/States';
import { cn } from '@/src/lib/cn';
import type { Event } from '@/src/types';

function yesNo(v: boolean | undefined) {
  return v ? 'Yes' : 'No';
}

function ContextRow({ label, value, description }: { label: string; value: string; description?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-default py-4 text-[0.85rem] last:border-0">
      <div>
        <div className="text-fg font-medium">{label}</div>
        {description && <div className="text-fg-subtle text-xs mt-0.5">{description}</div>}
      </div>
      <div className="flex items-center gap-2 text-right text-fg-muted font-medium">{value}</div>
    </div>
  );
}

function PremiumCard({ title, icon, colorClass, children, className }: { title: string; icon: string; colorClass?: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn("border border-default rounded bg-surface p-6 shadow-sm", className)}>
      <div className="flex items-center gap-3 mb-2">
        <div className={cn("w-10 h-10 rounded-full flex items-center justify-center", colorClass || "bg-accent/10 text-accent")}>
          <Icon name={icon} className="text-lg" />
        </div>
        <h2 className="text-lg font-medium text-fg">{title}</h2>
      </div>
      <div className="mt-4">
        {children}
      </div>
    </div>
  );
}

function EventDetail() {
  const params = useSearchParams();
  const eventId = params.get('id');
  const { mediaTicket } = useAuth();
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
    <div className="max-w-6xl mx-auto pb-10">
      <header className="mb-10 mt-2">
        <span
          className="mb-4 inline-flex items-center gap-3 rounded-full border px-4 py-1.5 text-[0.85rem] font-semibold bg-surface shadow-sm"
          style={{ borderColor: meta.color, color: meta.color }}
        >
          <span className="size-2.5 rounded-full shadow-[0_0_8px_currentColor]" style={{ background: meta.color }} aria-hidden />
          {meta.label}
          <span className="tabular-nums opacity-80 border-l pl-3 ml-1" style={{ borderColor: meta.color }}>
            {event.risk_score?.toFixed(0) || 0} / 100 Risk Score
          </span>
        </span>
        <h2 className="text-3xl font-bold text-fg mb-3">{formatEventType(event.event_type)}</h2>
        <p className="flex flex-wrap gap-x-6 gap-y-2 text-[0.9rem] text-fg-subtle">
          <span className="flex items-center gap-2"><Icon name="video" className="text-fg-muted" /> Camera {event.camera_id}</span>
          <span className="flex items-center gap-2"><Icon name="clock" className="text-fg-muted" /> {formatTime(event.timestamp)}</span>
          <span className="flex items-center gap-2"><Icon name="person" className="text-fg-muted" /> {event.object_type} (Track #{event.track_id})</span>
        </p>
      </header>

      {event.temporal_context?.semantic_description && (
        <PremiumCard title="Scene Description" icon="align-left" colorClass="bg-info/10 text-info" className="mb-6">
          <p className="text-[0.95rem] leading-relaxed text-fg p-2">{event.temporal_context.semantic_description}</p>
        </PremiumCard>
      )}

      <div className="mb-8 grid items-start gap-6 md:grid-cols-2 xl:grid-cols-3">
        <PremiumCard title="Contributing Factors" icon="list" colorClass="bg-warning/10 text-warning">
          {(event.contributing_factors ?? []).length === 0 ? (
            <p className="text-[0.85rem] text-fg-subtle p-2">None recorded in system</p>
          ) : (
            <ul className="space-y-3 p-1">
              {event.contributing_factors.map((f, i) => (
                <li key={i} className="flex items-start gap-3 text-[0.9rem] text-fg">
                  <Icon name="circle-check" className="text-success mt-1 shadow-sm rounded-full bg-success/10" /> 
                  <span className="leading-snug">{f}</span>
                </li>
              ))}
            </ul>
          )}
        </PremiumCard>

        <PremiumCard title="Spatial Context" icon="location-dot" colorClass="bg-accent/10 text-accent">
          <ContextRow label="In restricted zone" description="Breached geofenced area" value={yesNo(event.spatial_context?.in_restricted)} />
          <ContextRow label="Fence crossed" description="Perimeter violation detected" value={yesNo(event.spatial_context?.fence_crossed)} />
          <ContextRow label="Zones" description="Triggered regions" value={(event.spatial_context?.zones ?? []).join(', ') || 'None'} />
        </PremiumCard>

        <PremiumCard title="Temporal Context" icon="clock" colorClass="bg-purple-500/10 text-purple-400">
          <ContextRow label="Night time" description="Incident occurred after dark" value={yesNo(event.temporal_context?.is_night)} />
          <ContextRow label="Loitering" description="Prolonged static presence" value={yesNo(event.temporal_context?.is_loitering)} />
          <ContextRow label="Duration" description="Length of recorded event" value={`${event.duration?.toFixed(1) || 0}s`} />
        </PremiumCard>

        {evidenceFile && (
          <PremiumCard title="Evidence Snapshot" icon="image" colorClass="bg-success/10 text-success" className="md:col-span-2 xl:col-span-3">
            {imgFailed ? (
              <EmptyState icon="image" message="Evidence image unavailable or expired" />
            ) : (
              <div className="relative rounded-lg overflow-hidden border-2 border-default shadow-md group">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={mediaSrc(`/snapshots/${evidenceFile}`, mediaTicket)}
                  alt="Evidence snapshot"
                  className="w-full h-auto object-cover max-h-[600px] transition-transform duration-500 group-hover:scale-[1.01]"
                  onError={() => setImgFailed(true)}
                />
                <div className="absolute inset-0 ring-1 ring-inset ring-black/10 rounded-lg pointer-events-none"></div>
              </div>
            )}
            {event.evidence_hash && (
              <div className="mt-4 flex items-center justify-between bg-bg rounded p-3 border border-default">
                <div className="flex flex-col">
                  <span className="text-[0.65rem] font-bold uppercase tracking-wider text-fg-muted mb-1">SHA-256 Checksum</span>
                  <span className="font-mono text-xs text-fg-subtle break-all">{event.evidence_hash}</span>
                </div>
                <Icon name="shield-check" className="text-success text-xl ml-4" />
              </div>
            )}
          </PremiumCard>
        )}
      </div>

      <ButtonLink href="/events" icon="arrow-left" variant="secondary" className="px-6 py-2.5 shadow-sm rounded-lg">
        Back to Event History
      </ButtonLink>
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
