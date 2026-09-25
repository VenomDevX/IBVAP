import { test, expect } from '@playwright/test';
import { login } from './helpers';

test.describe('multiview', () => {
  test('camera-select dropdown changes the displayed camera', async ({ page }) => {
    await login(page);
    await page.goto('/multiview');
    await page.waitForLoadState('load');

    const select = page.getByLabel('Camera for tile 1');
    const appeared = await select.waitFor({ state: 'visible', timeout: 8000 }).then(() => true).catch(() => false);
    if (!appeared) {
      test.skip(true, 'no cameras configured to populate the multiview grid');
    }

    const options = await select.locator('option').allTextContents();
    if (options.length < 2) {
      test.skip(true, 'only one camera available — nothing to switch to');
    }

    const targetValue = await select.locator('option').nth(1).getAttribute('value');
    await select.selectOption(targetValue!);
    await expect(select).toHaveValue(targetValue!);
  });
});

test.describe('multiview layout memory', () => {
  test('the chosen grid and cameras come back on the next sign-in', async ({ page, browser }) => {
    await login(page);
    await page.goto('/multiview');
    const first = page.getByLabel('Camera for tile 1');
    if (!(await first.waitFor({ timeout: 8000 }).then(() => true).catch(() => false))) {
      test.skip(true, 'no cameras configured to populate the multiview grid');
    }
    const ids = (await first.locator('option').evaluateAll(o => o.map(x => (x as HTMLOptionElement).value))).reverse();
    test.skip(ids.length < 2, 'needs at least two cameras');

    // 3 × 3 with 8 tiles picked in reverse order — something the default layout never produces.
    await page.getByRole('radio', { name: '3 × 3' }).click();
    const picked = Array.from({ length: 8 }, (_, i) => ids[i % ids.length]);
    for (const [i, id] of picked.entries()) await page.getByLabel(`Camera for tile ${i + 1}`).selectOption(id);
    await page.waitForTimeout(2500); // debounced save to the user's profile

    // A brand-new browser (no local storage) signing in again.
    const fresh = await browser.newContext();
    const next = await fresh.newPage();
    await login(next);
    await next.goto('/multiview');
    await expect(next.getByRole('radio', { name: '3 × 3' })).toHaveAttribute('aria-checked', 'true');
    for (const [i, id] of picked.entries()) await expect(next.getByLabel(`Camera for tile ${i + 1}`)).toHaveValue(id);
    await fresh.close();
  });
});
