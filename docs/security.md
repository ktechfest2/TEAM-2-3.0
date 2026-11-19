# Security

VoteTrace treats the browser as an untrusted client. Hiding a button is not access control. The API and the database are.

## Secrets

| Value | Where it may live |
| --- | --- |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | Frontend. Public by design. Row Level Security is what protects data. |
| `VITE_API_BASE_URL` | Frontend. Public. |
| `DATABASE_URL` | API only. |
| `AUTH_JWT_SECRET` | API only. Signs VoteTrace session tokens. |
| `SUPABASE_JWT_SECRET` | API only, optional. Verifies Supabase access tokens. |
| `CHANNEL_CALLBACK_TOKEN`, `AFRICASTALKING_API_KEY` | API only. Gateway callback token and outbound SMS credential. |
| `SUPABASE_SERVICE_ROLE_KEY` | API only. Reserved for private-storage signing. The current API does not read it. |

The frontend env parser accepts only `VITE_` variables. There is no frontend setting for the service-role key. Production boot fails when the database URL, JWT secret or CORS list is missing. CORS rejects a wildcard origin. Cookies are not used for API auth, and credentialed CORS is off.

Logs and validation errors are scrubbed. A failed database check does not log the exception, because the message can include the connection string. Settings use `SecretStr`, so a repr does not print the JWT secret or the service-role key.

## Authentication and roles

Protected routes require `Authorization: Bearer`. Two token types are accepted.

Built-in accounts (`POST /api/v1/auth/login`): passwords are hashed with scrypt (N=2^15, r=8, p=1) in `user_credentials`. Sign-in is rate limited per client, locks an account after `AUTH_MAX_FAILED_ATTEMPTS` failures, and returns the same error for an unknown email and a wrong password. Tokens are HS256, issuer `verivote`, signed with `AUTH_JWT_SECRET`. On every request the API reloads the account, so disabling an account, changing its roles, or resetting its password takes effect immediately; a reset or password change also invalidates every existing session through a token version. Accounts with a temporary password hold no roles until they change it. Only `system_admin` manages accounts, an administrator cannot demote or disable themselves, and the last active administrator cannot be removed. Every account action is written to the hash-chained audit log.

Supabase tokens, when `SUPABASE_JWT_SECRET` is set: the token must be an HS256 Supabase access token for the `authenticated` audience, signed with `SUPABASE_JWT_SECRET`, and it must include `exp` and `sub`. Tokens signed with the newer Supabase ECC signing keys are rejected. Use the project's legacy JWT secret until that verification is added.

Roles are read only from `app_metadata.roles`. That claim is written with the service role, not by the user. `user_metadata` and the top-level `role` claim (which Supabase sets to `authenticated`) are ignored. Unknown role names are ignored. A missing secret produces 503 `auth_not_configured` rather than a pass.

`GET /api/v1/auth/me` returns the principal. `GET /api/v1/admin/session` requires a console role. Neither route returns operational data.

## Public directory routes

`/api/v1/locations/*`, `/api/v1/polling-units` and `/api/v1/updates` are anonymous and read-only. They accept only `GET`. `PUT`, `PATCH` and `DELETE` return 405. Responses contain no user data. Relocation reports are returned only as a count and the first and last report times, never with reporter identity.

Every query parameter is validated. IDs must be UUIDs. The search text must be 2 to 80 characters of letters, digits, spaces and place-name punctuation. Codes must match `[A-Za-z0-9-]{2,24}`. Enums are checked, `page_size` is at most 50, and a reversed date range is rejected. Invalid input returns 422 without echoing the value.

The browser sends these requests without an `Authorization` header and with `credentials: 'omit'`. Responses are saved in IndexedDB for offline viewing. Authenticated responses are never cached there.

## Rate limiting

`/api/v1/*` is limited per client IP to `RATE_LIMIT_PER_MINUTE` (default 120) with a sliding window. Excess requests get 429 `rate_limited`, a `Retry-After` header and CORS headers, so the browser can read the error. The limiter is in-process: each API instance counts separately. A deployment must also rate-limit at the proxy or CDN. `X-Forwarded-For` is honoured only when `TRUST_PROXY_HEADERS=true`. Set that only behind a proxy that overwrites the header.

## Transport

