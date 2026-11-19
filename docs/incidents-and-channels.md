# Incident reporting, USSD and SMS

This document covers the incident reporting workflow, the USSD and SMS channels, and how both reuse the existing backend. Every part is labelled with its status:

- **Implemented**: works end to end in this repository and is covered by tests.
- **Simulated**: works against a built-in simulator; no telecom network is involved.
- **Provider-dependent**: needs a contract, credentials or an allocated code from an outside provider.
- **Needs authoritative data**: correct only once the official INEC register and election mapping replace the demo directory.

## Status summary

| Area | Status |
| --- | --- |
| Incident submission (web, offline queue, idempotency) | Implemented |
| Reference number tracking | Implemented |
| Reviewer workflow, history and audit events | Implemented |
| Deterministic triage (duplicates, severity, missing information, similar reports) | Implemented |
| Admin incident dashboard and review queue | Implemented |
| Public incident summary | Implemented |
| USSD menu, pagination and timeout | Implemented, reached through the simulator |
| USSD gateway callback with HMAC signature | Implemented, but no provider is connected (provider-dependent) |
| USSD shortcode | Provider-dependent. None is allocated, and none is shown anywhere |
| SMS commands, rate limit, duplicate protection | Implemented, reached through the simulator |
| SMS outbound delivery | Provider-dependent. `SmsOutbound` is an interface with no provider implementation |
| Locations, polling-unit codes and results | Needs authoritative data. All current data is fictional demo data |

## Incident reporting

### Submission

`POST /api/v1/incidents` accepts `multipart/form-data` without an account. Fields:

| Field | Required | Notes |
| --- | --- | --- |
| `election_id`, `category`, `description`, `state_id`, `lga_id` | Yes | The description is 20 to 2,000 characters |
| `ward_id`, `polling_unit_id` | No | If only the polling unit is given, the ward is taken from the register |
| `occurred_at`, `time_is_approximate` | Yes | Between 90 days in the past and 10 minutes in the future |
| `latitude`, `longitude` | No | Both or neither, within valid latitude and longitude ranges |
| `photo` | No | JPEG, PNG or WebP, up to `INCIDENT_ATTACHMENT_MAX_BYTES` |
| `protect_identity` | No | Only meaningful when signed in |

The `Idempotency-Key` header is required. The offline queue uses the device draft id, so a retried upload returns the original receipt instead of creating a second report. A different payload with the same key is refused with 409.

Categories: violence, intimidation, vote buying, delayed officials, polling-unit relocation, voting disruption, accessibility, misinformation, other.

The response gives a reference such as `VV-0M9M-7A4E-8B0S`. Anyone with the reference can call `GET /api/v1/incidents/track/{reference}`. It returns only the public stage, the received and updated times, and a public summary if one has been approved.

### What is stored, and what the privacy claims rest on

The form shows only claims the backend enforces:

| Claim shown to the reporter | How it is enforced |
| --- | --- |
| No IP address, device identifier or phone number is stored with a report | The incident tables have no such columns. The per-address rate limit is counted in memory and never written |
| Location and camera details are removed from photos | Photos are re-encoded as JPEG with Pillow before storage, so EXIF, GPS and camera details are dropped. Tested in `test_incidents.py` |
| Phone numbers and e-mail addresses typed into the description are masked | `triage.clean_text` replaces them with `[number removed]` and `[email removed]` before the text is stored |
| Photos are private | They are stored through the private evidence storage. The attachment route needs a staff role, and no public schema includes attachments |
| Network and hosting providers can still see the connection | Stated plainly, because the app cannot prevent it |

Identity modes:

- **Anonymous** (signed out): `reporter_user_id` is null. The report cannot be linked to anyone, so the reference is the only way to follow it.
- **Account** (signed in): the user id is kept, so the system can stop that person reviewing their own report. Reviewers see "Submitted from an account".
- **Protected** (signed in, with `protect_identity`): the user id is kept for the self-review check only. Reviewers see "Identity protected", and no API returns the id.

Limits that operators must handle:

- Uvicorn's own access log records client IPs. Run it with `--no-access-log`, and configure the proxy or CDN to drop or truncate IPs on incident routes. The application's JSON log does not record IPs or incident text.
- If a reviewer submits an anonymous report and then reviews it, the system cannot detect that. Verifying needs at least one evidence reference, which reduces the risk without removing it.

### Review workflow

Only users with the `reviewer` or `election_admin` role may call `POST /api/v1/incidents/{id}/review`. Auditors and system admins can read the queue but cannot change it. A user can never review a report submitted from their own account, and the API returns 403.

Allowed transitions:

