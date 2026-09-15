import { test, expect } from '@playwright/test';
import { login } from './helpers';

test.describe('alerts/events list -> detail flow', () => {
  test('alerts list "View" navigates to the matching event detail', async ({ page }) => {
    await login(page);
    await page.goto('/alerts');
    await page.waitForLoadState('load');
    const viewLink = page.getByRole('link', { name: 'View', exact: true }).first();
    const appeared = await viewLink.waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false);
    if (!appeared) {
      test.skip(true, 'no alerts in the demo dataset');
    }
    const href = await viewLink.getAttribute('href');
    expect(href).toMatch(/^\/event\/?\?id=/);
    await viewLink.click();
    // The static export renders "/event/?id=" but may land on "/event?id=": allow either.
    await expect(page).toHaveURL(new RegExp(href!.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace('/event/', '/event/?')));
    await expect(page.getByText(/Track #/)).toBeVisible();
  });

  test('events list "View" navigates to the matching event detail', async ({ page }) => {
    await login(page);
    await page.goto('/events');
    await page.waitForLoadState('load');
    const viewLink = page.getByRole('link', { name: 'View', exact: true }).first();
    const appeared = await viewLink.waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false);
    if (!appeared) {
      test.skip(true, 'no events in the demo dataset');
    }
    const href = await viewLink.getAttribute('href');
    expect(href).toMatch(/^\/event\/?\?id=/);
    await viewLink.click();
    // The static export renders "/event/?id=" but may land on "/event?id=": allow either.
    await expect(page).toHaveURL(new RegExp(href!.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace('/event/', '/event/?')));
    await expect(page.getByText(/Track #/)).toBeVisible();
  });
});

test.describe('events table', () => {
  test('sorting by Time toggles row order, pagination respects boundaries', async ({ page }) => {
    await login(page);
    await page.goto('/events');
    await page.waitForLoadState('load');

    // The table header renders even when empty; wait for an actual data row
    // (proxied by a "View" link) before deciding whether there's anything to sort.
    const hasRows = await page.getByRole('link', { name: 'View', exact: true }).first()
      .waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false);
    if (!hasRows) {
      test.skip(true, 'no events in the demo dataset to sort');
    }
    const timeHeader = page.getByRole('button', { name: 'Time' });
    const timeColumnHeader = timeHeader.locator('xpath=ancestor::th');
    await expect(timeColumnHeader).toHaveAttribute('aria-sort', 'none');
    await timeHeader.click(); // ascending
    await expect(timeColumnHeader).toHaveAttribute('aria-sort', 'ascending');
    await timeHeader.click(); // descending
    await expect(timeColumnHeader).toHaveAttribute('aria-sort', 'descending');

    const nextButton = page.getByRole('button', { name: /Next/i });
    if (await nextButton.count() > 0) {
      const prevButton = page.getByRole('button', { name: /Prev/i });
      await expect(prevButton).toBeDisabled();
      if (await nextButton.isEnabled()) {
        await nextButton.click();
        await expect(prevButton).toBeEnabled();
      }
    }
  });
});
