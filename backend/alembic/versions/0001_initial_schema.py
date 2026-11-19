"""Create the initial VeriVote schema from the SQLAlchemy metadata.

This revision has not been applied to any deployed database, so pre-release
schema work (including the evidence engine tables) is consolidated here.
Once a database has been upgraded past this revision, every schema change
must be an explicit new revision instead.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op
from app.db import models  # noqa: F401
from app.db.base import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Supabase projects often enable these from the dashboard. IF NOT EXISTS
    # keeps the migration safe where the extensions are already present.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
