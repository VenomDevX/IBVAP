'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { ArrowClockwise, Plus } from '@phosphor-icons/react';
import { ApiError, apiJson, apiSend, errorMessage, formatTime, toDate } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { pushToast } from '@/src/lib/toast';
import { Button } from '@/src/components/ui/Button';
import DataTable, { type Column } from '@/src/components/ui/DataTable';
import Dialog from '@/src/components/ui/Dialog';
import { Field, Input, SearchInput, Select, Textarea } from '@/src/components/ui/Field';
import { Tag } from '@/src/components/ui/Indicators';
import { Toolbar } from '@/src/components/ui/Section';
import SegmentedControl from '@/src/components/ui/SegmentedControl';
import { EmptyState, InlineError } from '@/src/components/ui/States';
import type { WatchlistEntry, WatchlistKind, WatchlistListType, WatchlistResponse } from '@/src/types';

const LIST_LABELS: Record<WatchlistListType, string> = {
  wanted: 'Wanted',
  authorized: 'Authorized',
  vip: 'VIP',
};

const LIST_HINTS: Record<WatchlistListType, string> = {
  wanted: 'A sighting raises a critical alert.',
  authorized: 'Known and cleared: lowers the risk score.',
  vip: 'Shown to operators; no extra risk.',
};

type FormState = { plate: string; label: string; list_type: WatchlistListType; notes: string; image: File | null };
const EMPTY_FORM: FormState = { plate: '', label: '', list_type: 'wanted', notes: '', image: null };

function ListTag({ type }: { type: WatchlistListType }) {
  // cn() only joins classes, so Tag's own colours can't be overridden: wanted gets its own badge.
  if (type === 'wanted') {
    return (
      <span className="inline-flex h-5 items-center rounded-sm bg-bad/10 px-1.5 text-xs font-medium text-bad">
        {LIST_LABELS.wanted}
      </span>
    );
  }
  return <Tag>{LIST_LABELS[type]}</Tag>;
}