Production responses include `Strict-Transport-Security: max-age=63072000; includeSubDomains`. Terminate TLS at the proxy and redirect HTTP to HTTPS there. Every response is `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`.

## Publishing official updates

`POST /api/v1/admin/updates` requires a valid token with `election_admin` or `system_admin`. Other roles get 403, and anonymous requests get 401. The body cannot set an id, `published_at`, `published_by` or `is_demo` (`extra="forbid"`). The server sets those. An `officially_confirmed` update must carry a reference or an HTTPS source URL. With the database directory the update is stored and audited. With the demo directory, the request is authorized and validated, then refused with 503 `persistence_unavailable`. Register imports and election changes (`/api/v1/admin/register/import`, `/api/v1/admin/elections`) need the same roles and are written to the audit log.

## Evidence routes

The other write routes are under `/api/v1/evidence` and all require authentication. A test asserts that every mutating route in the OpenAPI schema is under `/api/v1/admin/` or `/api/v1/evidence`, and that each refuses anonymous requests with 401.

- Upload: `observer`, `party_agent`, `reviewer`, `election_admin`, `system_admin`. It requires an `Idempotency-Key`, checks the file by content rather than extension, limits size and dimensions, refuses decompression bombs, and is rate limited per user.
- Submitters see only their own submissions. Other users' submissions return 404, not 403. Public result viewers never see submitter identities.
- Comparison, anomaly reports and review history are staff only (`reviewer`, `election_admin`, `system_admin`). Audit actor IDs are hidden from non-staff.
- `POST /{id}/review` requires `reviewer`, `election_admin` or `system_admin`. A reviewer cannot review their own submission.
- Clients never send a status. Statuses change only through server-side transitions in `app/evidence/workflow.py`. `verified` requires distinct approvals on the same result fingerprint. VoteTrace AI cannot change a status or a value.
- Images are served by the API with `Cache-Control: private, no-store`. Storage URLs are never returned to clients.

The pipeline, its limits and the tamper-evidence caveat are described in [evidence-engine.md](evidence-engine.md).

## Result aggregation routes

- `/api/v1/analytics/*` is public and read-only (`GET` only). Every parameter is typed and validated. The global per-client rate limit applies, and the event stream is capped at 500 listeners.
- Totals are derived on the server from evidence records. No route accepts totals, statuses or aggregation rows from a client. Aggregation rows are written only by the session hooks inside the transaction that changed the evidence, and every change appends a hash-chained audit event.
- Public polling-unit reports list submission ids, workflow status, receipt time, figures fingerprint and whether each submission counted. They never include the submitter, images, storage paths or reviewer identities. Staff links into evidence go through the authenticated evidence API.
- `POST /api/v1/admin/analytics/rebuild` is limited to `system_admin` and `election_admin`.
- Events on `/analytics/updates` carry identifiers only. Clients refetch figures from the API.

## Incident routes

- `POST /api/v1/incidents` is open to the public, with a required `Idempotency-Key` and a per-address limit (`INCIDENT_SUBMISSIONS_PER_HOUR`). The limit is counted in memory. The address is never written to the database.
- Reports store no IP address, device identifier or phone number. Photos are re-encoded to drop EXIF and GPS data. Phone numbers and e-mail addresses in descriptions are masked before storage.
- `GET /incidents`, `/incidents/stats`, `/incidents/{id}` and attachments require `reviewer`, `auditor`, `election_admin` or `system_admin`. `POST /incidents/{id}/review` requires `reviewer` or `election_admin`. A reviewer can never review a report submitted from their own account.
- `GET /incidents/track/{reference}` and `GET /public/incidents` return the public stage and reviewer-approved summaries only. No public schema includes descriptions, attachments, reporter details or review reasons.
- Run Uvicorn with `--no-access-log`, and make the proxy or CDN drop or truncate client IPs on incident routes. Otherwise the server's own logs undermine the privacy statement on the form.

## USSD and SMS routes

