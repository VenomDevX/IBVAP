import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect, type Page } from '@playwright/test';
import { login } from './helpers';

const OPERATOR = 'operator@ibvap.local';
// Same source seed_users.py uses, so the password is not copied into the test.
const operatorPassword = () =>
  readFileSync(join(import.meta.dirname, '../../../backend/.env'), 'utf8').match(/^IBVAP_OPERATOR_PASSWORD=(.*)$/m)?.[1].trim();

async function setOperatorMfa(page: Page, required: boolean) {
  await page.goto('/settings?tab=users');
  const toggle = page.getByRole('switch', { name: `Two-step verification for ${OPERATOR}` });
  await toggle.waitFor();
  if ((await toggle.isChecked()) !== required) {
    await toggle.click();
    await expect(toggle).toBeChecked({ checked: required });
  }
}

test('an admin can turn two-step verification off and on for one user', async ({ page, browser }) => {
  const password = operatorPassword();
  test.skip(!password, 'IBVAP_OPERATOR_PASSWORD is not set in backend/.env');
  await login(page);

  await setOperatorMfa(page, false);
  const operator = await (await browser.newContext()).newPage();
  try {
    // Password only: straight into the console, no code step.
    await operator.goto('/login');
    await operator.getByPlaceholder('operator@ibvap.gov').fill(OPERATOR);
    await operator.getByPlaceholder('Enter password').fill(password!);
    await operator.getByRole('button', { name: /sign in/i }).click();
    await operator.waitForURL('/', { timeout: 15_000 });
    await expect(operator.getByRole('heading', { name: /verification/i })).toHaveCount(0);

    // Back on: the next sign-in asks for the code again.
    await setOperatorMfa(page, true);
    const again = await (await browser.newContext()).newPage();
    await again.goto('/login');
    await again.getByPlaceholder('operator@ibvap.gov').fill(OPERATOR);
    await again.getByPlaceholder('Enter password').fill(password!);
    await again.getByRole('button', { name: /sign in/i }).click();
    await expect(again.getByRole('heading', { name: /two-step verification|verification code/i })).toBeVisible();
    await again.context().close();
  } finally {
    await setOperatorMfa(page, true); // never leave the account exempt
    await operator.context().close();
  }
});
