from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.db.models import EvidenceSubmission, ExtractedResultRecord, User

EXPECTED_TABLES = {
    "users",
    "role_assignments",
    "elections",
    "states",
    "lgas",
    "wards",
    "polling_units",
    "evidence_submissions",
    "extracted_result_records",
    "verification_records",
    "audit_events",
    "incident_reports",
    "polling_unit_notices",
    "relocation_reports",
    "election_updates",
    "evidence_images",
    "ocr_extractions",
    "extracted_result_fields",
    "result_validations",
    "submission_comparisons",
    "anomaly_alerts",
    "evidence_reviews",
    "polling_unit_results",
    "polling_unit_result_metrics",
    "incident_attachments",
    "incident_reviews",
    "sms_messages",
    "user_credentials",
}

def test_schema_contains_the_planned_entities():
    assert set(Base.metadata.tables) == EXPECTED_TABLES

def test_sensitive_columns_are_not_on_the_wrong_tables():
    assert "password" not in User.__table__.columns
    assert "verification_status" not in EvidenceSubmission.__table__.columns
    assert "status" not in ExtractedResultRecord.__table__.columns
    assert "verification_status" not in ExtractedResultRecord.__table__.columns

def test_models_compile_for_postgresql():
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        compiled = str(CreateTable(table).compile(dialect=dialect))
        assert table.name in compiled
