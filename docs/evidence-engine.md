# Evidence capture and result verification

This document covers the evidence pipeline: upload, OCR, human correction, deterministic validation, cross-submission comparison, VoteTrace AI anomaly detection, integrity, and the review workflow.

**VoteTrace statuses describe this platform's own checks and human review. They are not INEC declarations.** This document stops at the per-submission decision. How submissions become polling-unit, ward, LGA, state and national figures is in [results-aggregation.md](results-aggregation.md).

## Pipeline

```
upload ─► validate bytes ─► SHA-256 + perceptual hash ─► private storage (original, never modified)
      ─► preprocess copy ─► OCR (replaceable provider) ─► fields v1 with confidence + review flags
      ─► human corrections (new versions; OCR output kept) ─► deterministic validation
      ─► comparison with other submissions ─► VoteTrace AI alerts ─► human review ─► VERIFIED / REJECTED
```

Every step appends an event to the submission's hash-chained audit trail.

## Upload

`POST /api/v1/evidence` (multipart) requires a signed-in user with `observer`, `party_agent`, `reviewer`, `election_admin` or `system_admin`.

- `Idempotency-Key` header (required). Replaying the same key with the same file returns the original receipt (`201` first, then `200`). The same key with different content returns `409 idempotency_conflict`.
- `X-Content-SHA256` (optional). The client's hash of the file. If it differs from the server's hash of the received bytes, the upload is refused with `hash_mismatch`.
- The file type is determined from its content (magic bytes plus a full Pillow decode), not from its name or declared type. JPEG, PNG and WebP are accepted. Size and dimension limits come from `EVIDENCE_MAX_BYTES`, `EVIDENCE_MIN_DIMENSION` and `EVIDENCE_MAX_DIMENSION`. Decompression bombs are refused.
- `captured_at` is normalised to UTC and may not be in the future. The server records `received_at` separately.
- Each user may submit at most `EVIDENCE_MAX_PER_POLLING_UNIT` sheets per polling unit and election. Uploads are rate limited to 20 per minute per user.

The SHA-256 is computed before any processing. The original bytes are stored unchanged at a content-addressed key, and every later read re-hashes them (`GET /{id}/integrity`). Preprocessing (EXIF orientation, grayscale, denoise, deskew, contrast) works on a copy stored as a separate derivative image.

Storage is `EVIDENCE_STORAGE=local` (a private directory, `var/evidence`) or `supabase` (the private `evidence` bucket, accessed with the service-role key on the server only). Images reach the browser only through `GET /{id}/image`, which checks access and returns `Cache-Control: private, no-store`. The storage layer can mint signed URLs, but the API does not hand them out.

## OCR

The provider interface (`app/evidence/ocr.py`) returns tokens with text, confidence and bounding box. `OCR_PROVIDER=tesseract` uses Tesseract through `pytesseract`. `OCR_PROVIDER=rapidocr` uses RapidOCR (PaddleOCR models on ONNX Runtime), which needs no system binary; install it with the steps in `backend/requirements-ocr.txt`. `OCR_PROVIDER=auto` (the default) picks Tesseract when its binary is present and RapidOCR otherwise. `OCR_PROVIDER=none` disables OCR so every field is entered by hand.

RapidOCR returns whole lines. The provider splits them into words using the recogniser's own spaces, falling back to character gaps for lines read without spaces. The field mapper tolerates labels split or merged by the engine, digits misread inside labels (`c0de`), and a figure reported as a separate line from its label when both sit on the same row.

Fields are mapped using a configurable template (`app/evidence/templates/*.json`). Party rows come from the election's configured party list. No party is hardcoded. The included `generic-pu-result-v1` template is a demonstration layout. **It is not a certified INEC form layout.**

Each field carries a confidence value, the source text, a bounding box and review reasons. A field requires review when it was not found, is below `OCR_CONFIDENCE_THRESHOLD`, or contained look-alike characters (for example `O` read as `0`). Look-alike substitutions also reduce confidence.

### OCR limitations

- Neither engine is tuned for handwriting. Handwritten figures on result sheets will often be misread or missed. Accuracy on printed sample sheets says little about real, handwritten forms.
- Photos taken at an angle, in poor light, or with folds, stamps or signatures over the figures reduce accuracy.
- Label matching depends on the template wording. A different form layout needs its own template.
- Confidence is the engine's own estimate. A high confidence value can still be wrong.
- If no engine is installed, processing completes with empty fields marked `manual_entry_required`.

OCR output is always a draft. Every value must be checked against the image by a person.

Install Tesseract: `brew install tesseract` (macOS) or `apt-get install tesseract-ocr` (Debian/Ubuntu).

## Human correction

`PATCH /{id}/extraction` writes a new version for each changed field, with `origin=human`, the editor, and a reason. Changing an existing value requires a reason. Version 1 (the OCR output) is never overwritten. The full history is returned with each field. After a correction, earlier validation is no longer current and the record returns to `extracted`.

The submitter may correct their own record until review starts. Reviewers may correct at any stage before a final decision.

## Deterministic validation

`POST /{id}/validate` runs fixed rules from the template: required fields, non-negative integers, party totals equal total valid votes, valid plus rejected equal total votes cast, votes cast not above accredited voters, accredited voters not above registered voters, and the sheet's polling-unit code and election type match the submission.

