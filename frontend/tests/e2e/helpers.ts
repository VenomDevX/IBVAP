import type { Page } from '@playwright/test';

/**
 * Seeded local dev account (backend/scripts/seed_users.py --defaults against
 * the local Supabase stack; password from backend/.env IBVAP_ADMIN_PASSWORD).
 * Validation-only specs (login-signup.spec.ts) don't need this — only specs
 * that exercise an authenticated route do.
 */
export const ADMIN_EMAIL = 'admin@ibvap.local';
export const ADMIN_PASSWORD = 'admin123';

export async function login(page: Page, email = ADMIN_EMAIL, password = ADMIN_PASSWORD) {
  await page.goto('/login');
  await page.getByPlaceholder('operator@ibvap.gov').fill(email);
  await page.getByPlaceholder('Enter password').fill(password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL('/', { timeout: 15_000 });
}