- USSD and SMS are read-only. `InfoService` has no write methods. The only table they write is `sms_messages`, which records hashed senders, the parsed command and the reply for rate limiting and duplicate protection.
- Gateway callbacks must be signed (`X-VoteTrace-Signature: sha256=<HMAC-SHA256 of the raw body>`) with `USSD_WEBHOOK_SECRET` or `SMS_WEBHOOK_SECRET`, checked in constant time. Unsigned simulator calls are accepted only while `CHANNEL_SIMULATOR_ENABLED` is on, and production refuses to start with it on.
- Phone numbers are hashed with `CHANNEL_HASH_SECRET` and never stored in clear.
- No provider credentials exist in the code. See [incidents-and-channels.md](incidents-and-channels.md).

## What clients cannot do

A client cannot:

- set or change a verification status
- write, correct or submit aggregated results or national totals
- overwrite OCR output or earlier field versions (corrections add versions)
- read or write the evidence bucket directly, or receive a storage URL
- set an incident's status, severity or publication, or verify their own report
- change any record through USSD or SMS

Incident drafts wait in IndexedDB until the server confirms receipt. The description, photo and coordinates are then removed from the device, and only the reference and a short label remain. Evidence drafts follow the same rule for image data. The service worker does not cache API responses.

## Database policies

Apply the following in the Supabase SQL editor after `alembic upgrade head`. The application does not run it automatically.

The API connects with `DATABASE_URL`. Use a dedicated role for that URL. Do not point it at the `anon` role. The service-role key bypasses RLS and stays on the server.

```sql
-- Public reference data is readable. Nothing here is writable by clients.
alter table public.states enable row level security;
alter table public.lgas enable row level security;
alter table public.wards enable row level security;
alter table public.polling_units enable row level security;
alter table public.elections enable row level security;

create policy states_read on public.states
  for select to anon, authenticated using (true);
create policy lgas_read on public.lgas
  for select to anon, authenticated using (true);
create policy wards_read on public.wards
  for select to anon, authenticated using (true);
create policy polling_units_read on public.polling_units
  for select to anon, authenticated using (true);
create policy elections_read on public.elections
  for select to anon, authenticated using (true);

-- Published notices and updates are public. Writes go through the API only.
alter table public.polling_unit_notices enable row level security;
alter table public.election_updates enable row level security;
create policy polling_unit_notices_read on public.polling_unit_notices
  for select to anon, authenticated using (true);
create policy election_updates_read on public.election_updates
  for select to anon, authenticated using (true);

-- Crowd reports carry reporter ids: no client access at all.
alter table public.relocation_reports enable row level security;

-- Sensitive tables: RLS on, and no policy for anon or authenticated.
-- Default deny covers select, insert, update and delete.
alter table public.users enable row level security;
alter table public.role_assignments enable row level security;
alter table public.evidence_submissions enable row level security;
alter table public.extracted_result_records enable row level security;
alter table public.verification_records enable row level security;
alter table public.audit_events enable row level security;
alter table public.incident_reports enable row level security;
-- Derived results: served only through the API (migration 0003 also revokes grants).
alter table public.polling_unit_results enable row level security;
alter table public.polling_unit_result_metrics enable row level security;

insert into storage.buckets (id, name, public)
values ('evidence', 'evidence', false)
on conflict (id) do update set public = false;
```

No storage policy is created for `evidence`. Without one, the anon and authenticated keys cannot read or write objects. The API writes and reads objects with the service-role key on the server, and proxies images after checking access. Do not add a public bucket policy.

Migration `0002` also enables RLS on the evidence history tables, revokes `anon` and `authenticated` access to them, and adds triggers that refuse `UPDATE`, `DELETE` and `TRUNCATE`. A database owner can still disable those triggers, which is why the audit trail is hash-chained: tampering is detectable, not prevented.

`verification_records` is not publicly selectable: the row includes the reviewer's justification. Public status, when it is published, should come from an API response or a view that exposes only the status.

Incident submission goes through the API, not through Supabase. Migration `0004` enables RLS on `incident_reports`, `incident_attachments`, `incident_reviews` and `sms_messages`. It revokes all `anon` and `authenticated` privileges on them, and makes the last three refuse `UPDATE` and `DELETE`. Do not add a client insert policy.

There is intentionally no update or delete policy on `verification_records`, `extracted_result_records` or `audit_events`. There is also no insert, update or delete policy on `polling_units`, `polling_unit_notices` or `election_updates`, so clients cannot modify polling-unit records or publish notices directly through Supabase.
