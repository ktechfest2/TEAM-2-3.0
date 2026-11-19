# Result aggregation and the national dashboard

This document explains how VoteTrace turns polling-unit evidence into ward, LGA, state and national figures. It also covers what the dashboard shows and how it stays current.

**VoteTrace is independent civic verification. Its figures are not INEC declarations, are not legally binding, and never name a winner.** Totals cover only the polling units counted so far. Partial coverage is not a final result.

## Shape

```
evidence_submissions ──(workflow commit)──► polling_unit_results (one row per election × polling unit)
                                              └─ polling_unit_result_metrics (stream × metric × value, with ward/LGA/state ids)
                                                     │
            ward / LGA / state / national ◄── SQL SUM … GROUP BY on demand
```

The only stored aggregate is the per-polling-unit row. Ward, LGA, state and national totals are indexed `SUM … GROUP BY` queries over those rows, so they always add up exactly. There is no second copy of the totals that could drift. Expected polling-unit counts come from the polling-unit register (`DirectoryRepository`), not from the results tables.

Code lives in `backend/app/analytics/`:

| File | Responsibility |
| --- | --- |
| `policy.py` | Pure function `decide(submissions)`: the reconciliation policy below |
| `refresh.py` | Recomputes one polling unit inside the caller's transaction, writes the audit event |
| `hooks.py` | SQLAlchemy session hooks that call `refresh.py` for every polling unit touched by a commit |
| `registry.py` | Hierarchy and expected counts from the register (State, LGA, Ward, Polling Unit, FCT included) |
| `queries.py` | Area summaries, party totals, coverage, alerts, drill-down lists, progress |
| `events.py` | In-process broker and Server-Sent Events stream |
| `demo_seed.py` | Labelled demonstration dataset |

## Reconciliation policy

For each (election, polling unit) the policy looks at every submission:

1. **Rejected** submissions are ignored. They stay visible in the evidence API and audit trail, but they never contribute figures.
2. A submission is **accepted** when its workflow status is `arithmetic_validated`, `cross_checked`, `flagged_for_review`, `under_human_review`, `reviewed` or `verified`, its latest deterministic validation passed, and it has a result fingerprint. Received, processing and extracted submissions, and any whose validation failed, are **pending**. They show that evidence arrived but add no figures.
3. Accepted submissions are grouped by **result fingerprint** (SHA-256 of the canonical transcribed values).
4. Exactly one group means the submissions agree. That one set of values is the unit's **reported** result. If at least one submission in the group reached `verified` (two distinct reviewer approvals by default, `VERIFICATION_REQUIRED_APPROVALS`), the same values are also the unit's **verified** result.
5. More than one group is a **conflict**. Every submission is kept and listed. The unit counts as reporting, but its figures are **excluded from both reported and verified totals** until reviewers reject the wrong submission or submissions.

Resulting polling-unit status:

| Status | Meaning | Reported totals | Verified totals |
| --- | --- | --- | --- |
| `not_reporting` | No live (non-rejected) submission | — | — |
| `pending` | Evidence received, none accepted yet | — | — |
| `reported` | Accepted submissions agree, not yet verified | included | — |
| `conflict` | Accepted submissions disagree | excluded | excluded |
| `verified` | Agreeing figures approved by reviewers | included | included |

The reported stream therefore contains every unit with one agreed result, verified or not. The verified stream is the subset that passed human review. The two are always shown side by side, never merged.

### Duplicate handling

- A polling unit contributes **at most one** set of figures per stream, however many submissions it has. Ten agreeing photos of one sheet count once.
- The database enforces this. `polling_unit_results` is unique on `(election_id, polling_unit_id)`, and `polling_unit_result_metrics` is unique on `(result_id, stream, metric)`. Check constraints require a reported fingerprint for reported and verified rows, a verified fingerprint for verified rows, non-negative values and a positive revision.
- **Independent sources** are reported for transparency only, and never multiply votes. They are agreeing submissions from different accounts whose original image is neither byte-identical (SHA-256) nor a near-duplicate (perceptual hash within Hamming distance 6) of an earlier one, counted in received order.
- "Submissions received" and "unique polling units reporting" are separate figures everywhere.

