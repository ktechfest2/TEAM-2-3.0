# Data model

The tables below are created by `backend/alembic/versions/0001_initial_schema.py` from the SQLAlchemy models. `0002_append_only_history.py` adds append-only triggers and row-level security to the evidence history tables. `0003_result_aggregation.py` adds the derived result tables. How they are computed is in [results-aggregation.md](results-aggregation.md).

Identity comes from Supabase Auth. `users.id` is the auth user id. The `users` table has no password column.

| Table | Purpose |
| --- | --- |
| `users` | Profile mirror: email, display name, active flag. |
| `role_assignments` | Durable grant of one role to one user. |
| `elections` | An election and its date. |
| `states`, `lgas`, `wards` | INEC reference geography. Codes are unique within their parent. `states.iso_code` (ISO 3166-2, unique) joins states to map boundaries. |
| `polling_units` | Polling unit code, name, optional PostGIS point, optional registered-voter count, address description, `status`, and source provenance (`source_name`, `source_reference`, `source_updated_at`). |
| `polling_unit_notices` | Staff-recorded relocation or closure notice: source, reference, new location, effective date, received time, verification status, recorder. |
| `relocation_reports` | Crowd reports that a unit may have moved. Kept apart from notices and never promoted automatically. |
| `election_updates` | Published updates: category, source, reference, verification status, optional polling unit, publisher. |
| `evidence_submissions` | One result-sheet capture: election, polling unit, submitter, idempotency key, original SHA-256 and perceptual hash, capture and receipt times, and the workflow `status`, which only server-side transitions change. |
| `evidence_images` | Stored image objects: the untouched original and processed derivatives, each with its hash. Append-only. |
| `ocr_extractions` | One OCR run: provider and version, template, mean confidence, error. Append-only. |
| `extracted_result_fields` | One version of one field: value, origin (`ocr` or `human`), confidence, bounding box, review reasons, editor and reason. A correction adds a version. Append-only. |
| `result_validations` | Deterministic validation report and the canonical result fingerprint. Append-only. |
| `submission_comparisons` | Comparison against other submissions for the same polling unit. Append-only. |
| `anomaly_alerts` | VoteTrace AI alerts with explanation, model name and version. Append-only. |
| `evidence_reviews` | Reviewer actions (start, approve, reject, request correction) tied to a result fingerprint. Append-only. |
| `extracted_result_records` | Counts recorded for one polling unit. `vote_counts` is JSON whose shape is defined later. No status column. |
| `verification_records` | Append-only review decision. The current status is the latest row for a result. |
| `polling_unit_results` | Derived, server-written aggregation state: one row per (election, polling unit), unique. Status (`not_reporting`, `pending`, `reported`, `conflict`, `verified`), submission, accepted and independent counts, reported and verified fingerprints, source and contributing submission ids, timestamps and a revision. Checks tie status to fingerprints. |
| `polling_unit_result_metrics` | The figures behind a row: `(result_id, stream, metric)` unique, `stream` is `reported` or `verified`, value ≥ 0. Denormalised `state_id`, `lga_id`, `ward_id` make level totals indexed `SUM … GROUP BY` queries. |
| `audit_events` | Append-only action log. No update column. |
| `incident_reports` | A report received by the server: public `reference`, category (as reported and as corrected), cleaned description, location ids, time, optional coordinates, status, severity, triage JSON, possible duplicate, content fingerprint, nullable `reporter_user_id` (null when anonymous), `identity_protected`, client idempotency key, and the reviewer-approved public summary. No IP, device or phone fields. |
| `incident_attachments` | A private photo re-encoded without metadata: storage path, SHA-256, size and dimensions. Append-only. |
| `incident_reviews` | Every reviewer action: previous and new status, reason, evidence references, category and severity corrections, and publication. Append-only. |
| `sms_messages` | Inbound SMS log: provider, provider message id (unique per provider), hashed sender, parsed command, outcome and reply parts. Append-only. No phone number in clear. |

## Roles

`observer`, `party_agent`, `reviewer`, `auditor`, `election_admin`, `system_admin`.

The same names are used in `frontend/src/features/auth/roles.ts`, in the `app_role` Postgres enum, and in the `app_metadata.roles` array of a Supabase access token. A signed token is the request-time authority. `role_assignments` is the record an administrator will later sync into that claim. This foundation does not perform that sync.

`reviewer`, `auditor`, `election_admin` and `system_admin` may open the admin console. Individual sections restrict the set further. `observer` and `party_agent` are field roles: they can submit evidence and see their own submissions, but cannot open the console.

## Evidence workflow status

`received`, `processing`, `extracted`, `arithmetic_validated`, `cross_checked`, `flagged_for_review`, `under_human_review`, `reviewed`, `verified`, `rejected`. Transitions and the approval rule are described in [evidence-engine.md](evidence-engine.md). These are VoteTrace statuses, not INEC declarations.

## Verification status

`pending`, `under_review`, `verified`, `discrepancy`, `rejected`.

Status lives only on `verification_records`. Changing a decision inserts a new row. There is no API that accepts a status from the browser.

## Incident status

`received`, `screening`, `under_review`, `corroboration_required`, `verified`, `unverified`, `inconclusive`, `rejected`, `resolved`. Only reviewers change it, and the public sees grouped bands. See [incidents-and-channels.md](incidents-and-channels.md).

## Polling-unit status and update verification

Polling-unit `status`: `active`, `relocation_reported`, `officially_relocated`, `temporarily_unavailable`, `pending_verification` (default).

Notice verification: `officially_confirmed`, `awaiting_confirmation`, `withdrawn`. A notice counts as official only when it is `officially_confirmed` and names a source.

Update verification: `officially_confirmed`, `independently_verified`, `reported_unverified`. Update categories: `polling_unit_relocation`, `election_schedule`, `voting_delay`, `official_announcement`, `security_notice`, `general_information`.

## Counts

Nullable integer counts on `extracted_result_records` and `polling_units.registered_voters` must be null or zero or greater. The meaning of each count, and the keys inside `vote_counts`, belong to the later result workflow.

## Evidence storage

`storage_bucket` and `storage_path` identify an object in a private bucket. The path is not a public URL. Originals are stored under a content-addressed key, and their SHA-256 is re-checked on every read.

## Audit

`audit_events.details` is JSON. Writers must not put tokens, passwords or raw evidence bytes in it. `request_id` ties an event to the API log line.
