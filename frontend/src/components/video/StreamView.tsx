'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { VideoCameraSlash } from '@phosphor-icons/react';
import { mediaSrc } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { cn } from '../../lib/cn';

type LoadState = 'loading' | 'ok' | 'error';
const MAX_RETRIES = 3;
const RETRY_MS = 3000;

interface Props {
  /** stream path, e.g. /api/stream/CAM_1; null shows the idle state */
  path: string | null;
  alt: string;
  className?: string;
  idleLabel?: string;
  /**
   * 'stream' holds one MJPEG connection open. 'poll' fetches `${path}/snapshot`
   * one frame at a time. Browsers allow only 6 connections per host, so pages
   * showing many cameras must poll or the extra tiles never start.
   */
  mode?: 'stream' | 'poll';
  /** delay between snapshot requests in poll mode */
  pollMs?: number;
  children?: ReactNode;
}

/**
 * Live camera view with connecting / reconnecting / unavailable states.
 * In stream mode the media ticket is frozen for the life of the connection:
 * the backend checks it only when the request opens, so the 90s ticket refresh
 * must not reopen a working stream.
 */
export default function StreamView({ path, alt, className, idleLabel = 'No camera selected', mode = 'stream', pollMs = 1000, children }: Props) {
  const { mediaTicket } = useAuth();
  const latestTicket = useRef(mediaTicket);
  const [ticket, setTicket] = useState(mediaTicket);
  const [attempt, setAttempt] = useState(0);
  const [frame, setFrame] = useState(0);
  const [state, setState] = useState<LoadState>('loading');
  const [prevKey, setPrevKey] = useState(`${mode}:${path}`);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { latestTicket.current = mediaTicket; }, [mediaTicket]);

  const key = `${mode}:${path}`;
  if (key !== prevKey) {
    setPrevKey(key);
    setState('loading');
    setAttempt(0);
    setFrame(0);
    setTicket(mediaTicket);
  }

  useEffect(() => {
    if (!ticket && mediaTicket) setTicket(mediaTicket);
  }, [ticket, mediaTicket]);

  // Stream mode: reopen a failed connection a few times, then give up.
  useEffect(() => {
    if (mode !== 'stream' || state !== 'error' || attempt >= MAX_RETRIES) return;
    const timer = setTimeout(() => {
      setTicket(latestTicket.current);
      setAttempt(a => a + 1);
      setState('loading');
    }, RETRY_MS);
    return () => clearTimeout(timer);
  }, [mode, state, attempt]);

  useEffect(() => () => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
  }, [key]);

  // Poll mode: the next request is only scheduled once the current one settles,
  // so a slow backend never builds a queue of pending snapshots.
  const scheduleNext = (delay: number) => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
    pollTimer.current = setTimeout(() => {
      setTicket(latestTicket.current);
      setFrame(n => n + 1);
    }, delay);
  };

  const polling = mode === 'poll';
  const src = !path || !ticket
    ? null
    : polling
      ? mediaSrc(`${path}/snapshot?v=${frame}`, ticket)
      : mediaSrc(path, ticket);
  const failed = state === 'error' && (polling ? true : attempt >= MAX_RETRIES);

  const onLoad = () => {
    setState('ok');
    if (polling) scheduleNext(pollMs);
  };
  const onError = () => {
    // In poll mode keep showing the last good frame while retrying.
    setState(current => (polling && current === 'ok' ? 'ok' : 'error'));
    if (polling) scheduleNext(RETRY_MS);
  };

  return (
    <div className={cn('relative overflow-hidden bg-video', className)}>
      {src && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={polling ? key : `${src}#${attempt}`}
          src={src}
          alt={alt}
          width={1280}
          height={720}
          decoding="async"
          className={cn('absolute inset-0 size-full object-contain', state !== 'ok' && 'invisible')}
          onLoad={onLoad}
          onError={onError}
        />
      )}
      {(!path || state !== 'ok') && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-white/60">
          {(!path || (failed && !polling)) && <VideoCameraSlash size={22} aria-hidden />}
          <span>
            {!path ? idleLabel : failed && !polling ? 'Stream unavailable' : state === 'error' ? 'Reconnecting…' : 'Connecting…'}
          </span>
        </div>
      )}
      {children}
    </div>
  );
}
