"""Database-backed directory: election configuration and polling-unit coordinates.

Elections gain the fields the API already exposes (sheet label, template, parties).
Polling units store latitude and longitude as plain columns so the importer runs on
any backend; a trigger keeps the PostGIS `location` column in step for spatial work.
Every statement is idempotent because 0001 builds the schema from current metadata.

Revision ID: 0006_portable_directory
Revises: 0005_builtin_accounts
Create Date: 2026-11-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_portable_directory"
down_revision: str | None = "0005_builtin_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.elections
          ADD COLUMN IF NOT EXISTS election_label varchar(200) NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS template_id varchar(80) NOT NULL DEFAULT 'generic_pu_result_v1',
          ADD COLUMN IF NOT EXISTS parties jsonb NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES public.users (id);
        ALTER TABLE public.polling_units
          ADD COLUMN IF NOT EXISTS latitude double precision,
          ADD COLUMN IF NOT EXISTS longitude double precision,
          ADD COLUMN IF NOT EXISTS location geometry(Point, 4326);
        CREATE INDEX IF NOT EXISTS ix_polling_units_location
          ON public.polling_units USING gist (location);
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'latitude_range') THEN
            ALTER TABLE public.polling_units ADD CONSTRAINT latitude_range
              CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90);
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'longitude_range') THEN
            ALTER TABLE public.polling_units ADD CONSTRAINT longitude_range
              CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180);
          END IF;
        END $$;
        UPDATE public.polling_units
           SET latitude = ST_Y(location), longitude = ST_X(location)
         WHERE location IS NOT NULL AND latitude IS NULL;

        CREATE OR REPLACE FUNCTION public.polling_units_sync_location() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.latitude IS NULL OR NEW.longitude IS NULL THEN
            NEW.location := NULL;
          ELSE
            NEW.location := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326);
          END IF;
          RETURN NEW;
        END $$;
        DROP TRIGGER IF EXISTS polling_units_sync_location ON public.polling_units;
        CREATE TRIGGER polling_units_sync_location
          BEFORE INSERT OR UPDATE OF latitude, longitude ON public.polling_units
          FOR EACH ROW EXECUTE FUNCTION public.polling_units_sync_location();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS polling_units_sync_location ON public.polling_units;
        DROP FUNCTION IF EXISTS public.polling_units_sync_location();
        ALTER TABLE public.polling_units
          DROP CONSTRAINT IF EXISTS latitude_range,
          DROP CONSTRAINT IF EXISTS longitude_range,
          DROP COLUMN IF EXISTS latitude,
          DROP COLUMN IF EXISTS longitude;
        ALTER TABLE public.elections
          DROP COLUMN IF EXISTS election_label,
          DROP COLUMN IF EXISTS template_id,
          DROP COLUMN IF EXISTS parties,
          DROP COLUMN IF EXISTS created_by;
        """
    )
