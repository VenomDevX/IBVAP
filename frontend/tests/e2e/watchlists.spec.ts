import { test, expect } from '@playwright/test';
import { login } from './helpers';

test.describe('watchlists', () => {
  test('add a plate, see it listed, then remove it', async ({ page }) => {
    const plate = `E2E${Date.now().toString().slice(-6)}`;
    const label = `E2E test plate ${plate}`;

    await login(page);
    await expect(page.getByRole('link', { name: 'Watchlists' })).toHaveAttribute('href', /\/watchlists\/?$/);
    await page.goto('/watchlists');
    await page.waitForLoadState('load');
    await expect(page.getByRole('heading', { name: 'Watchlists' })).toBeVisible();

    await page.getByRole('button', { name: 'Add plate' }).click({ timeout: 20_000 });
    const dialog = page.getByRole('dialog', { name: 'Add number plate' });
    await dialog.getByLabel('Number plate').fill(plate);
    await dialog.getByLabel('Description').fill(label);
    await dialog.getByLabel('List').selectOption('wanted');
    await dialog.getByRole('button', { name: 'Add plate' }).click();
    await expect(dialog).toBeHidden();

    const row = page.getByRole('row').filter({ hasText: label });
    await expect(row).toBeVisible();
    await expect(row.getByText('Wanted')).toBeVisible();

    // A duplicate active plate is refused with a readable message.
    await page.getByRole('button', { name: 'Add plate' }).click();
    await dialog.getByLabel('Number plate').fill(plate.toLowerCase());
    await dialog.getByLabel('Description').fill('duplicate');
    await dialog.getByRole('button', { name: 'Add plate' }).click();
    await expect(dialog.getByText(/already on an active watchlist/i)).toBeVisible();
    await dialog.getByRole('button', { name: 'Cancel' }).click();

    await row.getByRole('button', { name: 'Remove' }).click();
    const confirm = page.getByRole('dialog', { name: 'Remove from watchlist?' });
    await confirm.getByRole('button', { name: 'Remove' }).click();
    await expect(row).toBeHidden();
  });

  test('faces tab renders', async ({ page }) => {
    await login(page);
    await page.goto('/watchlists');
    await page.getByRole('radio', { name: 'Faces' }).or(page.getByRole('button', { name: 'Faces' })).first().click();
    // The button appears once the user's role has loaded.
    await expect(page.getByRole('button', { name: 'Add face' })).toBeVisible({ timeout: 20_000 });
  });
});
