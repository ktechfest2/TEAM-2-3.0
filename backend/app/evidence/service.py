"""Evidence workflow service. All writes to evidence tables happen here.

Routes authorise the caller; this module enforces the workflow rules: originals are
stored once and verified on every read, OCR output is never overwritten, statuses
move only along permitted transitions, and only human reviewers can verify or reject."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError as DbIntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import Principal
from app.db.enums import (
    EvidenceImageKind,
    EvidenceStatus,
    ExtractionStatus,
    FieldOrigin,
    ReviewDecision,
)
from app.db.models import (
    AnomalyAlert,
    EvidenceImage,
    EvidenceReview,
    EvidenceSubmission,
    ExtractedResultField,
    OcrExtraction,
    ResultValidation,
    SubmissionComparison,
)
from app.evidence import workflow
from app.evidence.ai import analyze
from app.evidence.audit import AuditAction, append_event
from app.evidence.comparison import SubmissionSnapshot, compare_submissions
from app.evidence.db import ensure_user
from app.evidence.field_mapping import MappedField, empty_fields, field_labels, map_fields
from app.evidence.hashing import canonical_result, result_fingerprint, sha256_bytes
from app.evidence.image_validation import safe_filename, validate_image
from app.evidence.ocr import OcrProvider, OcrUnavailableError
from app.evidence.preprocess import original_perceptual_hash, preprocess
from app.evidence.storage import EvidenceStorage, IntegrityError, read_verified
from app.evidence.templates import FormTemplate, get_template, party_key
from app.evidence.validation import SubmissionContext, validate_result
from app.schemas.elections import Election
from app.schemas.polling_units import PollingUnitDetail

logger = logging.getLogger("verivote.evidence")

S = EvidenceStatus
_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

def get_submission(db: Session, submission_id: uuid.UUID) -> EvidenceSubmission:
    submission = db.get(EvidenceSubmission, submission_id)
    if submission is None:
        raise AppError("not_found", "Evidence submission not found.", 404)
    return submission

def original_image(db: Session, submission_id: uuid.UUID) -> EvidenceImage:
    image = db.scalar(
        select(EvidenceImage).where(
            EvidenceImage.submission_id == submission_id,
            EvidenceImage.kind == EvidenceImageKind.ORIGINAL,
        )
    )
    if image is None:
        raise AppError("evidence_missing", "The original evidence record is missing.", 410)
    return image

def images(db: Session, submission_id: uuid.UUID) -> list[EvidenceImage]:
    return list(
        db.scalars(
            select(EvidenceImage)
            .where(EvidenceImage.submission_id == submission_id)
            .order_by(EvidenceImage.created_at)
        )
    )

def latest_extraction(db: Session, submission_id: uuid.UUID) -> OcrExtraction | None:
    return db.scalar(
        select(OcrExtraction)
        .where(OcrExtraction.submission_id == submission_id)
        .order_by(OcrExtraction.created_at.desc())
        .limit(1)
    )

def field_history(db: Session, extraction_id: uuid.UUID) -> list[ExtractedResultField]:
    return list(
        db.scalars(
            select(ExtractedResultField)
            .where(ExtractedResultField.extraction_id == extraction_id)
            .order_by(ExtractedResultField.field_key, ExtractedResultField.version)
        )
    )

def effective_fields(history: list[ExtractedResultField]) -> dict[str, ExtractedResultField]:
    current: dict[str, ExtractedResultField] = {}
    for row in history:
        if row.field_key not in current or row.version > current[row.field_key].version:
            current[row.field_key] = row
    return current

def field_value(row: ExtractedResultField) -> int | str | None:
    return row.value_int if row.value_int is not None else row.value_text

def latest_validation(db: Session, submission_id: uuid.UUID) -> ResultValidation | None:
    return db.scalar(
        select(ResultValidation)
        .where(ResultValidation.submission_id == submission_id)
        .order_by(ResultValidation.created_at.desc())
        .limit(1)
    )

def latest_comparison(db: Session, submission_id: uuid.UUID) -> SubmissionComparison | None:
    return db.scalar(
        select(SubmissionComparison)
        .where(SubmissionComparison.trigger_submission_id == submission_id)
        .order_by(SubmissionComparison.created_at.desc())
        .limit(1)
    )

def alerts(db: Session, submission_id: uuid.UUID) -> list[AnomalyAlert]:
    return list(
        db.scalars(
            select(AnomalyAlert)
            .where(AnomalyAlert.submission_id == submission_id)
            .order_by(AnomalyAlert.created_at.desc())
        )
    )

def reviews(db: Session, submission_id: uuid.UUID) -> list[EvidenceReview]:
    return list(
        db.scalars(
            select(EvidenceReview)
            .where(EvidenceReview.submission_id == submission_id)
            .order_by(EvidenceReview.created_at)
        )
    )

@dataclass(frozen=True)
class Upload:
    data: bytes
    filename: str | None
    content_type: str | None
    idempotency_key: uuid.UUID
    captured_at: datetime | None
    client_sha256: str | None
    client_info: dict[str, str]

def ingest(
    db: Session,
    storage: EvidenceStorage,
    settings: Settings,
    principal: Principal,
    election: Election,
    polling_unit: PollingUnitDetail,
    upload: Upload,
) -> tuple[EvidenceSubmission, bool]:
    """Store a new submission. Returns (submission, created). Retries with the same
    idempotency key return the original record instead of creating another."""
    existing = db.scalar(
        select(EvidenceSubmission).where(
            EvidenceSubmission.submitted_by == principal.user_id,
            EvidenceSubmission.idempotency_key == upload.idempotency_key,
        )
    )
    if existing is not None:
        if (
            existing.original_sha256 != sha256_bytes(upload.data)
            or existing.polling_unit_id != polling_unit.id
            or existing.election_id != election.id
        ):
            raise AppError(
                "idempotency_conflict",
                "This idempotency key was already used for a different submission.",
                409,
            )
        return existing, False

    validated = validate_image(
        upload.data,
        filename=upload.filename,
        declared_content_type=upload.content_type,
        settings=settings,
    )
    # Fingerprint the exact received bytes before any decoding or processing.
    digest = sha256_bytes(upload.data)
    if upload.client_sha256 and upload.client_sha256.lower() != digest:
        raise AppError(
            "hash_mismatch",
            "The file changed in transit: its fingerprint does not match the one sent.",
            422,
        )

    same_file = db.scalar(
        select(EvidenceSubmission).where(
            EvidenceSubmission.submitted_by == principal.user_id,
            EvidenceSubmission.election_id == election.id,
            EvidenceSubmission.polling_unit_id == polling_unit.id,
            EvidenceSubmission.original_sha256 == digest,
        )
    )
    if same_file is not None:
        return same_file, False

    count = db.scalar(
        select(func.count())
        .select_from(EvidenceSubmission)
        .where(
            EvidenceSubmission.submitted_by == principal.user_id,
            EvidenceSubmission.election_id == election.id,
            EvidenceSubmission.polling_unit_id == polling_unit.id,
        )
    )
    if (count or 0) >= settings.evidence_max_per_polling_unit:
        raise AppError(
            "submission_limit_reached",
            "You have reached the submission limit for this polling unit.",
            429,
        )

    perceptual = original_perceptual_hash(upload.data)
    submission_id = uuid.uuid4()
    received_at = datetime.now(UTC)
    key = f"originals/{election.id}/{submission_id}/{digest}.{_EXTENSIONS[validated.content_type]}"
    storage.put(key, upload.data, validated.content_type)

    ensure_user(db, principal)
    provenance = {
        "original_filename": safe_filename(upload.filename),
        "declared_content_type": (upload.content_type or "")[:60],
        "detected_content_type": validated.content_type,
        "capture_source": upload.client_info.get("capture_source", "unknown"),
        "client": {k: v[:120] for k, v in upload.client_info.items() if k != "capture_source"},
        "client_sha256_supplied": upload.client_sha256 is not None,
        "election_label": election.election_label,
        "polling_unit_code": polling_unit.code,
        "directory_is_demo": election.is_demo,
    }
    submission = EvidenceSubmission(
        id=submission_id,
        election_id=election.id,
        polling_unit_id=polling_unit.id,
        submitted_by=principal.user_id,
        idempotency_key=upload.idempotency_key,
        template_id=election.template_id,
        workflow_status=S.RECEIVED,
        status_changed_at=received_at,
        captured_at=upload.captured_at,
        received_at=received_at,
        original_sha256=digest,
        provenance=provenance,
    )
    image = EvidenceImage(
        submission_id=submission_id,
        kind=EvidenceImageKind.ORIGINAL,
        storage_bucket=storage.bucket,
        storage_path=key,
        content_type=validated.content_type,
        byte_size=validated.byte_size,
        width=validated.width,
        height=validated.height,
        sha256=digest,
        perceptual_hash=perceptual,
    )
    db.add(submission)
    db.flush()
    db.add(image)
    db.flush()
    append_event(
        db,
        entity_id=submission_id,
        action=AuditAction.EVIDENCE_RECEIVED,
        actor_id=principal.user_id,
        details={
            "election_id": election.id,
            "polling_unit_id": polling_unit.id,
            "captured_at": upload.captured_at,
            "received_at": received_at,
            "byte_size": validated.byte_size,
            "content_type": validated.content_type,
        },
    )
    append_event(
        db,
        entity_id=submission_id,
        action=AuditAction.EVIDENCE_HASHED,
        actor_id=None,
        details={"algorithm": "SHA-256", "original_sha256": digest, "image_id": image.id},
    )
    try:
        db.commit()
    except DbIntegrityError as exc:
        # A concurrent retry with the same idempotency key won the race.
        db.rollback()
        winner = db.scalar(
            select(EvidenceSubmission).where(
                EvidenceSubmission.submitted_by == principal.user_id,
                EvidenceSubmission.idempotency_key == upload.idempotency_key,
            )
        )
        if winner is None:
            raise AppError("conflict", "The submission could not be stored.", 409) from exc
        return winner, False
    return submission, True

def verify_original(
    db: Session,
    storage: EvidenceStorage,
    submission: EvidenceSubmission,
    actor_id: uuid.UUID | None,
) -> bytes:
    image = original_image(db, submission.id)
    if image.sha256 != submission.original_sha256:
        raise IntegrityError()
    try:
        data = read_verified(storage, image.storage_path, submission.original_sha256)
    except IntegrityError:
        append_event(
            db,
            entity_id=submission.id,
            action=AuditAction.INTEGRITY_FAILED,
            actor_id=actor_id,
            details={"image_id": image.id, "expected_sha256": submission.original_sha256},
        )
        db.commit()
        raise
    return data

def _election_template(election: Election) -> FormTemplate:
    return get_template(election.template_id)

def process(
    db: Session,
    storage: EvidenceStorage,
    provider: OcrProvider,
    settings: Settings,
    submission: EvidenceSubmission,
    election: Election,
    actor: Principal,
) -> OcrExtraction:
    status = S(submission.workflow_status)
    if status not in workflow.PROCESSABLE:
        raise AppError(
            "invalid_state", f"A submission in status {status.value} cannot be processed.", 409
        )
    template = _election_template(election)
    workflow.transition(db, submission, S.PROCESSING, actor_id=actor.user_id, reason="ocr")
    append_event(
        db,
        entity_id=submission.id,
        action=AuditAction.OCR_STARTED,
        actor_id=actor.user_id,
        details={"provider": provider.name, "template_id": template.id},
    )
    db.commit()

    try:
        original = verify_original(db, storage, submission, actor.user_id)
    except AppError:
        submission.processing_error = "integrity_or_storage_failure"
        workflow.transition(db, submission, S.RECEIVED, actor_id=None, reason="processing_failed")
        db.commit()
        raise
    append_event(
        db,
        entity_id=submission.id,
        action=AuditAction.INTEGRITY_VERIFIED,
        actor_id=None,
        details={"original_sha256": submission.original_sha256, "context": "before_processing"},
    )

    source = original_image(db, submission.id)
    try:
        processed = preprocess(original, provider)
    except Exception as exc:
        logger.warning("preprocessing failed type=%s", type(exc).__name__)
        submission.processing_error = "preprocessing_failed"
        append_event(
            db,
            entity_id=submission.id,
            action=AuditAction.OCR_FAILED,
            actor_id=None,
            details={"stage": "preprocessing"},
        )
        workflow.transition(db, submission, S.RECEIVED, actor_id=None, reason="processing_failed")
        db.commit()
        raise AppError("processing_failed", "The image could not be processed.", 422) from exc

    derivative_sha = sha256_bytes(processed.png_bytes)
    derivative_key = f"processed/{submission.election_id}/{submission.id}/{derivative_sha}.png"
    if db.scalar(select(EvidenceImage.id).where(EvidenceImage.storage_path == derivative_key)):
        derivative = db.scalar(
            select(EvidenceImage).where(EvidenceImage.storage_path == derivative_key)
        )
    else:
        storage.put(derivative_key, processed.png_bytes, "image/png")
        derivative = EvidenceImage(
            submission_id=submission.id,
            kind=EvidenceImageKind.PROCESSED,
            derived_from_id=source.id,
            storage_bucket=storage.bucket,
            storage_path=derivative_key,
            content_type="image/png",
            byte_size=len(processed.png_bytes),
            width=processed.width,
            height=processed.height,
            sha256=derivative_sha,
            perceptual_hash=processed.perceptual_hash,
            processing_steps=processed.steps,
        )
        db.add(derivative)
        db.flush()

    parties = election.parties
    error: str | None = None
    tokens: list[dict[str, Any]] = []
    raw_text: str | None = None
    provider_version: str | None = None
    if provider.is_available():
        try:
            result = provider.recognize(processed.image)
            provider_version = result.provider_version
            tokens = [token.as_dict() for token in result.tokens]
            raw_text = result.text
            mapped = map_fields(result.tokens, template, parties, settings.ocr_confidence_threshold)
            extraction_status = ExtractionStatus.COMPLETED
        except OcrUnavailableError:
            mapped, extraction_status = (
                empty_fields(template, parties),
                ExtractionStatus.OCR_UNAVAILABLE,
            )
        except Exception as exc:
            logger.warning("ocr failed type=%s", type(exc).__name__)
            mapped, extraction_status = empty_fields(template, parties), ExtractionStatus.FAILED
            error = "The OCR engine failed on this image. Enter the figures manually."
    else:
        mapped, extraction_status = (
            empty_fields(template, parties),
            ExtractionStatus.OCR_UNAVAILABLE,
        )
        error = "No OCR engine is available on the server. Enter the figures manually."

    confidences = [t["confidence"] for t in tokens]
    extraction = OcrExtraction(
        submission_id=submission.id,
        image_id=derivative.id if derivative else None,
        template_id=template.id,
        provider=provider.name,
        provider_version=provider_version,
        status=extraction_status,
        raw_text=raw_text[:20_000] if raw_text else None,
        tokens=tokens,
        mean_confidence=round(sum(confidences) / len(confidences), 4) if confidences else None,
        error=error,
    )
    db.add(extraction)
    db.flush()
    for item in mapped:
        db.add(_ocr_field_row(extraction, submission, item))
    submission.processing_error = None
    workflow.transition(db, submission, S.EXTRACTED, actor_id=None, reason="ocr_completed")
    append_event(
        db,
        entity_id=submission.id,
        action=AuditAction.OCR_COMPLETED,
        actor_id=None,
        details={
            "extraction_id": extraction.id,
            "status": extraction_status.value,
            "provider": provider.name,
            "provider_version": provider_version,
            "processed_image_sha256": derivative_sha,
            "fields_requiring_review": sorted(m.key for m in mapped if m.requires_review),
        },
    )
    db.commit()
    return extraction

def _ocr_field_row(
    extraction: OcrExtraction, submission: EvidenceSubmission, item: MappedField
) -> ExtractedResultField:
    return ExtractedResultField(
        extraction_id=extraction.id,
        submission_id=submission.id,
        field_key=item.key,
        version=1,
        origin=FieldOrigin.OCR,
        value_int=item.value_int,
        value_text=item.value_text,
        confidence=item.confidence,
        source_text=item.source_text,
        bbox=item.bbox,
        requires_review=item.requires_review,
        review_reasons=sorted(set(item.review_reasons))
        + (
            [f"ambiguous:{c}" for c in item.ambiguous_characters]
            if item.ambiguous_characters
            else []
        ),
    )

@dataclass(frozen=True)
class Correction:
    field_key: str
    value: int | str | None
    reason: str | None
    confirm: bool = False

def correct(
    db: Session,
    submission: EvidenceSubmission,
    election: Election,
    actor: Principal,
    corrections: list[Correction],
) -> list[ExtractedResultField]:
    status = S(submission.workflow_status)
    if status not in workflow.EDITABLE:
        raise AppError(
            "invalid_state", f"Values cannot be corrected while the status is {status.value}.", 409
        )
    extraction = latest_extraction(db, submission.id)
    if extraction is None:
        raise AppError("invalid_state", "Process the evidence before correcting values.", 409)
    template = _election_template(election)
    labels = field_labels(template, election.parties)
    current = effective_fields(field_history(db, extraction.id))

    written: list[ExtractedResultField] = []
    changes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in corrections:
        if item.field_key in seen:
            raise AppError("duplicate_field", f"{item.field_key} appears more than once.", 422)
        seen.add(item.field_key)
        spec = labels.get(item.field_key)
        if spec is None:
            raise AppError("unknown_field", f"{item.field_key} is not a field on this form.", 422)
        value = item.value
        if spec["kind"] == "integer":
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise AppError(
                    "invalid_value", f"{spec['label']} must be a whole number of zero or more.", 422
                )
        else:
            if value is not None and not isinstance(value, str):
                raise AppError("invalid_value", f"{spec['label']} must be text.", 422)
            value = (
                value.strip().upper()[:120] if isinstance(value, str) and value.strip() else None
            )
        previous = current.get(item.field_key)
        previous_value = field_value(previous) if previous else None
        if value == previous_value and not item.confirm:
            continue
        if (
            value != previous_value
            and previous_value is not None
            and not (item.reason or "").strip()
        ):
            raise AppError("reason_required", f"Give a reason for changing {spec['label']}.", 422)
        row = ExtractedResultField(
            extraction_id=extraction.id,
            submission_id=submission.id,
            field_key=item.field_key,
            version=(previous.version + 1) if previous else 1,
            origin=FieldOrigin.HUMAN,
            value_int=value if isinstance(value, int) else None,
            value_text=value if isinstance(value, str) else None,
            confidence=None,
            source_text=None,
            bbox=previous.bbox if previous else None,
            requires_review=value is None and bool(spec["required"]),
            review_reasons=["missing_value"] if value is None and spec["required"] else [],
            reason=(item.reason or "").strip()[:1000] or None,
            created_by=actor.user_id,
        )
        db.add(row)
        written.append(row)
        changes.append(
            {
                "field_key": item.field_key,
                "previous_value": previous_value,
                "previous_version": previous.version if previous else None,
                "new_value": value,
                "kind": "confirmation" if value == previous_value else "correction",
            }
        )
    if not written:
        return []
    ensure_user(db, actor)
    db.flush()
    append_event(
        db,
        entity_id=submission.id,
        action=AuditAction.FIELD_CORRECTED,
        actor_id=actor.user_id,
        details={"extraction_id": extraction.id, "changes": changes},
    )
    if status != S.EXTRACTED:
        workflow.transition(
            db, submission, S.EXTRACTED, actor_id=actor.user_id, reason="values_changed"
        )
    db.commit()
    return written

def _values(rows: dict[str, ExtractedResultField]) -> dict[str, int | str | None]:
    return {key: field_value(row) for key, row in sorted(rows.items())}

def _field_view(row: ExtractedResultField) -> dict[str, Any]:
    return {
        "field_key": row.field_key,
        "value": field_value(row),
        "confidence": row.confidence,
        "origin": FieldOrigin(row.origin).value,
        "requires_review": row.requires_review,
        "review_reasons": row.review_reasons,
        "ambiguous_characters": [
            r.split(":", 1)[1] for r in row.review_reasons if r.startswith("ambiguous:")
        ],
    }

def _snapshot_values(validation: ResultValidation) -> dict[str, int | str | None]:
    return {key: value for key, value in validation.result_snapshot["fields"]}

def validate(
    db: Session,
    submission: EvidenceSubmission,
    election: Election,
    polling_unit: PollingUnitDetail,
    actor: Principal,
    settings: Settings,
) -> ResultValidation:
    status = S(submission.workflow_status)
    if status not in workflow.VALIDATABLE:
        raise AppError(
            "invalid_state", f"A submission in status {status.value} cannot be validated.", 409
        )
    extraction = latest_extraction(db, submission.id)
    if extraction is None:
        raise AppError("invalid_state", "Process the evidence before validating it.", 409)
    template = _election_template(election)
    current = effective_fields(field_history(db, extraction.id))
    values = _values(current)
    attention = sorted(key for key, row in current.items() if row.requires_review)
    context = SubmissionContext(polling_unit.code, election.election_label)
    report = validate_result(values, template, election.parties, context, attention)
    canonical = canonical_result(
        election_id=submission.election_id,
        polling_unit_id=submission.polling_unit_id,
        template_id=template.id,
        values=values,
    )
    result_hash = result_fingerprint(canonical)

    if status != S.EXTRACTED:
        workflow.transition(
            db, submission, S.EXTRACTED, actor_id=actor.user_id, reason="revalidation"
        )

    # Comparison with every other submission for this election and polling unit that has
    # been validated at least once.
    party_keys = [party_key(p.code) for p in election.parties]
    compared_fields = [s.key for s in template.fields if s.kind == "integer"] + party_keys
    others = list(
        db.scalars(
            select(EvidenceSubmission).where(
                EvidenceSubmission.election_id == submission.election_id,
                EvidenceSubmission.polling_unit_id == submission.polling_unit_id,
                EvidenceSubmission.id != submission.id,
                EvidenceSubmission.workflow_status != S.REJECTED,
            )
        )
    )
    snapshots: list[SubmissionSnapshot] = []
    for other in others:
        other_validation = latest_validation(db, other.id)
        if other_validation is None:
            continue
        snapshots.append(
            SubmissionSnapshot(
                id=other.id,
                submitted_by=other.submitted_by,
                received_at=other.received_at,
                original_sha256=other.original_sha256,
                perceptual_hash=original_image(db, other.id).perceptual_hash,
                values=_snapshot_values(other_validation),
            )
        )
    target = SubmissionSnapshot(
        id=submission.id,
        submitted_by=submission.submitted_by,
        received_at=submission.received_at,
        original_sha256=submission.original_sha256,
        perceptual_hash=original_image(db, submission.id).perceptual_hash,
        values=values,
    )
    now = datetime.now(UTC)
    comparison_report = compare_submissions(target, snapshots, compared_fields, now)
    comparison = SubmissionComparison(
        election_id=submission.election_id,
        polling_unit_id=submission.polling_unit_id,
        trigger_submission_id=submission.id,
        submission_ids=comparison_report["submission_ids"],
        has_conflicts=bool(comparison_report["conflicting_fields"]),
        has_duplicates=bool(comparison_report["duplicates"]),
        report=comparison_report,
    )
    db.add(comparison)
    db.flush()

    reference = _reliable_reference(db, submission)
    analysis = analyze(
        fields=[_field_view(row) for row in current.values()],
        comparison=comparison_report if snapshots else None,
        target_values=values,
        reference_values=reference,
        party_keys=party_keys,
        min_samples=settings.anomaly_min_samples,
        threshold=settings.ocr_confidence_threshold,
    )
    for alert in analysis.alerts:
        db.add(
            AnomalyAlert(
                submission_id=submission.id,
                analysis_run_id=analysis.run_id,
                category=alert.category,
                severity=alert.severity,
                headline=alert.headline,
                summary=alert.summary,
                fields=alert.fields,
                explanation=alert.explanation,
                recommendation=alert.recommendation,
                model_name=alert.model_name,
                model_version=alert.model_version,
                is_demo=alert.is_demo,
            )
        )

    full_report = {
        **report,
        "result_hash": result_hash,
        "comparison_id": str(comparison.id),
        "analysis_run_id": str(analysis.run_id),
        "statistical_analysis": analysis.statistical,
    }
    validation = ResultValidation(
        submission_id=submission.id,
        extraction_id=extraction.id,
        template_id=template.id,
        result_hash=result_hash,
        result_snapshot=canonical,
        passed=report["is_consistent"],
        report=full_report,
        created_by=actor.user_id,
    )
    ensure_user(db, actor)
    db.add(validation)
    db.flush()

    append_event(
        db,
        entity_id=submission.id,
        action=AuditAction.VALIDATION_COMPLETED,
        actor_id=actor.user_id,
        details={
            "validation_id": validation.id,
            "result_hash": result_hash,
            "passed": report["passed"],
            "failed": report["failed"],
            "warnings": report["warnings"],
            "missing_fields": report["missing_fields"],
            "attention_fields": report["attention_fields"],
        },
    )
    append_event(
        db,
        entity_id=submission.id,
        action=AuditAction.COMPARISON_COMPLETED,
        actor_id=None,
        details={
            "comparison_id": comparison.id,
            "submission_ids": comparison_report["submission_ids"],
            "conflicting_fields": comparison_report["conflicting_fields"],
            "duplicate_types": sorted({d["type"] for d in comparison_report["duplicates"]}),
            "recommendation": comparison_report["recommendation"]["code"],
        },
    )
    for alert in analysis.alerts:
        append_event(
            db,
            entity_id=submission.id,
            action=AuditAction.ANOMALY_DETECTED,
            actor_id=None,
            details={
                "analysis_run_id": analysis.run_id,
                "category": alert.category.value,
                "severity": alert.severity.value,
                "fields": alert.fields,
                "model": f"{alert.model_name}@{alert.model_version}",
            },
        )

    needs_attention = bool(
        attention or comparison.has_conflicts or comparison.has_duplicates or analysis.alerts
    )
    if not report["is_consistent"]:
        workflow.transition(
            db, submission, S.FLAGGED_FOR_REVIEW, actor_id=None, reason="validation_failed"
        )
    else:
        workflow.transition(
            db, submission, S.ARITHMETIC_VALIDATED, actor_id=None, reason="validation_passed"
        )
        workflow.transition(
            db,
            submission,
            S.FLAGGED_FOR_REVIEW if needs_attention else S.CROSS_CHECKED,
            actor_id=None,
            reason="attention_required" if needs_attention else "cross_check_completed",
        )
    db.commit()
    return validation

def _reliable_reference(
    db: Session, submission: EvidenceSubmission
) -> list[dict[str, int | str | None]]:
    """Human-reviewed records of the same election, one per polling unit, excluding this
    polling unit. Only these are trustworthy enough to describe what is typical."""
    rows = db.scalars(
        select(EvidenceSubmission)
        .where(
            EvidenceSubmission.election_id == submission.election_id,
            EvidenceSubmission.polling_unit_id != submission.polling_unit_id,
            EvidenceSubmission.workflow_status.in_([S.REVIEWED, S.VERIFIED]),
        )
        .order_by(EvidenceSubmission.status_changed_at.desc())
    )
    seen: set[uuid.UUID] = set()
    reference = []
    for row in rows:
        if row.polling_unit_id in seen:
            continue
        validation = latest_validation(db, row.id)
        if validation is None or not validation.passed:
            continue
        seen.add(row.polling_unit_id)
        reference.append(_snapshot_values(validation))
    return reference

ReviewAction = str
REVIEW_ACTIONS = ("start", "approve", "reject", "request_correction")

def current_result_hash(db: Session, submission: EvidenceSubmission) -> str | None:
    extraction = latest_extraction(db, submission.id)
    if extraction is None:
        return None
    values = _values(effective_fields(field_history(db, extraction.id)))
    return result_fingerprint(
        canonical_result(
            election_id=submission.election_id,
            polling_unit_id=submission.polling_unit_id,
            template_id=extraction.template_id,
            values=values,
        )
    )

def approvals_for(
    db: Session, submission: EvidenceSubmission, result_hash: str
) -> list[EvidenceReview]:
    history = reviews(db, submission.id)
    last_reset = max(
        (
            i
            for i, r in enumerate(history)
            if r.decision in (ReviewDecision.CORRECTION_REQUESTED, ReviewDecision.REJECTED)
        ),
        default=-1,
    )
    approvals: dict[uuid.UUID, EvidenceReview] = {}
    for review in history[last_reset + 1 :]:
        if review.decision == ReviewDecision.APPROVED and review.result_hash == result_hash:
            approvals.setdefault(review.reviewer_id, review)
    return list(approvals.values())

def review(
    db: Session,
    submission: EvidenceSubmission,
    actor: Principal,
    action: ReviewAction,
    notes: str | None,
    settings: Settings,
) -> EvidenceReview:
    if submission.submitted_by == actor.user_id:
        raise AppError("conflict_of_interest", "You cannot review your own submission.", 403)
    status = S(submission.workflow_status)
    notes = (notes or "").strip()[:4000] or None
    validation = latest_validation(db, submission.id)
    current_hash = current_result_hash(db, submission)
    ensure_user(db, actor)

    def record(decision: ReviewDecision) -> EvidenceReview:
        row = EvidenceReview(
            submission_id=submission.id,
            reviewer_id=actor.user_id,
            decision=decision,
            notes=notes,
            result_hash=current_hash,
            validation_id=validation.id if validation else None,
        )
        db.add(row)
        db.flush()
        append_event(
            db,
            entity_id=submission.id,
            action=AuditAction.REVIEW_RECORDED,
            actor_id=actor.user_id,
            details={
                "review_id": row.id,
                "decision": decision.value,
                "result_hash": current_hash,
                "validation_id": row.validation_id,
                "has_notes": notes is not None,
            },
        )
        return row

    if action == "start":
        if status not in workflow.REVIEWABLE:
            raise AppError(
                "invalid_state", "Only cross-checked or flagged submissions can enter review.", 409
            )
        row = record(ReviewDecision.STARTED)
        workflow.transition(
            db, submission, S.UNDER_HUMAN_REVIEW, actor_id=actor.user_id, reason="review_started"
        )

    elif action == "approve":
        if status not in (S.UNDER_HUMAN_REVIEW, S.REVIEWED):
            raise AppError("invalid_state", "Start the review before approving.", 409)
        if validation is None or validation.result_hash != current_hash:
            raise AppError(
                "stale_validation",
                "Values changed since the last validation. Validate again first.",
                409,
            )
        if not validation.passed:
            raise AppError(
                "validation_failed",
                "This result failed arithmetic or consistency checks. Request a "
                "correction or reject it.",
                409,
            )
        extraction = latest_extraction(db, submission.id)
        assert extraction is not None
        unresolved = sorted(
            key
            for key, row in effective_fields(field_history(db, extraction.id)).items()
            if row.requires_review
        )
        if unresolved:
            raise AppError(
                "unresolved_fields",
                "Confirm or correct every field that needs attention first.",
                409,
                details={"fields": unresolved},
            )
        flagged = bool(
            validation.report.get("warnings")
            or _run_alerts(db, submission.id, validation)
            or (latest_comparison(db, submission.id) or _NO_COMPARISON).has_conflicts
        )
        if flagged and not notes:
            raise AppError(
                "notes_required",
                "Explain how the flagged issues were resolved before approving.",
                422,
            )
        if any(a.reviewer_id == actor.user_id for a in approvals_for(db, submission, current_hash)):
            raise AppError("already_approved", "You have already approved this result.", 409)
        row = record(ReviewDecision.APPROVED)
        if status == S.UNDER_HUMAN_REVIEW:
            workflow.transition(
                db, submission, S.REVIEWED, actor_id=actor.user_id, reason="approved"
            )
        approvals = approvals_for(db, submission, current_hash)
        if len(approvals) >= settings.verification_required_approvals:
            workflow.transition(
                db,
                submission,
                S.VERIFIED,
                actor_id=actor.user_id,
                reason=f"{len(approvals)} independent approvals",
            )

    elif action == "reject":
        if status not in (S.UNDER_HUMAN_REVIEW, S.REVIEWED):
            raise AppError("invalid_state", "Start the review before rejecting.", 409)
        if not notes:
            raise AppError("notes_required", "Give the reason for rejecting this evidence.", 422)
        row = record(ReviewDecision.REJECTED)
        if status == S.REVIEWED:
            workflow.transition(
                db,
                submission,
                S.UNDER_HUMAN_REVIEW,
                actor_id=actor.user_id,
                reason="approval_challenged",
            )
        workflow.transition(db, submission, S.REJECTED, actor_id=actor.user_id, reason="rejected")

    elif action == "request_correction":
        if status not in (S.UNDER_HUMAN_REVIEW, S.REVIEWED):
            raise AppError("invalid_state", "Start the review before requesting a correction.", 409)
        if not notes:
            raise AppError("notes_required", "Describe what needs correcting.", 422)
        row = record(ReviewDecision.CORRECTION_REQUESTED)
        workflow.transition(
            db, submission, S.EXTRACTED, actor_id=actor.user_id, reason="correction_requested"
        )
    else:
        raise AppError("invalid_action", "Unknown review action.", 422)

    db.commit()
    return row

@dataclass(frozen=True)
class _EmptyComparison:
    has_conflicts: bool = False

_NO_COMPARISON = _EmptyComparison()

def _run_alerts(db: Session, submission_id: uuid.UUID, validation: ResultValidation) -> list:
    run_id = validation.report.get("analysis_run_id")
    if not run_id:
        return []
    return [a for a in alerts(db, submission_id) if str(a.analysis_run_id) == run_id]
