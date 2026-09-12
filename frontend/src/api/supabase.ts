import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if ((!supabaseUrl || !supabaseAnonKey) && typeof window !== 'undefined') {
  const msg =
    'NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY are not set. ' +
    'Run `npx supabase start`, check frontend/.env, then restart `npm run dev`.';
  console.error(msg);
  const show = () => {
    if (document.getElementById('supabase-env-banner')) return;
    const bar = document.createElement('div');
    bar.id = 'supabase-env-banner';
    bar.textContent = msg;
    bar.style.cssText =
      'position:fixed;top:0;left:0;right:0;z-index:9999;background:#b00;color:#fff;' +
      'font:13px/1.4 monospace;padding:8px 12px';
    document.body.prepend(bar);
  };
  if (document.body) show();
  else window.addEventListener('DOMContentLoaded', show);
}

export const supabase = createClient(
  supabaseUrl || 'http://127.0.0.1:54321',
  supabaseAnonKey || 'missing-anon-key',
);
