-- Per-user two-step verification switch (admin-controlled from Settings → Users).
-- Only admins can write user_profiles (see rls_lockdown), so a user cannot exempt themselves.
alter table public.user_profiles
  add column if not exists mfa_required boolean not null default true;

-- RLS does not see the app's MFA gate, so a password-only (aal1) admin token could
-- otherwise edit profiles straight through the Data API. Admin rights now also need
-- the code step, unless that admin has been exempted.
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.user_profiles
    where id = auth.uid()
      and role = 'admin'
      and (coalesce(auth.jwt() ->> 'aal', '') = 'aal2' or not mfa_required)
  );
$$;
