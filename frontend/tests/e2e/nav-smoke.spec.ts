import { test, expect } from '@playwright/test';
import { login } from './helpers';

// All 12 app routes (see frontend/app/ — the (app) route group plus login/signup).
const AUTHED_ROUTES = ['/', '/cameras', '/multiview', '/map', '/alerts', '/events', '/zones', '/audit', '/settings'];

test.describe('navigation smoke', () => {
  test('every sidebar route loads without console errors or failed requests', async ({ page }) => {
    const consoleErrors: string[] = [];
    const failedRequests: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(`${page.url()} :: ${msg.text()}`);
    });
    page.on('response', res => {
      if (res.status() >= 400 && !res.url().includes('/auth/v1/')) {
        failedRequests.push(`${res.status()} ${res.url()}`);
      }
    });

    await login(page);

    for (const route of AUTHED_ROUTES) {
      await page.goto(route);
      await page.waitForLoadState('load');
      // Every page should render the sidebar (confirms the shell + auth guard
      // didn't bounce us back to /login).
      await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    }

    expect(consoleErrors, `console errors:\n${consoleErrors.join('\n')}`).toEqual([]);
    expect(failedRequests, `failed requests:\n${failedRequests.join('\n')}`).toEqual([]);
  });

  test('an event detail page reachable from /events loads', async ({ page }) => {
    await login(page);
    await page.goto('/events');
    await page.waitForLoadState('load');
    const viewLink = page.getByRole('link', { name: 'View', exact: true }).first();
    const appeared = await viewLink.waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false);
    if (!appeared) {
      test.skip(true, 'no events in the demo dataset to open');
    }
    await viewLink.click();
    await expect(page).toHaveURL(/\/event\/?\?id=/);
    await expect(page.getByText(/Track #/)).toBeVisible();
  });
});
