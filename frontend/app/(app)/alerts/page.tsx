'use client';

import Link from 'next/link';
import { Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowClockwise, X } from '@phosphor-icons/react';
import {
  apiJson, apiSend, errorMessage, formatEventType, formatRelative, formatStatus, formatTime, RISK_LEVELS, riskMeta,
} from '@/src/api/client';
import { canManageAlerts, useAuth } from '@/src/context/AuthContext';
import { useCameras } from '@/src/hooks/useCameras';
import { useInterval } from '@/src/hooks/useInterval';
import { useDebouncedValue, useUrlState } from '@/src/hooks/useUrlState';
import { pushToast } from '@/src/lib/toast';
import { cn } from '@/src/lib/cn';
import { Button, ButtonLink, IconButton } from '@/src/components/ui/Button';
import DataTable, { type Column, type SortState } from '@/src/components/ui/DataTable';
import Dialog from '@/src/components/ui/Dialog';
import { Field, Input, SearchInput, Select, Textarea } from '@/src/components/ui/Field';
import Pagination from '@/src/components/ui/Pagination';
import Section, { Toolbar } from '@/src/components/ui/Section';
import { InlineError, Loading } from '@/src/components/ui/States';
import { AlertStatusLabel, RiskLabel } from '@/src/components/ui/Indicators';
import type { Alert, AlertStatus, Paged } from '@/src/types';

const PAGE_SIZE = 25;

const STATUSES: AlertStatus[] = ['open', 'acknowledged', 'investigating', 'resolved', 'false_positive', 'reopened'];

const FALSE_ALARM_REASONS = [
  'Wrong object detection',
  'Duplicate alert',
  'Authorized person',
  'Authorized vehicle',
  'Incorrect zone',
  'Behavior incorrectly classified',
  'Other',
];

const DEFAULTS = { q: '', level: '', status: '', reviewed: '', camera: '', from: '', to: '', page: '1', sort: '', dir: '', id: '' };

const isClosed = (status: string | undefined) => status === 'resolved' || status === 'false_positive';

