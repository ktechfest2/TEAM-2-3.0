-- SUPERSEDED: do not apply. This draft targets an earlier schema (profiles, user_roles).
-- The current statements are in docs/security.md under "Database policies".
--
-- VeriVote Nigeria - DRAFT Row Level Security policies.
-- Apply AFTER the first Alembic migration. Review against the generated schema before use.
--
-- Model: the FastAPI service role (table owner) performs all writes. The Supabase
-- `anon` and `authenticated` roles (used by PostgREST/GraphQL with the public anon key)
-- get read access to reference data only. Everything else is denied by default.

-- ---------------------------------------------------------------------------
-- 1. Enable RLS everywhere (no policy = no access for anon/authenticated).
-- ---------------------------------------------------------------------------
alter table public.profiles                 enable row level security;
alter table public.roles                    enable row level security;
alter table public.user_roles               enable row level security;
alter table public.elections                enable row level security;
alter table public.states                   enable row level security;
alter table public.lgas                     enable row level security;
alter table public.wards                    enable row level security;
alter table public.polling_units            enable row level security;
alter table public.evidence_submissions     enable row level security;
alter table public.extracted_result_records enable row level security;
alter table public.verification_records     enable row level security;
alter table public.audit_events             enable row level security;
alter table public.incident_reports         enable row level security;

-- ---------------------------------------------------------------------------
-- 2. Strip default write privileges from the public API roles.
-- ---------------------------------------------------------------------------
revoke insert, update, delete, truncate on all tables in schema public from anon, authenticated;
alter default privileges in schema public revoke insert, update, delete, truncate on tables from anon, authenticated;

-- Sensitive tables: no direct API access at all.
revoke all on public.evidence_submissions,
              public.extracted_result_records,
              public.verification_records,
              public.incident_reports,
              public.audit_events,
              public.user_roles
  from anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. Helper: role check from the verified JWT (app_metadata is not user-editable).
-- ---------------------------------------------------------------------------
create or replace function public.has_role(required text)
returns boolean
language sql
stable
set search_path = ''
as $$
  select coalesce(
    (auth.jwt() -> 'app_metadata' -> 'roles') ? required,
    false
  );
$$;

-- ---------------------------------------------------------------------------
-- 4. Read-only reference data.
-- ---------------------------------------------------------------------------
create policy "reference data is public" on public.states        for select to anon, authenticated using (true);
create policy "reference data is public" on public.lgas          for select to anon, authenticated using (true);
create policy "reference data is public" on public.wards         for select to anon, authenticated using (true);
create policy "reference data is public" on public.polling_units for select to anon, authenticated using (true);
create policy "reference data is public" on public.elections     for select to anon, authenticated using (true);
create policy "role catalogue is readable" on public.roles       for select to authenticated using (true);

-- Users may read (not modify) their own profile.
create policy "read own profile" on public.profiles
  for select to authenticated
  using ((select auth.uid()) = id);

-- ---------------------------------------------------------------------------
-- 5. Audit log is append-only, even for the table owner.
-- ---------------------------------------------------------------------------
create or replace function public.block_audit_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'audit_events is append-only';
end;
$$;

create trigger audit_events_append_only
  before update or delete on public.audit_events
  for each row execute function public.block_audit_mutation();

create trigger audit_events_no_truncate
  before truncate on public.audit_events
  for each statement execute function public.block_audit_mutation();

-- ---------------------------------------------------------------------------
-- 6. Verification history is append-only.
-- ---------------------------------------------------------------------------
create trigger verification_records_append_only
  before update or delete on public.verification_records
  for each row execute function public.block_audit_mutation();

-- ---------------------------------------------------------------------------
-- 7. Storage: the evidence bucket is private with no client policies.
--    Create it in the dashboard with "Public bucket" OFF, or:
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('evidence', 'evidence', false, 15728640, array['image/jpeg', 'image/png', 'image/webp', 'application/pdf'])
on conflict (id) do update set public = false;

-- Intentionally NO policies on storage.objects for bucket 'evidence'.
-- All uploads and downloads use short-lived signed URLs issued by the API.
