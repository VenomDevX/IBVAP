/** Plain-language summaries of audit log entries. */

type Details = Record<string, unknown> | null | undefined;

function asDetails(details: unknown): Details {
  return details && typeof details === 'object' ? (details as Record<string, unknown>) : undefined;
}

function label(details: Details, idKey: string): string {
  const name = details?.name;
  const id = details?.[idKey];
  if (typeof name === 'string' && name && typeof id === 'string' && name !== id) return `${name} (${id})`;
  return String(id ?? name ?? 'unknown');
}

const FIELD_NAMES: Record<string, string> = {
  fps_limit: 'frame rate limit',
  source: 'video source',
  type: 'type',
  trigger_classes: 'trigger classes',
  camera_id: 'camera',
};

function show(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'none';
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'none';
  if (typeof value === 'boolean') return value ? 'on' : 'off';
  return String(value);
}

export function describeChanges(changes: unknown): string {
  if (!changes || typeof changes !== 'object') return '';
  return Object.entries(changes as Record<string, { from?: unknown; to?: unknown }>)
    .map(([field, diff]) => `${FIELD_NAMES[field] ?? field.replace(/_/g, ' ')}: ${show(diff?.from)} → ${show(diff?.to)}`)
    .join('; ');
}

/** One sentence for known actions, `null` for anything else. */
export function describeAudit(action: string, rawDetails: unknown): string | null {
  const d = asDetails(rawDetails);
  const changes = describeChanges(d?.changes);
  switch (action) {
    case 'enable_camera': return `Enabled camera ${label(d, 'camera_id')}`;
    case 'disable_camera': return `Disabled camera ${label(d, 'camera_id')}`;
    case 'update_camera':
      return `Changed camera ${label(d, 'camera_id')}${changes ? `: ${changes}` : ''}`;
    case 'create_camera': return `Added camera ${label(d, 'camera_id')}`;
    case 'retire_camera': return `Removed camera ${label(d, 'camera_id')}`;
    case 'restart_camera': return `Restarted camera ${label(d, 'camera_id')}`;
    case 'enable_zone': return `Enabled zone ${label(d, 'zone_id')}`;
    case 'disable_zone': return `Disabled zone ${label(d, 'zone_id')}`;
    case 'update_zone':
      return `Changed zone ${label(d, 'zone_id')}${changes ? `: ${changes}` : ''}`;
    case 'create_zone': return `Added zone ${label(d, 'zone_id')}`;
    case 'delete_zone': return `Deleted zone ${label(d, 'zone_id')}`;
    case 'watchlist_add':
      return `Added ${d?.plate ? `plate ${d.plate}` : 'a face'} to the ${show(d?.list_type)} watchlist`;
    case 'watchlist_remove': return `Removed watchlist entry ${show(d?.entry_id)}`;
    case 'purge_clips': {
      const gb = typeof d?.bytes === 'number' ? ` (${(d.bytes / 1024 ** 3).toFixed(1)} GB)` : '';
      return `Deleted ${show(d?.files)} video clips older than ${show(d?.older_than_days)} days${gb}`;
    }
    default: return null;
  }
}

export function isRawRequest(action: string): boolean {
  return / \//.test(action);
}