export default function WatchlistsPage() {
  const { role } = useAuth();
  const canEdit = role === 'admin' || role === 'commander' || role === 'supervisor';
  const [kind, setKind] = useState<WatchlistKind>('plate');
  const [rows, setRows] = useState<WatchlistEntry[]>([]);
  const [loaded, setLoaded] = useState<WatchlistResponse['loaded'] | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<{ status?: number; message: string } | null>(null);
  const [query, setQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<WatchlistEntry | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await apiJson<WatchlistResponse>(`/api/watchlists?kind=${kind}`);
      setRows(data.entries);
      setLoaded(data.loaded);
      setError(null);
    } catch (err) {
      setError({ status: err instanceof ApiError ? err.status : undefined, message: errorMessage(err) });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [kind]);

  useEffect(() => { void load(); }, [load]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm(f => ({ ...f, [key]: value }));

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setFormError(null);
    setFormOpen(true);
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      if (kind === 'plate') {
        await apiSend('/api/watchlists/plates', 'POST', {
          plate: form.plate, label: form.label, list_type: form.list_type, notes: form.notes,
        });
      } else {
        if (!form.image) throw new Error('Choose a photo showing one face');
        const body = new FormData();
        body.append('image', form.image);
        body.append('label', form.label);
        body.append('list_type', form.list_type);
        body.append('notes', form.notes);
        await apiJson('/api/watchlists/faces', { method: 'POST', body });
      }
      setFormOpen(false);
      pushToast({ title: `${form.label} added to the ${LIST_LABELS[form.list_type].toLowerCase()} list`, level: 'success' });
      void load();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const confirmRemove = async () => {
    if (!removing) return;
    setRemoveBusy(true);
    try {
      await apiSend(`/api/watchlists/${encodeURIComponent(removing.entry_id)}`, 'DELETE');
      pushToast({ title: `${removing.label} removed from the watchlist`, level: 'success' });
      setRemoving(null);
      void load();
    } catch (err) {
      pushToast({ title: 'Could not remove the entry', message: errorMessage(err), level: 'error' });
    } finally {
      setRemoveBusy(false);
    }
  };

  const columns: Column<WatchlistEntry>[] = [
    ...(kind === 'plate' ? [{
      key: 'plate', header: 'Plate', sortable: true, accessor: (row: WatchlistEntry) => row.plate ?? '',
      render: (row: WatchlistEntry) => <span className="num font-mono font-medium" translate="no">{row.plate}</span>,
    }] : []),
    {
      key: 'label', header: kind === 'plate' ? 'Description' : 'Name', sortable: true, accessor: row => row.label,
      render: row => <span className="font-medium">{row.label}</span>,
    },
    {
      key: 'list_type', header: 'List', sortable: true, accessor: row => row.list_type,
      render: row => <ListTag type={row.list_type} />,
    },
    {
      key: 'notes', header: 'Notes', hideBelow: 'lg', accessor: row => row.notes,
      render: row => row.notes
        ? <span className="block max-w-sm truncate text-muted" title={row.notes}>{row.notes}</span>
        : <span className="text-muted">None</span>,
    },
    {
      key: 'created_at', header: 'Added', sortable: true, hideBelow: 'md',
      accessor: row => toDate(row.created_at)?.getTime() ?? 0,
      render: row => (
        <span className="whitespace-nowrap text-muted">
          <span className="num">{formatTime(row.created_at)}</span> by {row.created_by}
        </span>
      ),
    },
    ...(canEdit ? [{
      key: 'actions', header: '', accessor: () => '',
      render: (row: WatchlistEntry) => (
        <Button size="sm" variant="ghost" className="text-bad hover:text-bad" onClick={() => setRemoving(row)}>
          Remove
        </Button>
      ),
    }] : []),
  ];

  const noun = kind === 'plate' ? 'plate' : 'face';

  return (
    <div>
      <Toolbar>
        <SegmentedControl
          ariaLabel="Watchlist type"
          value={kind}
          onChange={value => { setKind(value); setQuery(''); setRows([]); setLoading(true); }}
          options={[{ value: 'plate', label: 'Number plates' }, { value: 'face', label: 'Faces' }]}
        />
        <SearchInput placeholder={kind === 'plate' ? 'Filter by plate or description…' : 'Filter by name…'}
          aria-label="Filter watchlist" value={query} onChange={e => setQuery(e.target.value)} wrapperClassName="w-full sm:w-72" />
        {loaded && (
          <span className="num text-sm text-muted">
            {kind === 'plate' ? loaded.plates : loaded.faces} active in the live pipeline
          </span>
        )}
        <div className="ml-auto flex gap-1">
          <Button variant="ghost" icon={<ArrowClockwise size={14} />} loading={refreshing && !loading} onClick={() => void load()}>
            Refresh
          </Button>
          {canEdit && (
            <Button variant="primary" icon={<Plus size={14} />} onClick={openCreate}>Add {noun}</Button>
          )}
        </div>
      </Toolbar>

      {error && rows.length === 0 && !loading ? (
        <EmptyState
          title="The watchlist could not be loaded"
          description={error.status === 403 ? 'Your role cannot view watchlists.' : error.message}
          action={<Button onClick={() => void load()}>Try again</Button>}
        />
      ) : (
        <DataTable
          label={kind === 'plate' ? 'Number plate watchlist' : 'Face watchlist'}
          columns={columns}
          rows={rows}
          rowKey={row => row.entry_id}
          search={query}
          loading={loading}
          emptyTitle={query ? 'No entries match this filter' : `No ${noun}s on the watchlist`}
        />
      )}

      <Dialog
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={kind === 'plate' ? 'Add number plate' : 'Add face'}
        description={kind === 'plate'
          ? 'Matching tolerates common misreads such as 0/O, 1/I and 8/B.'
          : 'Use a clear, front-facing photo of one person. Only an encrypted face signature is stored, not the photo.'}
      >
        <form onSubmit={save} className="grid gap-4">
          {kind === 'plate' ? (
            <Field label="Number plate" htmlFor="wl-plate" hint="Spaces and dashes are ignored.">
              <Input id="wl-plate" name="plate" required minLength={4} maxLength={30} value={form.plate}
                autoComplete="off" spellCheck={false} className="font-mono uppercase"
                onChange={e => set('plate', e.target.value)} placeholder="MH 12 AB 3456" />
            </Field>
          ) : (
            <Field label="Photo" htmlFor="wl-image" hint="JPEG or PNG, up to 8 MB.">
              <Input id="wl-image" name="image" type="file" required accept="image/jpeg,image/png,image/webp"
                onChange={e => set('image', e.target.files?.[0] ?? null)} />
            </Field>
          )}
          <Field label={kind === 'plate' ? 'Description' : 'Name'} htmlFor="wl-label">
            <Input id="wl-label" name="label" required maxLength={200} value={form.label} autoComplete="off"
              onChange={e => set('label', e.target.value)}
              placeholder={kind === 'plate' ? 'White pickup, reported stolen…' : 'Full name or case reference…'} />
          </Field>
          <Field label="List" htmlFor="wl-list" hint={LIST_HINTS[form.list_type]}>
            <Select id="wl-list" name="list_type" value={form.list_type}
              onChange={e => set('list_type', e.target.value as WatchlistListType)}>
              {(Object.keys(LIST_LABELS) as WatchlistListType[]).map(value => (
                <option key={value} value={value}>{LIST_LABELS[value]}</option>
              ))}
            </Select>
          </Field>
          <Field label="Notes" htmlFor="wl-notes" hint="Optional. Case number, source of the request…">
            <Textarea id="wl-notes" name="notes" rows={3} maxLength={1000} value={form.notes}
              onChange={e => set('notes', e.target.value)} />
          </Field>
          {formError && <InlineError>{formError}</InlineError>}
          <div className="flex justify-end gap-2 border-t border-line pt-4">
            <Button variant="ghost" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button type="submit" variant="primary" loading={saving}>Add {noun}</Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={removing !== null}
        onClose={() => setRemoving(null)}
        title="Remove from watchlist?"
        description={removing ? `${removing.label}${removing.plate ? ` (${removing.plate})` : ''} will no longer be matched. The removal is recorded in the audit log.` : undefined}
        footer={(
          <>
            <Button variant="ghost" onClick={() => setRemoving(null)}>Cancel</Button>
            <Button variant="danger" loading={removeBusy} onClick={() => void confirmRemove()}>Remove</Button>
          </>
        )}
      />
    </div>
  );
}
