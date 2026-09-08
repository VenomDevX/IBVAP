import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

if (!supabaseUrl || !supabaseAnonKey) {
  // Visible, non-fatal: show a banner but let the app (and its error UI) still render.
  const msg =
    'VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not set. ' +
    'Run `npx supabase start` and check frontend/.env, then restart `npm run dev`.';
  console.error(msg);
  window.addEventListener('DOMContentLoaded', () => {
    const bar = document.createElement('div');
    bar.textContent = msg;
    bar.style.cssText =
      'position:fixed;top:0;left:0;right:0;z-index:99999;background:#b00;color:#fff;' +
      'font:13px/1.4 monospace;padding:8px 12px';
    document.body.prepend(bar);
  });
}

// Fall back to the standard local dev endpoint so the client still constructs.
export const supabase = createClient(
  supabaseUrl || 'http://127.0.0.1:54321',
  supabaseAnonKey || 'missing-anon-key',
);