| From | To |
| --- | --- |
| RECEIVED | SCREENING, UNDER_REVIEW, REJECTED |
| SCREENING | UNDER_REVIEW, CORROBORATION_REQUIRED, UNVERIFIED, REJECTED |
| UNDER_REVIEW | CORROBORATION_REQUIRED, VERIFIED, UNVERIFIED, INCONCLUSIVE, REJECTED |
| CORROBORATION_REQUIRED | UNDER_REVIEW, VERIFIED, UNVERIFIED, INCONCLUSIVE |
| VERIFIED, UNVERIFIED, INCONCLUSIVE | RESOLVED (UNVERIFIED and INCONCLUSIVE may also return to UNDER_REVIEW) |
| REJECTED | SCREENING |
| RESOLVED | none |

Every review needs a reason of at least 10 characters. Moving to VERIFIED needs at least one evidence reference. Each review writes an append-only `incident_reviews` row and a hash-chained audit event. A review that changes nothing is refused.

### Public stages

The public never sees the internal status. Statuses are grouped into separate bands:

| Band | Statuses |
| --- | --- |
| Reported, awaiting review | RECEIVED |
| Under review | SCREENING, UNDER_REVIEW |
| Under review, with independent similar reports | CORROBORATION_REQUIRED |
| Verified by VoteTrace reviewers | VERIFIED, or RESOLVED after VERIFIED |
| Reviewed, inconclusive | INCONCLUSIVE, or RESOLVED after it |
| Reviewed, not substantiated | UNVERIFIED, REJECTED, or RESOLVED after either |

"Corroborated" means that other independent reports exist. It never means verified.

### Publishing

Only a verified incident can be published, and only with a reviewer-written public summary. The public summary page (`/incidents`) shows counts per band and the approved summaries. It never shows the original description, photos, reporter details or reviewer notes. Summaries are filtered for phone numbers and e-mail addresses. Reviewers are told not to name individuals or parties.

### Triage

`app/incidents/triage.py` is rule-based. It returns its reasons, so a reviewer can see why it produced each result. It suggests, and never decides.

- **Classification**: keyword matches per category. The reporter's category is kept until a reviewer changes it.
- **Severity**: a base level per category, raised by injury or weapon terms such as "injured", "gun", "machete" or "armed", and by urgency or scale terms such as "happening now" or "crowd". Severity sets queue order only.
- **Missing information**: lists absent optional fields such as polling unit, ward, exact time, coordinates and image.
- **Exact duplicates**: the same cleaned description for the same election, category and place within 24 hours is refused with 409, and the reporter is told it is already queued.
- **Near duplicates and similar reports**: word overlap with reports in the same area and category within `INCIDENT_SIMILARITY_WINDOW_HOURS`. Above a high threshold, the report is flagged `possible_duplicate_of` the earliest match. Otherwise, matches are listed as similar or corroborating reports. Neither changes the status.

### Admin pages

- `/admin/incidents`: totals, breakdowns by category, severity, state and band, a timeline (hourly for short ranges, daily otherwise), a review queue sorted by severity, an all-reports view, duplicate badges and filters.
- `/admin/incidents/{id}`: the original report, private photo, triage reasons, full review history, and the review form. Auditors see the same page read-only.

## Shared information service

`app/channels/info.py` (`InfoService`) is the only source for USSD, SMS and `GET /api/v1/public/election-updates`. It reads:

- results through `app.analytics.queries`, the same functions behind `/api/v1/analytics`, so figures cannot differ between channels;
- locations through the directory registry;
- updates through the existing announcements service.

It has no write methods. A test checks that a full USSD and SMS session changes no table except `sms_messages`, which is the duplicate and rate-limit log. No USSD or SMS command can change results, evidence, verification statuses, audit events or announcements.

## USSD

| Route | Purpose |
| --- | --- |
| `POST /api/v1/ussd/sessions` | Start a simulator session. Returns 404 when the simulator is off |
| `POST /api/v1/ussd/sessions/{id}/input` | Send one input to a simulator session |
| `POST /api/v1/ussd/gateway` | Gateway callback, using the common cumulative-text format (`1*2*3`) |

Menu: polling-unit, ward, LGA, state and national results, and election updates. `98` shows more, `0` goes back, `00` returns to the menu. Every screen fits 160 characters. Sessions end after `USSD_SESSION_TIMEOUT_SECONDS` without input.

The gateway format is handled by `CumulativeTextAdapter`. A different provider format needs a new `UssdGatewayAdapter`, not a change to the menu. If a callback arrives for a session the store does not know, for example after a restart, the handler replays the cumulative history.

Session state is kept in memory, in `InMemoryUssdSessionStore`. A multi-worker deployment needs a shared store such as Redis behind the `UssdSessionStore` protocol.

