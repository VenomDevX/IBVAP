import { createHmac } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { Page } from '@playwright/test';

/**
 * Seeded local dev account (backend/scripts/seed_users.py --defaults against
 * the local Supabase stack; password from backend/.env IBVAP_ADMIN_PASSWORD).
 * Validation-only specs (login-signup.spec.ts) don't need this — only specs
 * that exercise an authenticated route do.
 */
export const ADMIN_EMAIL = 'admin@ibvap.local';
export const ADMIN_PASSWORD = 'admin123';

// The TOTP secret shown at the account's first enrollment, kept for later runs (gitignored).
// If the account was enrolled by hand, reset it first: POST /api/auth/users/{id}/reset-mfa.
const secretFile = (email: string) => join(import.meta.dirname, `.totp-${email.replace(/\W/g, '_')}`);

/** RFC 6238 code (SHA-1, 30 s, 6 digits) — what authenticator apps show. */
export function totp(base32Secret: string, now = Date.now()) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits = '';
  for (const c of base32Secret.replace(/=+$/, '').toUpperCase()) bits += alphabet.indexOf(c).toString(2).padStart(5, '0');
  const key = Buffer.from(bits.match(/.{8}/g)!.map(b => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(now / 30_000)));
  const hmac = createHmac('sha1', key).update(counter).digest();
  const offset = hmac[hmac.length - 1] & 0xf;
  return String((hmac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, '0');
}

export async function login(page: Page, email = ADMIN_EMAIL, password = ADMIN_PASSWORD) {
  await page.goto('/login');
  await page.getByPlaceholder('operator@ibvap.gov').fill(email);
  await page.getByPlaceholder('Enter password').fill(password);
  await page.getByRole('button', { name: /sign in/i }).click();

  const heading = page.getByRole('heading', { name: /two-step verification|verification code/i });
  await heading.waitFor({ timeout: 15_000 });
  if (/set up/i.test(await heading.innerText())) {
    writeFileSync(secretFile(email), (await page.locator('code').innerText()).trim());
  } else if (!existsSync(secretFile(email))) {
    throw new Error(`${email} is already enrolled with an unknown authenticator; reset its MFA first.`);
  }
  await page.getByPlaceholder('123456').fill(totp(readFileSync(secretFile(email), 'utf8')));
  await page.getByRole('button', { name: /verify/i }).click();
  await page.waitForURL('/', { timeout: 15_000 });
}

// Self-check against the RFC 6238 SHA-1 test vector ("12345678901234567890", T=59s → 287082).
if (totp('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ', 59_000) !== '287082') throw new Error('totp() is broken');
