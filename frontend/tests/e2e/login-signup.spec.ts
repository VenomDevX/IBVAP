import { test, expect } from '@playwright/test';
import { ADMIN_EMAIL } from './helpers';

test.describe('login validation', () => {
  test('empty submit is blocked by required fields (stays on /login)', async ({ page }) => {
    await page.goto('/login');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/login/);
  });

  test('wrong password shows an error and does not navigate away', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('operator@ibvap.gov').fill(ADMIN_EMAIL);
    await page.getByPlaceholder('Enter password').fill('definitely-wrong-password');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page.getByText(/incorrect email or password/i)).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/login/);
  });
});

test.describe('signup validation', () => {
  test('empty submit is blocked by required fields (stays on /signup)', async ({ page }) => {
    await page.goto('/signup');
    const disabledNotice = page.getByText(/self-service registration is disabled/i);
    if (await disabledNotice.count() > 0) {
      test.skip(true, 'signup disabled in this build (production mode)');
    }
    await page.getByRole('button', { name: /sign up/i }).click();
    await expect(page).toHaveURL(/\/signup/);
  });
});