**Arithmetic consistency is not proof of authenticity.** A fabricated sheet can add up perfectly. Validation can only show that figures are internally consistent or not.

The canonical result fingerprint (SHA-256 of the canonical JSON of the field values) is recorded with each validation.

## Comparison

Validated submissions for the same polling unit and election are compared:

- `identical_file`: the same SHA-256
- `near_duplicate_image`: perceptual hash distance of 6 or less
- `same_submitter`: the same account submitted both

Fields are reported as `match`, `conflict` or `incomplete`. Agreement between duplicates or between submissions from the same account does not count as independent confirmation. The engine never calls a submission fraudulent. Its recommendation codes are `consistent`, `review_conflicts`, `review_dependence` and `no_comparison`.

## VoteTrace AI anomaly detection

The engine combines four components:

1. **OCR uncertainty**: fields that came from OCR and still require review.
2. **Discrepancy**: conflicting values between submissions and duplicate evidence from different accounts.
3. **Statistical**: an Isolation Forest (fixed random seed) over four ratios: turnout of accredited voters, rejected-ballot share, leading-party share and accreditation of registered voters. It runs only when at least `ANOMALY_MIN_SAMPLES` reliable reference records exist. Reliable means human-reviewed (`reviewed` or `verified`), one per other polling unit in the same election. With fewer records, it reports `insufficient_data` and raises no statistical alert.
4. **Explainability**: each alert states what was observed, why, which fields contributed (robust z-scores against the reference median), the model name and version, and a recommendation.

Every alert uses the headline **"Anomaly detected — human review required."** The recommendation states that the alert is not a finding of fraud or wrongdoing.

VoteTrace AI never declares fraud, rejects a result, changes a value, or overrides deterministic validation. An alert can only route a record to human review. There is no fraud classifier and no model trained on labelled fraud data.

### Demonstration

```bash
cd backend
python -m app.evidence.ai.demo
```

The demo prints a statistical analysis over 60 synthetic reference records. Its output is labelled `DEMONSTRATION — synthetic values, not election data` and `is_demo: true`. It is not used by the API.

## Workflow

| Status | Meaning |
| --- | --- |
| `received` | Stored and fingerprinted |
| `processing` | Preprocessing and OCR running |
| `extracted` | Draft values available for checking and correction |
| `arithmetic_validated` | Deterministic rules passed |
| `cross_checked` | Compared with other submissions; no conflicts or alerts |
| `flagged_for_review` | A rule failed, values conflict, or an anomaly alert was raised |
| `under_human_review` | A reviewer has started a review |
| `reviewed` | At least one reviewer approved the current fingerprint |
| `verified` | The required number of distinct reviewers approved the same fingerprint |
| `rejected` | A reviewer rejected the evidence, with notes |

Transitions are enforced on the server (`app/evidence/workflow.py`). Invalid transitions return `409 invalid_transition`. Clients cannot send a status.

`verified` is never automatic. It requires `VERIFICATION_REQUIRED_APPROVALS` (default 2) approvals from distinct reviewers on the current result fingerprint. Approvals made before a correction request or rejection are not counted. A reviewer cannot review their own submission. Approval is refused if validation is stale or failing, or if any field still requires review. Rejection and correction requests require notes.

## Integrity and audit

- **Image hash**: SHA-256 of the original bytes, re-verified on every read.
- **Result fingerprint**: SHA-256 of the canonical field values, recorded with each validation and each review.
- **Audit trail**: each event stores the previous event's hash and its own hash over its content. `GET /{id}/audit` re-verifies the chain and reports `missing_event`, `broken_link` or `content_altered`.

The application never updates or deletes history rows. Migration `0002` adds Postgres triggers that refuse `UPDATE`, `DELETE` and `TRUNCATE` on evidence history tables, enables row-level security, and revokes table access from the `anon` and `authenticated` roles.

**The chain is tamper-evident, not tamper-proof.** A database owner or other privileged role can disable triggers and rewrite rows and hashes together. Detecting that requires anchoring chain heads outside the database (for example, periodically publishing them), which is not implemented.

## Offline capture

The submit screen checks the file in the browser (content type, size, dimensions), computes its SHA-256 and saves a draft to IndexedDB (`evidenceDrafts`). The sync runner uploads queued drafts with the draft id as the `Idempotency-Key`, so retries never create duplicates. Network errors keep the draft queued. Server refusals mark it failed until the user retries or discards it.

A draft is shown as received only after the server confirms it. The image bytes are then removed from the device. Server-side evidence data is never cached in IndexedDB.

## Running locally

Without `DATABASE_URL`, evidence data is stored in a development SQLite file (`DEV_DATABASE_PATH`) and images in `EVIDENCE_LOCAL_DIR`. Both are under `backend/var/`, which is git-ignored. Authenticated routes still need `SUPABASE_JWT_SECRET`.

With Postgres, run `alembic upgrade head` and then `python -m app.directory.seed_demo` (development only) so the demo elections and polling units exist for foreign keys.

## Tests

```bash
cd backend && pytest                  # engine and API tests, including evidence
cd frontend && npm test               # includes the evidence queue and screens
```

Test images and OCR output are generated by `tests/evidence_support.py` and are labelled as test data. Tests use a fake OCR provider, so they do not need Tesseract.
