'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { VideoCameraSlash } from '@phosphor-icons/react';
import { mediaSrc } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { cn } from '../../lib/cn';

type LoadState = 'loading' | 'ok' | 'error';
const MAX_RETRIES = 3;

/**
 * MJPEG (or any image) from the backend, with connecting / reconnecting /
 * unavailable states. The media ticket is frozen for the life of a stream: the
 * backend checks it only when the request opens, so refreshing it every 90s
 * must not reopen a working stream.
 */
export default function StreamView({ path, alt, className, idleLabel = 'No camera selected', children }: {
  path: string | null;
  alt: string;
  className?: string;
  idleLabel?: string;
  children?: ReactNode;
}) {
  const { mediaTicket } = useAuth();
  const latestTicket = useRef(mediaTicket);
  const [ticket, setTicket] = useState(mediaTicket);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>('loading');
  const [prevPath, setPrevPath] = useState(path);

  useEffect(() => { latestTicket.current = mediaTicket; }, [mediaTicket]);

  if (path !== prevPath) {
    setPrevPath(path);
    setState('loading');
    setAttempt(0);
    setTicket(mediaTicket);
  }

  useEffect(() => {
    if (!ticket && mediaTicket) setTicket(mediaTicket);
  }, [ticket, mediaTicket]);

  useEffect(() => {
    if (state !== 'error' || attempt >= MAX_RETRIES) return;
    const timer = setTimeout(() => {
      setTicket(latestTicket.current);
      setAttempt(a => a + 1);
      setState('loading');
    }, 3000);
    return () => clearTimeout(timer);
  }, [state, attempt]);

  const src = path && ticket ? mediaSrc(path, ticket) : null;
  const failed = state === 'error' && attempt >= MAX_RETRIES;

  return (
    <div className={cn('relative overflow-hidden bg-video', className)}>
      {src && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={`${src}#${attempt}`}
          src={src}
          alt={alt}
          width={1280}
          height={720}
          decoding="async"
          className={cn('absolute inset-0 size-full object-contain', state !== 'ok' && 'invisible')}
          onLoad={() => setState('ok')}
          onError={() => setState('error')}
        />
      )}
      {(!path || state !== 'ok') && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-white/60">
          {(!path || failed) && <VideoCameraSlash size={22} aria-hidden />}
          <span>{!path ? idleLabel : failed ? 'Stream unavailable' : state === 'error' ? 'Reconnecting…' : 'Connecting…'}</span>
        </div>
      )}
      {children}
    </div>
  );
}
