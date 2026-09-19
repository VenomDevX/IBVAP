import { test, expect } from '@playwright/test';
import { login } from './helpers';

test.describe('per-page landmarks', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('dashboard renders summary + recent alerts', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('load');
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
  });

  test('cameras page renders the camera grid/table', async ({ page }) => {
    await page.goto('/cameras');
    await page.waitForLoadState('load');
    await expect(page.getByRole('link', { name: 'Cameras' })).toBeVisible();
  });

  test('map page renders', async ({ page }) => {
    await page.goto('/map');
    await page.waitForLoadState('load');
    await expect(page.getByRole('link', { name: 'Map View' })).toBeVisible();
  });

  test('zones page renders', async ({ page }) => {
    await page.goto('/zones');
    await page.waitForLoadState('load');
    await expect(page.getByRole('link', { name: 'Zones' })).toBeVisible();
  });

  test('audit log page renders', async ({ page }) => {
    await page.goto('/audit');
    await page.waitForLoadState('load');
    await expect(page.getByRole('link', { name: 'Audit Log' })).toBeVisible();
  });

  test('settings page renders', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('load');
    await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
  });
});
