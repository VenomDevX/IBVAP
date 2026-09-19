import { describe, expect, it } from 'vitest';
import { describeAudit, describeChanges, isRawRequest } from '../src/lib/audit';

describe('describeAudit', () => {
  it('names camera toggles', () => {
    expect(describeAudit('disable_camera', { camera_id: 'CAM_IN_MUMBAI', name: 'Mumbai Arterial Road' }))
      .toBe('Disabled camera Mumbai Arterial Road (CAM_IN_MUMBAI)');
    expect(describeAudit('enable_camera', { camera_id: 'cam_x' })).toBe('Enabled camera cam_x');
  });

  it('lists old and new values for edits', () => {
    expect(describeAudit('update_camera', {
      camera_id: 'cam_y', name: 'Gate Y',
      changes: { fps_limit: { from: 15, to: 8 }, enabled: { from: true, to: false } },
    })).toBe('Changed camera Gate Y (cam_y): frame rate limit: 15 → 8; enabled: on → off');
  });

  it('describes storage and watchlist actions', () => {
    expect(describeAudit('purge_clips', { files: 12, older_than_days: 30, bytes: 2 * 1024 ** 3 }))
      .toBe('Deleted 12 video clips older than 30 days (2.0 GB)');
    expect(describeAudit('watchlist_add', { plate: 'MH12AB3456', list_type: 'wanted' }))
      .toBe('Added plate MH12AB3456 to the wanted watchlist');
  });

  it('returns null for unknown actions and handles empty lists', () => {
    expect(describeAudit('PATCH /api/cameras/x', { status: 200 })).toBeNull();
    expect(describeChanges({ trigger_classes: { from: [], to: ['car'] } })).toBe('trigger classes: none → car');
  });

  it('recognises raw request entries', () => {
    expect(isRawRequest('PATCH /api/cameras/x')).toBe(true);
    expect(isRawRequest('disable_camera')).toBe(false);
  });
});
