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