function AlertPane({ alertId, onClose, onChanged }: { alertId: string; onClose: () => void; onChanged: () => void }) {
  const { role } = useAuth();
  const canManage = canManageAlerts(role);
  const [alert, setAlert] = useState<Alert | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [assignee, setAssignee] = useState('');
  const [note, setNote] = useState('');
  const [falseAlarmOpen, setFalseAlarmOpen] = useState(false);
  const [reason, setReason] = useState(FALSE_ALARM_REASONS[0]);

  const load = useCallback(async () => {
    try {
      const detail = await apiJson<Alert>(`/api/alerts/${encodeURIComponent(alertId)}`);
      setAlert(detail);
      setAssignee(detail.assignee ?? '');
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [alertId]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !falseAlarmOpen && !(event.target as HTMLElement)?.closest('dialog')) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, falseAlarmOpen]);

  const update = async (key: string, changes: Record<string, string>, success: string) => {
    setPending(key);
    try {
      await apiSend(`/api/alerts/${encodeURIComponent(alertId)}`, 'PATCH', changes);
      pushToast({ title: success, level: 'success' });
      await load();
      onChanged();
      return true;
    } catch (err) {
      pushToast({ title: 'The alert was not updated', message: errorMessage(err), level: 'error' });
      return false;
    } finally {
      setPending(null);
    }
  };

  const addNote = async (event: FormEvent) => {
    event.preventDefault();
    if (!note.trim()) return;
    if (await update('note', { note: note.trim() }, 'Note added')) setNote('');
  };

  return (
    <>
      <div aria-hidden onClick={onClose} className="fixed inset-0 z-40 bg-black/30 xl:hidden" />
      <aside
        aria-label="Alert details"
        className={cn(
          'fixed inset-y-0 right-0 z-50 w-full overflow-y-auto overscroll-contain bg-canvas px-5 py-5 shadow-pop sm:w-[26rem]',
          'xl:sticky xl:top-[4.5rem] xl:z-auto xl:max-h-[calc(100dvh-5.5rem)] xl:w-auto xl:border-l xl:border-line xl:py-0 xl:pl-8 xl:pr-0 xl:shadow-none',
        )}
      >
        <div className="flex items-center justify-between gap-3">
          <p className="truncate font-mono text-xs text-muted" translate="no">{alertId}</p>
          <IconButton label="Close details" size="sm" onClick={onClose} className="-mr-1.5"><X size={16} /></IconButton>
        </div>

        {error ? (
          <div className="mt-4"><InlineError>This alert could not be loaded: {error}</InlineError></div>
        ) : !alert ? (
          <Loading label="Loading alert…" />
        ) : (
          <div className="space-y-8 pb-6">
            <div>
              <h2 className="text-xl font-semibold tracking-tight">{formatEventType(alert.event_type)}</h2>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                <RiskLabel level={alert.risk_level} score={alert.risk_score} />
                <AlertStatusLabel status={alert.status} />
              </div>
              <p className="mt-2 text-sm text-muted">
                Camera {alert.camera_id}
                {alert.object_type && <>, <span className="capitalize">{alert.object_type}</span></>}
                {alert.track_id != null && <>, Track #{alert.track_id}</>}
              </p>
              <p className="num text-sm text-muted">{formatTime(alert.timestamp)} ({formatRelative(alert.timestamp)})</p>
            </div>

            {canManage ? (
              <Section title="Response">
                <div className="flex flex-wrap gap-2">
                  {(alert.status ?? 'open') === 'open' || alert.status === 'reopened' ? (
                    <Button variant="primary" loading={pending === 'acknowledge'}
                      onClick={() => void update('acknowledge', { status: 'acknowledged' }, 'Alert acknowledged')}>
                      Acknowledge
                    </Button>
                  ) : null}
                  {!isClosed(alert.status) ? (
                    <>
                      <Button loading={pending === 'resolve'}
                        onClick={() => void update('resolve', { status: 'resolved', disposition: 'true_alarm' }, 'Alert resolved')}>
                        Resolve
                      </Button>
                      <Button variant="ghost" onClick={() => setFalseAlarmOpen(true)}>Mark false alarm</Button>
                    </>
                  ) : (
                    <Button loading={pending === 'reopen'} onClick={() => void update('reopen', { status: 'reopened' }, 'Alert reopened')}>
                      Reopen
                    </Button>
                  )}
                </div>
                <div className="mt-5 space-y-4">
                  <Field label="Status" htmlFor="alert-status">
                    <Select id="alert-status" value={alert.status ?? 'open'} disabled={!!pending}
                      onChange={e => void update('status', { status: e.target.value }, `Status set to ${formatStatus(e.target.value).toLowerCase()}`)}>
                      {STATUSES.map(status => <option key={status} value={status}>{formatStatus(status)}</option>)}
                    </Select>
                  </Field>
                  <form onSubmit={e => { e.preventDefault(); void update('assign', { assignee: assignee.trim() }, assignee.trim() ? `Assigned to ${assignee.trim()}` : 'Assignee cleared'); }}>
                    <Field label="Assignee" htmlFor="alert-assignee">
                      <div className="flex gap-2">
                        <Input id="alert-assignee" name="assignee" autoComplete="off" value={assignee}
                          onChange={e => setAssignee(e.target.value)} placeholder="Name or call sign…" />
                        <Button type="submit" loading={pending === 'assign'} disabled={assignee.trim() === (alert.assignee ?? '')}>Assign</Button>
                      </div>
                    </Field>
                  </form>
                </div>
              </Section>
            ) : (
              <p className="text-sm text-muted">Your role can view this alert but not change it.</p>
            )}

            {!!alert.contributing_factors?.length && (
              <Section title="Why it was flagged">
                <ul className="space-y-1.5">
                  {alert.contributing_factors.map((factor, index) => (
                    <li key={index} className="flex gap-2.5 text-sm">
                      <span aria-hidden className="mt-2 size-1 shrink-0 rounded-full bg-muted" />{factor}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            <Section title="Notes" description="Notes are permanent and part of the audit trail.">
              {alert.notes?.length ? (
                <ol className="space-y-3">
                  {alert.notes.map((item, index) => (
                    <li key={`${item.created_at}-${index}`} className="text-sm">
                      <p><span className="font-medium text-fg">{item.author}</span> <span className="num text-xs text-muted">{formatTime(item.created_at)}</span></p>
                      <p className="mt-0.5 whitespace-pre-wrap break-words text-fg">{item.note}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-muted">No notes yet.</p>
              )}
              {canManage && (
                <form onSubmit={addNote} className="mt-4 space-y-2">
                  <label htmlFor="alert-note" className="sr-only">New note</label>
                  <Textarea id="alert-note" name="note" value={note} onChange={e => setNote(e.target.value)} placeholder="What did you check or decide…" rows={3} />
                  <Button type="submit" size="sm" loading={pending === 'note'} disabled={!note.trim()}>Add note</Button>
                </form>
              )}
            </Section>

            <ButtonLink href={`/event?id=${encodeURIComponent(alert.event_id)}`} variant="secondary">Open full event</ButtonLink>
          </div>
        )}
      </aside>

      <Dialog
        open={falseAlarmOpen}
        onClose={() => setFalseAlarmOpen(false)}
        title="Mark as false alarm"
        description="The reason is used to tune detection. Pick the closest match."
        footer={
          <>
            <Button variant="ghost" onClick={() => setFalseAlarmOpen(false)}>Cancel</Button>
            <Button variant="primary" loading={pending === 'false_alarm'} onClick={async () => {
              const ok = await update('false_alarm', { status: 'false_positive', disposition: 'false_alarm', false_positive_reason: reason }, 'Marked as false alarm');
              if (ok) setFalseAlarmOpen(false);
            }}>
              Mark false alarm
            </Button>
          </>
        }
      >
        <fieldset className="space-y-1">
          <legend className="sr-only">Reason</legend>
          {FALSE_ALARM_REASONS.map(option => (
            <label key={option} className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-subtle">
              <input type="radio" name="false-alarm-reason" value={option} checked={reason === option}
                onChange={() => setReason(option)} className="size-4 accent-[var(--accent)]" />
              {option}
            </label>
          ))}
        </fieldset>
      </Dialog>
    </>
  );
}

function AlertsInner() {
  const [url, setUrl] = useUrlState(DEFAULTS);
  const cameras = useCameras();
  const [search, setSearch] = useState(url.q);
  const debouncedSearch = useDebouncedValue(search);
  const [rows, setRows] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  useEffect(() => {
    if (debouncedSearch !== url.q) setUrl({ q: debouncedSearch, page: null });
  }, [debouncedSearch]); // eslint-disable-line react-hooks/exhaustive-deps

  const page = Math.max(1, Number(url.page) || 1);
  const sort: SortState = url.sort ? { key: url.sort, dir: url.dir === 'asc' ? 'asc' : 'desc' } : null;

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setFetching(true);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (url.level) params.set('risk_level', url.level);
    if (url.status) params.set('status', url.status);
    if (url.reviewed) params.set('reviewed', url.reviewed);
    if (url.camera) params.set('camera_id', url.camera);
    if (url.q.trim()) params.set('search', url.q.trim());
    if (url.from) params.set('start_time', new Date(url.from).toISOString());
    if (url.to) params.set('end_time', new Date(url.to).toISOString());
    if (url.sort) { params.set('sort_by', url.sort); params.set('sort_order', url.dir === 'asc' ? 'asc' : 'desc'); }
    try {
      const data = await apiJson<Paged<Alert>>(`/api/alerts/query?${params}`);
      if (id !== requestId.current) return;
      setRows(data.items);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      if (id === requestId.current) setError(errorMessage(err));
    } finally {
      if (id === requestId.current) { setLoading(false); setFetching(false); }
    }
  }, [page, url.level, url.status, url.reviewed, url.camera, url.q, url.from, url.to, url.sort, url.dir]);

  useEffect(() => { void load(); }, [load]);
  useInterval(load, 15_000);

  const closePane = useCallback(() => setUrl({ id: null }), [setUrl]);
  const filtersActive = !!(url.q || url.level || url.status || url.reviewed || url.camera || url.from || url.to);

  const columns: Column<Alert>[] = [
    { key: 'priority', header: 'Level', sortable: true, render: alert => <RiskLabel level={alert.risk_level} score={alert.risk_score} /> },
    { key: 'event_type', header: 'Type', render: alert => <span className="whitespace-nowrap">{formatEventType(alert.event_type)}</span> },
    { key: 'camera_id', header: 'Camera', sortable: true },
    { key: 'timestamp', header: 'Time', sortable: true, render: alert => <span className="num whitespace-nowrap" title={formatTime(alert.timestamp)}>{formatTime(alert.timestamp)}</span> },
    { key: 'status', header: 'Status', sortable: true, render: alert => <AlertStatusLabel status={alert.status} /> },
    { key: 'assignee', header: 'Assignee', hideBelow: '2xl', render: alert => <span className={alert.assignee ? 'text-fg' : 'text-muted'}>{alert.assignee || 'Unassigned'}</span> },
    {
      key: 'actions', header: '', align: 'right',
      render: alert => (
        <span className="inline-flex items-center justify-end gap-3">
          <Link href={`/event?id=${encodeURIComponent(alert.event_id)}`} className="text-sm font-medium text-accent hover:text-accent-hover">View</Link>
          <Button size="sm" variant={url.id === alert.alert_id ? 'secondary' : 'ghost'} aria-pressed={url.id === alert.alert_id}
            onClick={() => setUrl({ id: url.id === alert.alert_id ? null : alert.alert_id })}>
            Manage
          </Button>
        </span>
      ),
    },
  ];

  return (
    <div>
      <Toolbar>
        <SearchInput placeholder="Search alerts…" aria-label="Search alerts" value={search}
          onChange={e => setSearch(e.target.value)} wrapperClassName="w-full sm:w-64" />
        <Select aria-label="Risk level" value={url.level} onChange={e => setUrl({ level: e.target.value, page: null })} wrapperClassName="w-36">
          <option value="">Any risk</option>
          {RISK_LEVELS.map(level => <option key={level} value={level}>{riskMeta(level).label}</option>)}
        </Select>
        <Select aria-label="Status" value={url.status} onChange={e => setUrl({ status: e.target.value, page: null })} wrapperClassName="w-40">
          <option value="">Any status</option>
          {STATUSES.map(status => <option key={status} value={status}>{formatStatus(status)}</option>)}
        </Select>
        <Select aria-label="Review state" value={url.reviewed} onChange={e => setUrl({ reviewed: e.target.value, page: null })} wrapperClassName="w-40">
          <option value="">Reviewed or not</option>
          <option value="false">Not reviewed</option>
          <option value="true">Reviewed</option>
        </Select>
        <Select aria-label="Camera" value={url.camera} onChange={e => setUrl({ camera: e.target.value, page: null })} wrapperClassName="w-44">
          <option value="">All cameras</option>
          {cameras.map(camera => <option key={camera.camera_id} value={camera.camera_id}>{camera.name}</option>)}
        </Select>
        <div className="w-[13.5rem]">
          <Input type="datetime-local" aria-label="From" title="From" value={url.from} onChange={e => setUrl({ from: e.target.value, page: null })} />
        </div>
        <div className="w-[13.5rem]">
          <Input type="datetime-local" aria-label="To" title="To" value={url.to} onChange={e => setUrl({ to: e.target.value, page: null })} />
        </div>
        {filtersActive && (
          <Button variant="ghost" onClick={() => { setSearch(''); setUrl({ q: null, level: null, status: null, reviewed: null, camera: null, from: null, to: null, page: null }); }}>
            Clear filters
          </Button>
        )}
        <Button variant="ghost" className="ml-auto" icon={<ArrowClockwise size={14} />} loading={fetching && !loading} onClick={() => void load()}>
          Refresh
        </Button>
      </Toolbar>

      <div className={cn('grid gap-8', url.id && 'xl:grid-cols-[minmax(0,1fr)_25rem]')}>
        <div className="min-w-0">
          {error && <div className="mb-4"><InlineError>Alerts could not be loaded: {error}</InlineError></div>}
          <DataTable
            label="Alerts"
            columns={columns}
            rows={rows}
            rowKey={alert => alert.alert_id}
            sort={sort}
            onSortChange={next => setUrl({ sort: next?.key ?? null, dir: next?.dir ?? null, page: null })}
            loading={loading}
            selectedKey={url.id || null}
            emptyTitle={filtersActive ? 'No alerts match these filters' : 'No alerts yet'}
            emptyDescription={filtersActive ? 'Widen the time range or clear a filter.' : 'Alerts are raised when an event crosses the risk threshold.'}
            rowAccent={alert => (alert.risk_level === 'critical' && !isClosed(alert.status) ? riskMeta('critical').color : undefined)}
          />
          <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={next => setUrl({ page: String(next) })} />
        </div>
        {url.id && <AlertPane key={url.id} alertId={url.id} onClose={closePane} onChanged={() => void load()} />}
      </div>
    </div>
  );
}

export default function AlertsPage() {
  return (
    <Suspense fallback={<Loading label="Loading alerts…" />}>
      <AlertsInner />
    </Suspense>
  );
}
