"""Unit tests for the evidence engines. All inputs are generated TEST DATA."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.db.enums import AlertCategory, EvidenceStatus
from app.db.models import AppendOnlyViolationError, AuditEvent
from app.evidence import workflow
from app.evidence.ai import HEADLINE, analyze
from app.evidence.ai.demo import DEMO_LABEL, run_demo
from app.evidence.ai.statistical import statistical_analysis
from app.evidence.audit import append_event, load_chain, verify_chain
from app.evidence.comparison import SubmissionSnapshot, compare_submissions
from app.evidence.db import create_dev_engine
from app.evidence.field_mapping import map_fields, parse_count
from app.evidence.hashing import (
    canonical_json,
    canonical_result,
    difference_hash,
    hamming_distance,
    result_fingerprint,
    sha256_bytes,
)
from app.evidence.image_validation import validate_image
from app.evidence.storage import IntegrityError, LocalStorage, read_verified
from app.evidence.templates import get_template
from app.evidence.validation import SubmissionContext, validate_result
from app.schemas.elections import Party
from tests.evidence_support import make_sheet_image, reencode, sheet_lines, sheet_tokens

TEMPLATE = get_template("generic-pu-result-v1")
PARTIES = [Party(code=c, name=f"Test Party {c}") for c in ("PA", "PB", "PC", "PD")]
CONTEXT = SubmissionContext(polling_unit_code="TEST/01/02/003", election_label="GOVERNORSHIP")
SETTINGS = Settings(_env_file=None)

def check_upload(data, name, mime, settings=SETTINGS):
    return validate_image(data, filename=name, declared_content_type=mime, settings=settings)

def good_values(**overrides):
    values = {
        "polling_unit_code": "TEST/01/02/003",
        "election_label": "GOVERNORSHIP",
        "registered_voters": 800,
        "accredited_voters": 300,
        "rejected_votes": 10,
        "total_valid_votes": 280,
        "total_votes_cast": 290,
        "party:PA": 120,
        "party:PB": 90,
        "party:PC": 50,
        "party:PD": 20,
    }
    values.update(overrides)
    return values

def test_sha256_of_original_bytes_is_stable_and_sensitive():
    data = make_sheet_image(1)
    assert sha256_bytes(data) == sha256_bytes(bytes(data))
    assert sha256_bytes(data) != sha256_bytes(data[:-1] + b"\x00")
    assert len(sha256_bytes(data)) == 64

def test_result_fingerprint_is_deterministic_and_order_independent():
    election, unit = uuid.uuid4(), uuid.uuid4()
    a = canonical_result(
        election_id=election, polling_unit_id=unit, template_id="t", values={"b": 2, "a": 1}
    )
    b = canonical_result(
        election_id=election, polling_unit_id=unit, template_id="t", values={"a": 1, "b": 2}
    )
    assert result_fingerprint(a) == result_fingerprint(b)
    c = canonical_result(
        election_id=election, polling_unit_id=unit, template_id="t", values={"a": 1, "b": 3}
    )
    assert result_fingerprint(a) != result_fingerprint(c)

def test_canonical_json_rejects_floats():
    with pytest.raises(TypeError):
        canonical_json({"x": 0.5})

def test_perceptual_hash_survives_reencoding_but_differs_between_images():
    import cv2
    import numpy as np

    def phash(data: bytes) -> str:
        gray = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
        return difference_hash(gray)

    original = make_sheet_image(3)
    assert hamming_distance(phash(original), phash(reencode(original, 60))) <= 6
    assert hamming_distance(phash(original), phash(make_sheet_image(99))) > 6

def test_valid_jpeg_png_and_webp_are_accepted():
    for fmt, name, mime in (
        ("JPEG", "a.jpg", "image/jpeg"),
        ("PNG", "a.png", "image/png"),
        ("WEBP", "a.webp", "image/webp"),
    ):
        result = check_upload(make_sheet_image(1, fmt=fmt), name, mime, SETTINGS)
        assert result.content_type == mime
        assert (result.width, result.height) == (900, 1200)

def test_extension_alone_is_not_trusted():
    with pytest.raises(AppError) as error:
        check_upload(b"%PDF-1.7 not an image" * 100, "sheet.jpg", "image/jpeg", SETTINGS)
    assert error.value.code == "unsupported_type"

def test_declared_type_must_match_actual_content():
    png = make_sheet_image(1, fmt="PNG")
    with pytest.raises(AppError) as error:
        check_upload(png, "sheet.jpg", "image/jpeg", SETTINGS)
    assert error.value.code == "type_mismatch"

def test_truncated_image_is_rejected():
    data = make_sheet_image(1)
    with pytest.raises(AppError) as error:
        check_upload(data[: len(data) // 3], "a.jpg", "image/jpeg", SETTINGS)
    assert error.value.code == "invalid_image"

def test_too_small_and_too_large_files_are_rejected():
    tiny = make_sheet_image(1, size=(200, 200))
    with pytest.raises(AppError) as error:
        check_upload(tiny, "a.jpg", "image/jpeg", SETTINGS)
    assert error.value.code == "invalid_image"

    limited = Settings(_env_file=None, evidence_max_bytes=100_000)
    big = make_sheet_image(1) + b"\x00" * 120_000
    with pytest.raises(AppError) as error:
        check_upload(big, "a.jpg", "image/jpeg", limited)
    assert error.value.status_code == 413

def test_local_storage_is_write_once_and_verified_on_read(tmp_path):
    storage = LocalStorage(str(tmp_path), "evidence")
    data = make_sheet_image(1)
    storage.put("originals/x.jpg", data, "image/jpeg")
    assert read_verified(storage, "originals/x.jpg", sha256_bytes(data)) == data
    with pytest.raises(FileExistsError):
        storage.put("originals/x.jpg", b"replacement", "image/jpeg")
    with pytest.raises(ValueError):
        storage.put("../escape.jpg", data, "image/jpeg")

    path = tmp_path / "evidence" / "originals" / "x.jpg"
    path.chmod(0o600)
    path.write_bytes(data + b"tampered")
    with pytest.raises(IntegrityError):
        read_verified(storage, "originals/x.jpg", sha256_bytes(data))

def test_fields_are_mapped_from_positioned_tokens():
    tokens = sheet_tokens(sheet_lines("TEST/01/02/003"))
    fields = {f.key: f for f in map_fields(tokens, TEMPLATE, PARTIES, 0.85)}
    assert fields["accredited_voters"].value_int == 300
    assert fields["party:PA"].value_int == 120
    assert fields["polling_unit_code"].value_text == "TEST/01/02/003"
    assert fields["total_votes_cast"].value_int == 290
    assert fields["accredited_voters"].bbox is not None
    assert fields["accredited_voters"].source_text == "300"
    assert not any(f.requires_review for f in fields.values())

def test_low_confidence_fields_require_review():
    tokens = sheet_tokens(sheet_lines("TEST/01/02/003"), overrides={"300": 0.41})
    fields = {f.key: f for f in map_fields(tokens, TEMPLATE, PARTIES, 0.85)}
    assert fields["accredited_voters"].requires_review
    assert "low_confidence" in fields["accredited_voters"].review_reasons

def test_ambiguous_characters_are_flagged_not_trusted():
    value, substitutions = parse_count("1O5")
    assert value == 105 and substitutions == ["O→0"]
    lines = sheet_lines("TEST/01/02/003")
    lines = [line.replace("PB 90", "PB 9O") for line in lines]
    fields = {f.key: f for f in map_fields(sheet_tokens(lines), TEMPLATE, PARTIES, 0.85)}
    assert fields["party:PB"].value_int == 90
    assert "ambiguous_characters" in fields["party:PB"].review_reasons
    assert fields["party:PB"].confidence < 0.85

def test_missing_fields_are_reported():
    lines = [line for line in sheet_lines("TEST/01/02/003") if not line.startswith("REJECTED")]
    fields = {f.key: f for f in map_fields(sheet_tokens(lines), TEMPLATE, PARTIES, 0.85)}
    assert fields["rejected_votes"].value_int is None
    assert fields["rejected_votes"].review_reasons == ["not_found"]

def test_parties_come_from_election_configuration():
    two = [Party(code="ZX", name="Test Party ZX"), Party(code="QY", name="Test Party QY")]
    lines = ["ZX 40", "QY 2", "TOTAL VALID VOTES 42"]
    fields = {f.key: f for f in map_fields(sheet_tokens(lines), TEMPLATE, two, 0.85)}
    assert fields["party:ZX"].value_int == 40
    assert "party:PA" not in fields

def check(report, rule_id):
    return next(c for c in report["checks"] if c["rule_id"] == rule_id)

def test_consistent_result_passes_with_disclaimer():
    report = validate_result(good_values(), TEMPLATE, PARTIES, CONTEXT, [])
    assert report["is_consistent"]
    assert report["failed"] == []
    assert "do not prove" in report["disclaimer"]

def test_valid_votes_must_equal_party_sum():
    report = validate_result(
        good_values(total_valid_votes=281, total_votes_cast=291), TEMPLATE, PARTIES, CONTEXT, []
    )
    assert "valid_votes_equal_party_sum" in report["failed"]
    assert check(report, "valid_votes_equal_party_sum")["expected"] == 280

def test_cast_must_equal_valid_plus_rejected():
    report = validate_result(good_values(total_votes_cast=300), TEMPLATE, PARTIES, CONTEXT, [])
    assert "cast_equals_valid_plus_rejected" in report["failed"]

def test_cast_must_not_exceed_accredited():
    report = validate_result(good_values(accredited_voters=200), TEMPLATE, PARTIES, CONTEXT, [])
    assert "cast_not_above_accredited" in report["failed"]

def test_missing_required_and_negative_values_fail():
    report = validate_result(
        good_values(rejected_votes=None, **{"party:PA": -4}), TEMPLATE, PARTIES, CONTEXT, []
    )
    assert "rejected_votes" in report["missing_fields"]
    assert "required_fields" in report["failed"]
    assert "non_negative_integers" in report["failed"]
    assert check(report, "cast_equals_valid_plus_rejected")["outcome"] == "not_evaluated"

def test_polling_unit_mismatch_is_an_error_and_election_mismatch_a_warning():
    report = validate_result(
        good_values(polling_unit_code="TEST/09/09/999", election_label="SENATE"),
        TEMPLATE,
        PARTIES,
        CONTEXT,
        [],
    )
    assert "polling_unit_matches_submission" in report["failed"]
    assert "election_matches_submission" in report["warnings"]

def test_attention_fields_are_reported():
    report = validate_result(good_values(), TEMPLATE, PARTIES, CONTEXT, ["party:PB"])
    assert report["attention_fields"] == ["party:PB"]

def snap(values, *, submitter=None, sha=None, phash="0f0f0f0f0f0f0f0f", minutes=0):
    return SubmissionSnapshot(
        id=uuid.uuid4(),
        submitted_by=submitter or uuid.uuid4(),
        received_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes),
        original_sha256=sha or uuid.uuid4().hex * 2,
        perceptual_hash=phash,
        values=values,
    )

FIELDS = ["total_valid_votes", "party:PA", "party:PB"]

def test_comparison_flags_the_differing_submission_without_blame():
    a = snap({"party:PA": 120, "party:PB": 90, "total_valid_votes": 210}, phash="0000000000000000")
    b = snap(
        {"party:PA": 120, "party:PB": 90, "total_valid_votes": 210},
        phash="ffffffffffffffff",
        minutes=1,
    )
    c = snap(
        {"party:PA": 170, "party:PB": 90, "total_valid_votes": 260},
        phash="00000000ffffffff",
        minutes=2,
    )
    report = compare_submissions(c, [a, b], FIELDS, datetime.now(UTC))
    pa = next(f for f in report["fields"] if f["field_key"] == "party:PA")
    assert pa["status"] == "conflict"
    assert pa["most_common_value"] == "120"
    assert pa["differing_submissions"] == [str(c.id)]
    assert "party:PB" in report["matching_fields"]
    assert report["recommendation"]["code"] == "review_conflicts"
    text = str(report).lower()
    assert "fraud" not in text

def test_comparison_detects_identical_files_near_duplicates_and_same_submitter():
    person = uuid.uuid4()
    a = snap({"party:PA": 1}, submitter=person, sha="a" * 64, phash="0000000000000000")
    b = snap({"party:PA": 1}, submitter=person, sha="a" * 64, phash="0000000000000000")
    c = snap({"party:PA": 1}, sha="c" * 64, phash="0000000000000003")
    report = compare_submissions(a, [b, c], ["party:PA"], datetime.now(UTC))
    kinds = sorted(d["type"] for d in report["duplicates"])
    assert "identical_file" in kinds
    assert "same_submitter" in kinds
    assert "near_duplicate_image" in kinds
    assert report["recommendation"]["code"] == "review_dependence"

def test_single_submission_cannot_be_cross_checked():
    report = compare_submissions(snap({"party:PA": 1}), [], ["party:PA"], datetime.now(UTC))
    assert report["recommendation"]["code"] == "no_comparison"

def test_ocr_uncertainty_alert_explains_fields_and_never_claims_fraud():
    fields = [
        {
            "field_key": "party:PA",
            "value": 120,
            "confidence": 0.3,
            "origin": "ocr",
            "requires_review": True,
            "review_reasons": ["low_confidence"],
            "ambiguous_characters": [],
        },
        {
            "field_key": "party:PB",
            "value": 90,
            "confidence": 0.99,
            "origin": "ocr",
            "requires_review": False,
            "review_reasons": [],
            "ambiguous_characters": [],
        },
    ]
    result = analyze(
        fields=fields,
        comparison=None,
        target_values={},
        reference_values=[],
        party_keys=["party:PA"],
        min_samples=30,
        threshold=0.85,
    )
    assert len(result.alerts) == 1
    alert = result.alerts[0]
    assert alert.category == AlertCategory.OCR_UNCERTAINTY
    assert alert.headline == HEADLINE == "Anomaly detected. Human review required."
    assert alert.fields == ["party:PA"]
    assert "not a finding of fraud" in alert.recommendation
    assert result.statistical["status"] == "insufficient_data"

def test_statistical_analysis_requires_enough_reliable_records():
    summary, alert = statistical_analysis(
        good_values(), [good_values()] * 5, ["party:PA", "party:PB"], min_samples=30
    )
    assert summary["status"] == "insufficient_data"
    assert alert is None

def test_statistical_demo_is_labelled_and_records_model_version():
    output = run_demo()
    assert output["label"] == DEMO_LABEL
    assert output["summary"]["is_demo"] is True
    assert output["summary"]["model_version"].startswith("sklearn-")
    assert output["summary"]["variables"]
    assert output["alert"] is not None
    assert output["alert"]["is_demo"] is True
    assert "fraud" not in output["alert"]["summary"].lower()

@pytest.fixture()
def session(tmp_path):
    engine = create_dev_engine(str(tmp_path / "unit.sqlite3"))
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        yield db

def test_audit_chain_links_and_detects_tampering(session):
    entity = uuid.uuid4()
    for index in range(3):
        append_event(
            session, entity_id=entity, action="test.event", actor_id=None, details={"n": index}
        )
    session.commit()
    chain = load_chain(session, entity)
    assert [e.sequence for e in chain] == [1, 2, 3]
    assert chain[1].previous_hash == chain[0].event_hash
    assert verify_chain(chain).valid

    # Simulate a privileged edit that bypasses the ORM guard.
    session.connection().exec_driver_sql(
        "UPDATE audit_events SET details = '{\"n\": 99}' WHERE sequence = 2"
    )
    session.expire_all()
    result = verify_chain(load_chain(session, entity))
    assert not result.valid
    assert result.broken_at_sequence == 2
    assert result.problem == "content_altered"

def test_audit_events_cannot_be_updated_or_deleted_through_the_application(session):
    event = append_event(session, entity_id=uuid.uuid4(), action="test.event", actor_id=None)
    session.commit()
    event.action = "edited"
    with pytest.raises(AppendOnlyViolationError):
        session.commit()
    session.rollback()
    stored = session.get(AuditEvent, event.id)
    session.delete(stored)
    with pytest.raises(AppendOnlyViolationError):
        session.commit()

def test_workflow_never_jumps_to_verified():
    S = EvidenceStatus
    for status in S:
        if status != S.REVIEWED:
            assert not workflow.can_transition(status, S.VERIFIED), status
    assert workflow.TRANSITIONS[S.VERIFIED] == frozenset()
    assert workflow.TRANSITIONS[S.REJECTED] == frozenset()
    assert not workflow.can_transition(S.EXTRACTED, S.REVIEWED)
    assert not workflow.can_transition(S.CROSS_CHECKED, S.REVIEWED)

def test_rapidocr_lines_become_word_tokens_and_split_labels_still_map():
    from app.evidence.field_mapping import map_fields
    from app.evidence.ocr import OcrToken, RapidOcrProvider
    from app.evidence.templates import load_templates

    def boxes(starts: list[int], width: int = 18, top: int = 48) -> list:
        return [[[x, top], [x + width, top], [x + width, top + 29], [x, top + 29]] for x in starts]

    # Character boxes as the recogniser reports them: no spaces, wider gaps between words.
    chars = list("TOTALVALIDVOTES:412")
    starts = [42, 63, 87, 111, 130, 164, 183, 207, 224, 241, 275, 299, 323, 342, 366, 383, 400]
    starts += [424, 443]
    line = [boxes([42])[0], "".join(chars), 0.99, boxes(starts), chars]
    words = RapidOcrProvider()._words(line, "line-0")
    assert [w.text for w in words] == ["TOTAL", "VALID", "VOTES:", "412"]

    # A label the engine split mid-word ("REJ ECTED") or merged still maps.
    template = next(iter(load_templates().values()))
    alias = next(f for f in template.fields if f.key == "rejected_votes").aliases[0].upper()
    head, rest = alias[:3], alias[3:].replace(" ", "")
    tokens = [
        *words,
        OcrToken(head, 0.95, 40, 150, 50, 29, "line-1"),
        OcrToken(rest + ":", 0.95, 100, 150, 200, 29, "line-1"),
        OcrToken("7", 0.95, 320, 150, 20, 29, "line-1"),
    ]
    mapped = {m.key: m for m in map_fields(tokens, template, [], 0.85)}
    assert mapped["total_valid_votes"].value_int == 412
    assert mapped["rejected_votes"].value_int == 7

def test_rapidocr_trusts_recogniser_spaces_over_character_gaps():
    from app.evidence.ocr import RapidOcrProvider

    # Wide capitals leave gaps inside a word; the recogniser's own space marks the break.
    chars = list("UNIT 503")
    lefts = [283, 314, 340, 361, 381, 400, 418, 440]
    boxes = [[[x, 48], [x + 20, 48], [x + 20, 77], [x, 77]] for x in lefts]
    line = [boxes[0], "UNIT 503", 0.99, boxes, chars]
    assert [w.text for w in RapidOcrProvider()._words(line, "line-0")] == ["UNIT", "503"]

def test_party_figure_on_a_separate_ocr_line_and_misread_label_letters_still_map():
    from app.evidence.ocr import OcrToken
    from app.schemas.elections import Party

    template = get_template("generic-pu-result-v1")
    tokens = [
        OcrToken("Polling", 0.98, 82, 300, 112, 30, "line-0"),
        OcrToken("unit", 0.98, 213, 300, 62, 30, "line-0"),
        OcrToken("c0de:", 0.98, 290, 300, 93, 30, "line-0"),
        OcrToken("AB-01-02-003", 0.98, 398, 300, 300, 30, "line-0"),
        # The engine returned the party code and its figure as two separate lines.
        OcrToken("PA", 0.99, 80, 600, 56, 30, "line-1"),
        OcrToken("201", 0.99, 401, 602, 63, 30, "line-2"),
        OcrToken("PB", 0.99, 80, 700, 56, 30, "line-3"),
        OcrToken("143", 0.99, 405, 701, 55, 30, "line-4"),
    ]
    parties = [Party(code="PA", name="Party A"), Party(code="PB", name="Party B")]
    mapped = {m.key: m for m in map_fields(tokens, template, parties, 0.85)}
    assert mapped["polling_unit_code"].value_text == "AB-01-02-003"
    assert mapped["party:PA"].value_int == 201
    assert mapped["party:PB"].value_int == 143
