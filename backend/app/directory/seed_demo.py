"""Copy the fictional demo directory into Postgres so evidence foreign keys resolve
when DATABASE_URL points at a development database.

    python -m app.directory.seed_demo

Development only. It refuses to run in production and inserts only rows that are
missing. Every name it writes is labelled as fictional demo data."""

from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db.enums import ElectionStatus
from app.db.models import Election, Lga, PollingUnit, State, Ward
from app.db.session import get_session_factory
from app.directory.demo_data import build_demo_dataset


def seed() -> dict[str, int]:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("Refusing to seed demo data in production.")
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set; the SQLite dev store needs no seeding.")
    data = build_demo_dataset()
    counts: dict[str, int] = {}
    with get_session_factory()() as db:

        def upsert(model, rows: list[dict]) -> None:
            if rows:
                db.execute(insert(model).values(rows).on_conflict_do_nothing())
            counts[model.__tablename__] = len(rows)

        upsert(
            State,
            [
                {"id": s.id, "code": s.code, "name": s.name, "iso_code": s.iso_code}
                for s in data.states
            ],
        )
        upsert(
            Lga,
            [
                {"id": x.id, "state_id": x.state_id, "code": x.code, "name": x.name}
                for x in data.lgas
            ],
        )
        upsert(
            Ward,
            [{"id": w.id, "lga_id": w.lga_id, "code": w.code, "name": w.name} for w in data.wards],
        )
        upsert(
            PollingUnit,
            [
                {
                    "id": u.id,
                    "ward_id": u.ward.id,
                    "code": u.code,
                    "name": u.name,
                    "address_description": u.address_description,
                    "status": u.status,
                    "source_name": u.source_name,
                }
                for u in data.polling_units
            ],
        )
        upsert(
            Election,
            [
                {
                    "id": e.id,
                    "name": e.name,
                    "election_date": e.election_date,
                    "status": ElectionStatus.SCHEDULED,
                }
                for e in data.elections
            ],
        )
        db.commit()
    return counts


if __name__ == "__main__":
    for table, count in seed().items():
        print(f"{table}: {count} demo rows ensured")