### Corrections

Human corrections, re-validation, review decisions and rejections all change the submission inside a database transaction. The session hooks see the change and recompute that polling unit **in the same transaction** before commit:

- `before_flush` records which (election, polling unit) pairs had an `EvidenceSubmission` inserted or modified.
- `before_commit` locks each affected result row (`INSERT … ON CONFLICT DO NOTHING`, then `SELECT … FOR UPDATE`), re-runs the policy, and replaces the metric rows only if something changed. It also bumps `revision` and appends a hash-chained audit event (`entity_type = polling_unit_result`, `action = aggregation.recalculated`, with previous and new status and fingerprints).
- `after_commit` publishes an identifier-only change event. `after_rollback` discards pending work, so a failed transaction never announces a change.

Only the affected polling units are recomputed. There is no national recompute on each change. Concurrent commits to the same unit serialise on the row lock, and the second one recomputes from the committed state. `POST /api/v1/admin/analytics/rebuild` (system or election administrators only) re-derives every unit of an election from source records. That is for recovery, not normal operation.

## Coverage

All coverage figures are divided by **expected polling units**, the number of registered polling units in the area for the election. They are rounded to one decimal place and are `null` when an area expects none.

- **Reporting coverage** = units with status `reported`, `conflict` or `verified` ÷ expected. Shown as "28 / 44 polling units reporting — 63.6% coverage".
- **Verification coverage** = units with status `verified` ÷ expected. Shown as "14 / 44 polling units verified — 31.8% verification coverage".
- **Pending** = units with at least one submission that are not verified.
- **Flagged** = units with a submission in `flagged_for_review`, or a conflict.
- **Discrepancies** = conflicts. **Unusual patterns** = units with open VoteTrace AI alerts (these are prompts for human review, not findings of wrongdoing).
- **Incomplete location records** = registered units with no coordinates, no address description, or a status still awaiting verification.
- At area levels, child areas count as **reporting** when at least one of their units reports. **Outstanding** child areas have none.

Party share percentages are each party's share of the party votes **in that stream only**, from the units that stream includes. They are labelled as such and never presented as shares of the whole electorate.

## API

Public, read-only, under `/api/v1/analytics` (all take `election_id`):

| Route | Returns |
| --- | --- |
| `GET /national` | National summary, both streams, states with coverage, alerts, provenance |
| `GET /states`, `GET /states/{id}`, `GET /lgas/{id}`, `GET /wards/{id}` | The same shape per level, with children |
| `GET /polling-units` | Paginated polling-unit rows (filter by `state_id`, `lga_id` or `ward_id`, and `status`) |
| `GET /polling-units/{id}` | Public verification report: status, approvals, checks, source records without submitter, image or storage details |
| `GET /reporting-coverage`, `GET /verification-coverage` | Areas at `level=state|lga|ward` (with `parent_id` below state), ordered least-covered first |
| `GET /party-results` | Both streams plus a per-child breakdown for a scope |
| `GET /discrepancies` | Polling units by `kind=conflict|flagged|anomaly|pending|incomplete` |
| `GET /progress` | Cumulative reporting and verified units by hour |
| `GET /updates` | Server-Sent Events (below) |

Every query parameter is typed and validated (UUIDs, enums, `page` 1–10000, `page_size` 1–100). Only one of `state_id`, `lga_id` or `ward_id` may be given. Unknown areas or elections return 404. The global per-client rate limit (`RATE_LIMIT_PER_MINUTE`) applies. There is no public write route. The API derives totals only from server-side records and never accepts client-supplied totals.

## Real-time updates

`GET /analytics/updates?election_id=…` is a Server-Sent Events stream. It sends `retry: 5000` and a `ready` event, then one `aggregation` event per polling unit whose result changed, plus heartbeats every 15 seconds. Events carry identifiers only (election, polling unit, ward, LGA, state, status, revision), never figures. Clients refetch the affected summaries from the API. Reconnecting clients send `Last-Event-ID` and receive buffered events (last 500). Clients that fall behind receive `resync`. The stream is capped at 500 concurrent listeners and returns 503 above that.

