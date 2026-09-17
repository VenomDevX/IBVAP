import { test, expect } from '@playwright/test';
import { login } from './helpers';

// Preview only: never deletes real evidence. Deletion is covered by backend tests.
test('settings shows clip storage and previews an old-clip cleanup', async ({ page }) => {
  await login(page);
  await page.goto('/settings?tab=health');
  await page.waitForLoadState('load');

  // Waits on /api/health, /api/auth/me and the clip scan against a live, busy backend.
  await expect(page.getByText('Video clip recording')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/\d[\d,]* clips, /)).toBeVisible({ timeout: 20_000 });

  await page.getByLabel('Older than (days)').fill('3650');
  await page.getByRole('button', { name: 'Check' }).click();
  await expect(page.getByText(/No clips are that old|clips \(.+\) would be deleted/)).toBeVisible({ timeout: 20_000 });
});
