"""Refuse UPDATE and DELETE on history tables at the database level, and close
evidence tables to Supabase's browser-facing roles.

The application ORM already refuses these operations. These triggers also stop
raw SQL issued by the application role or a compromised client key. They are
tamper-resistance for ordinary roles only: a database superuser or the table
owner can disable triggers, which is why audit events are also hash-chained.

Revision ID: 0002_append_only
Revises: 0001_initial
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_append_only"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HISTORY_TABLES = (
    "evidence_images",
    "ocr_extractions",
    "extracted_result_fields",
    "result_validations",
    "submission_comparisons",
    "anomaly_alerts",
    "evidence_reviews",
    "verification_records",
    "audit_events",
)
EVIDENCE_TABLES = ("evidence_submissions", *HISTORY_TABLES[:7], "audit_events")


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION verivote_refuse_history_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION '% rows are append-only', TG_TABLE_NAME
            USING ERRCODE = 'insufficient_privilege';
        END;
        $$;
        """
    )
    for table in HISTORY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION verivote_refuse_history_change()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON public.{table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION verivote_refuse_history_change()"
        )
    # Evidence is reached only through the API. Supabase's browser-facing roles get
    # no table privileges, and RLS without policies denies them every row.
    for table in EVIDENCE_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        DO $$
        DECLARE r text;
        BEGIN
          FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
              EXECUTE format('REVOKE ALL ON {", ".join(f"public.{t}" for t in EVIDENCE_TABLES)}
                              FROM %I', r);
            END IF;
          END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    for table in EVIDENCE_TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
    for table in HISTORY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON public.{table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON public.{table}")
    op.execute("DROP FUNCTION IF EXISTS verivote_refuse_history_change()")