The dashboard subscribes with `EventSource`. It batches events for 3 seconds and refetches only queries whose area contains the changed unit. It also refreshes every 90 seconds as a fallback, and shows the connection state ("Live updates on", "interrupted — retrying", "unavailable — refreshing periodically").

**Limitation:** the broker is in-process. With several API workers, a change committed in one worker only reaches listeners on that worker. Others still update through the 90-second fallback. For multi-worker deployments, replace the broker's publish/subscribe with Postgres `LISTEN/NOTIFY` (the `after_commit` hook is the single place to change). Proxies must not buffer the stream (`X-Accel-Buffering: no` is set).

## Dashboard

Public at `/results` and for staff at `/admin/results`, which is the same screens plus links into the evidence review workspace.

- **National → State → LGA → Ward → Polling unit** drill-down with breadcrumbs. Every level shows coverage cards, reported and verified party figures, alerts, freshness and provenance, child-area progress, an area comparison and progress over time.
- **Map**: state boundaries coloured by reporting coverage, never by party. States not in the register are greyed out. Selecting a state opens its dashboard. A table gives the same information for keyboard and screen-reader users.
- **Polling unit**: the public verification report and source records. Staff also see links to each submission. The public never sees submitter identities, images or storage paths.
- **Source records** (`/results/records`): the polling units behind any total or alert, filterable by status.
- **Freshness**: last result change, when figures were generated, when they were fetched, election name and ID, level, coverage, and data status. Data status is one of "Demonstration data from the server", "Current server data", or "Saved on this device (not live)". Saved copies show a warning and the live badge is suppressed, so cached data is never presented as live.
- Charts are plain SVG and CSS (no chart library). Parties are listed in ballot order and use a colour-blind-safe palette that does not represent party colours. No screen ranks parties or uses winner language.

## Map boundaries

`frontend/public/geo/nigeria-states.geojson` holds the 36 states plus the FCT from **geoBoundaries gbOpen NGA ADM1** (source: GRID3), licensed **CC BY 4.0**. The attribution is shown on the map. It was simplified for display with `scripts/simplify_boundaries.py` (Ramer–Douglas–Peucker, tolerance 0.008°, 3 decimals) and is not for legal or survey use. States are joined on ISO 3166-2 codes (`states.iso_code`, for example `NG-FC`, `NG-LA`, `NG-KN`). The file is precached so the map works offline.

To regenerate:

```bash
curl -L -o /tmp/ngb.geojson "$(curl -s https://www.geoboundaries.org/api/current/gbOpen/NGA/ADM1/ | python3 -c 'import json,sys;print(json.load(sys.stdin)["gjDownloadURL"])')"
python3 scripts/simplify_boundaries.py /tmp/ngb.geojson frontend/public/geo/nigeria-states.geojson
```

## Demonstration dataset

```bash
cd backend
python -m app.analytics.demo_seed
```

This seeds the fictional **Presidential Election 2027 (sample)** over the demo directory (3 states, 6 LGAs, 15 wards, 44 polling units with uneven counts per ward). It runs each sheet through the real pipeline: upload, OCR or manual transcription, validation, comparison, and review by fixed demo reviewer accounts. Scenarios cycle through verified, reported, not reporting, two agreeing sources, conflict, pending, failed arithmetic, under review and rejected. Sheet images are stamped "DEMONSTRATION - NOT A REAL RESULT SHEET", and every API response carries **"Sample data. Not an official election result."**

The seed refuses to run in production or against a non-demo election, and it skips units that already have submissions. Figures are generated, arithmetically consistent and fictional. They are not INEC data and are not hardcoded in the API or UI.

## Known limitations

- **Expected units per election.** Until the register records which polling units take part in each election, every registered unit is treated as expected for every election. With the official register, add an election-to-polling-unit mapping and `registry.py` will use it.
- **Single-process live updates.** See [Real-time updates](#real-time-updates).
- **Progress over time** is reconstructed from validation and verification timestamps of the units' current state. It is not a log of every historical change. The audit trail holds that.
- The demo directory covers three states. The map shows all 37 boundaries, and states without register data are marked as such rather than shown as zero.
