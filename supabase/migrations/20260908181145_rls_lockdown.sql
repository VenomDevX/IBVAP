-- =============================================================================
-- RLS lockdown
-- The init migration granted every authenticated user SELECT on every table
-- (USING (true)), including user_profiles. That is fixed here.
--
-- Datastore decision (TRD §17): SQLite is the runtime source of truth; Supabase
-- is used ONLY for auth + user_profiles. The mirrored operational tables are no
-- longer read by anyone, so they are locked to service_role only and dropped
-- from the realtime publication.
-- =============================================================================

-- ---- helper: is the current user an admin? (SECURITY DEFINER avoids RLS recursion) ----
create or replace function public.is_admin()
returns boolean
language sql
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.user_profiles
    where id = auth.uid() and role = 'admin'
  );
$$;

-- ---- user_profiles: self-read only; admins read all; nobody self-updates role ----
drop policy if exists "Allow authenticated read access" on public.user_profiles;
drop policy if exists "Allow service role full access" on public.user_profiles;

create policy "own profile read"      on public.user_profiles
  for select to authenticated using (id = auth.uid() or public.is_admin());
create policy "admin profile write"   on public.user_profiles
  for all to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "service role profiles" on public.user_profiles
  for all to service_role using (true) with check (true);

-- ---- operational tables: no direct client access; the API (service_role) is the only reader ----
do $$
declare t text;
begin
  foreach t in array array['cameras','tracks','events','alerts','zones'] loop
    execute format('drop policy if exists "Allow authenticated read access" on public.%I', t);
    execute format('drop policy if exists "Allow service role full access" on public.%I', t);
    execute format('create policy "service role only" on public.%I for all to service_role using (true) with check (true)', t);
  end loop;
end $$;

-- ---- stop broadcasting the alert/event firehose to every authenticated socket ----
alter publication supabase_realtime drop table public.alerts;
alter publication supabase_realtime drop table public.events;

-- ---- create a user_profiles row automatically for every new auth user ----
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.user_profiles (id, role, full_name, allowed_areas)
  values (new.id, 'operator', coalesce(new.raw_user_meta_data->>'full_name', ''), '[]'::jsonb)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
