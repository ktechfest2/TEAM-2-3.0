"""Polling-unit aggregation tables and the state ISO code.

Revision 0001 builds tables from the current models, so on a fresh database these
objects may already exist; every statement here is idempotent. The aggregation tables
are derived data written only by the API inside evidence transactions. Browser-facing
Supabase roles get no access to them; the public reads aggregates through the API.

Revision ID: 0003_result_aggregation
Revises: 0002_append_only
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op
from app.db.models import PollingUnitResult, PollingUnitResultMetric

revision: str = "0003_result_aggregation"
down_revision: str | None = "0002_append_only"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("polling_unit_results", "polling_unit_result_metrics")


def upgrade() -> None:
    op.execute("ALTER TABLE public.states ADD COLUMN IF NOT EXISTS iso_code varchar(8)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_states_iso_code ON public.states (iso_code)")
    bind = op.get_bind()
    for model in (PollingUnitResult, PollingUnitResultMetric):
        model.__table__.create(bind=bind, checkfirst=True)
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
    op.execute("DROP TABLE IF EXISTS public.polling_unit_result_metrics")
    op.execute("DROP TABLE IF EXISTS public.polling_unit_results")
    op.execute("DROP TYPE IF EXISTS result_stream")
    op.execute("DROP TYPE IF EXISTS pu_result_status")
    op.execute("DROP INDEX IF EXISTS public.uq_states_iso_code")
    op.execute("ALTER TABLE public.states DROP COLUMN IF EXISTS iso_code")
