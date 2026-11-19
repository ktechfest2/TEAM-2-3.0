"""Built-in accounts: password credentials.

Reached only through the API. Supabase's browser-facing roles get no privileges.

Revision ID: 0005_builtin_accounts
Revises: 0004_incidents_and_channels
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.models import UserCredential

revision: str = "0005_builtin_accounts"
down_revision: str | None = "0004_incidents_and_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    UserCredential.__table__.create(bind=bind, checkfirst=True)
    op.execute("ALTER TABLE public.user_credentials ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        DECLARE r text;
        BEGIN
          FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
              EXECUTE format('REVOKE ALL ON public.user_credentials FROM %I', r);
            END IF;
          END LOOP;
        END $$;
        """
    )
    if not sa.inspect(bind).has_table("user_credentials"):
        raise RuntimeError("user_credentials was not created")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.user_credentials")
