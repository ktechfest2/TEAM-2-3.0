"""Incident reporting, incident reviews and SMS message records.

Revision 0001 builds tables from the current models, so on a fresh database these
objects may already exist; every statement here is idempotent. A database created
from an earlier 0001 has the prototype `incident_reports` table (no `reference`
column). No route ever wrote to it, so it is replaced together with its enum types.

All four tables are reached only through the API. Supabase's browser-facing roles get
no privileges, and history tables refuse UPDATE and DELETE like the evidence history.

Revision ID: 0004_incidents_and_channels
Revises: 0003_result_aggregation
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.models import IncidentAttachment, IncidentReport, IncidentReview, SmsMessage

revision: str = "0004_incidents_and_channels"
down_revision: str | None = "0003_result_aggregation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("incident_reports", "incident_attachments", "incident_reviews", "sms_messages")
HISTORY_TABLES = ("incident_attachments", "incident_reviews", "sms_messages")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("incident_reports"):
        columns = {column["name"] for column in inspector.get_columns("incident_reports")}
        if "reference" not in columns:
            op.execute("DROP TABLE public.incident_reports")
            op.execute("DROP TYPE IF EXISTS incident_status")
            op.execute("DROP TYPE IF EXISTS incident_category")
    for model in (IncidentReport, IncidentAttachment, IncidentReview, SmsMessage):
        model.__table__.create(bind=bind, checkfirst=True)
    for table in HISTORY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON public.{table}")
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION verivote_refuse_history_change()"
        )
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        DO $$
        DECLARE r text;
        BEGIN
          FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
              EXECUTE format('REVOKE ALL ON {", ".join(f"public.{t}" for t in TABLES)}
                              FROM %I', r);
            END IF;
          END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    for table in HISTORY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON public.{table}")
    op.execute("DROP TABLE IF EXISTS public.sms_messages")
    op.execute("DROP TABLE IF EXISTS public.incident_reviews")
    op.execute("DROP TABLE IF EXISTS public.incident_attachments")
    op.execute("DROP TABLE IF EXISTS public.incident_reports")
    op.execute("DROP TYPE IF EXISTS incident_severity")
    op.execute("DROP TYPE IF EXISTS incident_status")
    op.execute("DROP TYPE IF EXISTS incident_category")