## SMS

`POST /api/v1/sms/incoming` takes `{ "phone_number": "...", "message": "...", "message_id": "..." }`.

| Command | Reply |
| --- | --- |
| `RESULT <polling unit code>` | Reported and verified figures for one polling unit |
| `WARD <code>`, `LGA <code>`, `STATE <code>` | Area totals and coverage |
| `NATIONAL` | National totals and coverage |
| `STATUS <polling unit code>` | Verification stage for one polling unit |
| `UPDATES` | Latest election updates |
| `HELP`, `MORE` | Command list, and the next reply parts |

Replies are split into numbered parts of up to 160 characters, with three parts per reply and the rest available through `MORE`. Every result reply ends with a demo or not-official notice.

Protection:

- Phone numbers are normalised and hashed with HMAC-SHA256 using `CHANNEL_HASH_SECRET`. They are never stored in clear.
- `SMS_MESSAGES_PER_WINDOW` per number per `SMS_WINDOW_SECONDS`.
- A repeated provider `message_id` returns the original reply without counting again, including when two copies arrive at the same moment.
- `GET /api/v1/sms/messages/{ref}` returns the logged reply only to staff, or to the simulator.

Replies are returned in the HTTP response. For Africa's Talking, `POST /api/v1/sms/africastalking` receives the inbound form and sends the reply through the Messaging API (`app/channels/africastalking.py`) as a background task. Duplicate deliveries are not answered twice, and neither phone numbers nor message text are logged.

## Gateway trust

Callbacks are never trusted without validation:

- A signed callback must carry `X-VoteTrace-Signature: sha256=<hex HMAC-SHA256 of the raw body>`, using `USSD_WEBHOOK_SECRET` or `SMS_WEBHOOK_SECRET` (at least 32 characters). The comparison runs in constant time.
- Africa's Talking cannot sign callbacks, so its callback URLs carry `?token=<CHANNEL_CALLBACK_TOKEN>` (at least 32 characters, compared in constant time). A wrong token is rejected with 401. Keep the token out of shared screenshots and logs, and rotate it if it leaks.
- Unsigned calls are accepted only while `CHANNEL_SIMULATOR_ENABLED` is on. It defaults to on outside production, and production refuses to start with it on.
- All payloads go through Pydantic validation, and inputs are length-limited.

## Running the simulators locally

```bash
cd backend && python -m app.analytics.demo_seed
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
cd ../frontend && npm run dev
```

Open <http://localhost:5173/phone-access>. Use `localhost`, not `127.0.0.1`, because `CORS_ORIGINS` lists `http://localhost:5173`. The page is labelled "Test console", and no shortcode is shown.

Directly with curl:

```bash
curl -s -X POST localhost:8000/api/v1/sms/incoming \
  -H 'Content-Type: application/json' \
  -d '{"phone_number":"+2348000000000","message":"NATIONAL"}'
```

## Connecting a real provider (Africa's Talking)

The integration code is in place. What it needs from you is an account, credentials and a public address, none of which can be created from this repository.

1. Create an account at <https://account.africastalking.com>. Start in the sandbox (username `sandbox`) and generate an API key.
2. Expose the API on a public HTTPS address, for example `ngrok http 8000` or `cloudflared tunnel --url http://localhost:8000`. The provider cannot reach `localhost`.
3. In `backend/.env` set `CHANNEL_CALLBACK_TOKEN` (`openssl rand -hex 32`), `CHANNEL_HASH_SECRET`, `AFRICASTALKING_USERNAME`, `AFRICASTALKING_API_KEY` and `AFRICASTALKING_ENVIRONMENT=sandbox`. Restart the API.
4. In the sandbox dashboard, create a USSD service code with callback `https://<public-host>/api/v1/ussd/gateway?token=<token>`, and set the SMS inbound callback to `https://<public-host>/api/v1/sms/africastalking?token=<token>` on a sandbox shortcode.
5. Open the sandbox phone simulator (<https://simulator.africastalking.com>), dial the service code or text the shortcode, and the answers come from this API.
6. To reach real handsets, switch the account to live and apply for a dedicated or shared USSD code and an SMS shortcode or sender ID. These are paid, need telecom approval, and take time. Then set `AFRICASTALKING_ENVIRONMENT=live`, `AFRICASTALKING_SENDER_ID`, and `CHANNEL_SIMULATOR_ENABLED=false`.
7. Run the API on a server with a fixed domain rather than a tunnel, use a shared `UssdSessionStore` if more than one worker runs, and import the official polling-unit register so that codes in commands match real polling units.

Other gateways can use the HMAC signature scheme above instead.
