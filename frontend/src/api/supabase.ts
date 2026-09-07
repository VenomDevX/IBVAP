import { createClient } from '@supabase/supabase-js';

const supabaseUrl = 'http://127.0.0.1:54321';
const supabaseAnonKey = '***REDACTED_SUPABASE_ANON_KEY***';

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
