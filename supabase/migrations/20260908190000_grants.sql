-- =============================================================================
-- Table grants for the Data API roles.
-- The init migration created public.* but never GRANTed privileges to the
-- anon/authenticated/service_role roles (newer Supabase no longer auto-exposes
-- new tables), so `service_role` got "permission denied for table user_profiles"
-- even though the RLS policy allowed it. RLS is only checked *after* the
-- role has table-level privileges.
-- =============================================================================

grant usage on schema public to anon, authenticated, service_role;

-- service_role bypasses RLS but still needs the base grant
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;

-- authenticated: RLS policies decide the rows; the grant just unlocks the table
grant select, insert, update, delete on all tables in schema public to authenticated;

-- future tables
alter default privileges in schema public
  grant select, insert, update, delete on tables to service_role, authenticated;
alter default privileges in schema public
  grant usage, select on sequences to service_role;
