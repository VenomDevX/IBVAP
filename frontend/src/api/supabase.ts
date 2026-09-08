import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  // Loud, visible failure — a silent dummy key hides a broken build.
  const msg = 'VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not set at build time. Auth is disabled.';
  console.error(msg);
  document.body.innerHTML =
    '<pre style="padding:2rem;font:14px monospace;color:#b00">' + msg + '</pre>';
  throw new Error(msg);
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
