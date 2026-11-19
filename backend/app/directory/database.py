"""Directory backed by the database: the register imported by administrators,
elections configured in the console, and updates published by staff."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.db import models
from app.db.enums import NoticeVerificationStatus
from app.directory.repository import Page, PollingUnitQuery, UpdateQuery
from app.evidence.audit import append_event
from app.schemas.common import DataSource
from app.schemas.elections import Election, Party
from app.schemas.locations import Lga, LocationRef, State, Ward
from app.schemas.polling_units import (
    Coordinates,
    OfficialNotice,
    PollingUnitDetail,
    PollingUnitSummary,
    RelocationReportSummary,
)
from app.schemas.updates import ElectionUpdate, ElectionUpdateCreate

REGISTER_SOURCE = DataSource(
    kind="official",
    label="Imported register",
    description=(
        "Polling units imported by VoteTrace administrators. Each unit names the source "
        "document it was imported from."
    ),
)
ENTITY_ELECTION_UPDATE = "election_update"

_UnitRow = tuple[models.PollingUnit, models.Ward, models.Lga, models.State]


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def election_out(row: models.Election) -> Election:
    return Election(
        id=row.id,
        name=row.name,
        election_label=row.election_label,
        election_date=row.election_date,
        template_id=row.template_id,
        parties=[Party(code=p["code"], name=p["name"]) for p in row.parties],
        is_demo=False,
    )


def _summary(row: _UnitRow) -> PollingUnitSummary:
    unit, ward, lga, state = row
    coordinates = None
    if unit.latitude is not None and unit.longitude is not None:
        coordinates = Coordinates(
            latitude=unit.latitude, longitude=unit.longitude, precision="source_reported"
        )
    return PollingUnitSummary(
        id=unit.id,
        code=unit.code,
        name=unit.name,
        state=LocationRef(id=state.id, name=state.name),
        lga=LocationRef(id=lga.id, name=lga.name),
        ward=LocationRef(id=ward.id, name=ward.name),
        address_description=unit.address_description,
        coordinates=coordinates,
        status=unit.status,
        source_name=unit.source_name,
        source_updated_at=_aware(unit.source_updated_at),
        updated_at=_aware(unit.updated_at) or datetime.now(UTC),
    )


def _update_out(row: models.ElectionUpdate) -> ElectionUpdate:
    return ElectionUpdate(
        id=row.id,
        title=row.title,
        description=row.description,
        category=row.category,
        source_name=row.source_name,
        source_url=row.source_url,
        reference=row.reference,
        verification_status=row.verification_status,
        polling_unit_id=row.polling_unit_id,
        published_at=_aware(row.published_at) or row.published_at,
        is_demo=False,
    )


def _units() -> Select[_UnitRow]:
    return (
        select(models.PollingUnit, models.Ward, models.Lga, models.State)
        .join(models.Ward, models.PollingUnit.ward_id == models.Ward.id)
        .join(models.Lga, models.Ward.lga_id == models.Lga.id)
        .join(models.State, models.Lga.state_id == models.State.id)
    )


class DatabaseDirectoryRepository:
    source = REGISTER_SOURCE

    def __init__(self, session_factory: Callable[[], Session] | sessionmaker[Session]) -> None:
        self._session = session_factory

    def list_states(self) -> list[State]:
        with self._session() as db:
            rows = db.scalars(select(models.State).order_by(models.State.name))
            return [State(id=s.id, code=s.code, name=s.name, iso_code=s.iso_code) for s in rows]

    def list_lgas(self, state_id: uuid.UUID) -> list[Lga]:
        with self._session() as db:
            rows = db.scalars(
                select(models.Lga).where(models.Lga.state_id == state_id).order_by(models.Lga.name)
            )
            return [Lga(id=r.id, state_id=r.state_id, code=r.code, name=r.name) for r in rows]

    def list_wards(self, lga_id: uuid.UUID) -> list[Ward]:
        with self._session() as db:
            rows = db.scalars(
                select(models.Ward).where(models.Ward.lga_id == lga_id).order_by(models.Ward.name)
            )
            return [Ward(id=r.id, lga_id=r.lga_id, code=r.code, name=r.name) for r in rows]

    def search_polling_units(
        self, query: PollingUnitQuery, page: int, page_size: int
    ) -> Page[PollingUnitSummary]:
        statement = _units()
        if query.state_id:
            statement = statement.where(models.State.id == query.state_id)
        if query.lga_id:
            statement = statement.where(models.Lga.id == query.lga_id)
        if query.ward_id:
            statement = statement.where(models.Ward.id == query.ward_id)
        if query.status:
            statement = statement.where(models.PollingUnit.status == query.status)
        if query.code:
            statement = statement.where(
                func.upper(models.PollingUnit.code).startswith(query.code.upper(), autoescape=True)
            )
        if query.text:
            needle = " ".join(query.text.casefold().split())
            statement = statement.where(
                func.lower(models.PollingUnit.name).contains(needle, autoescape=True)
                | func.lower(models.PollingUnit.code).contains(needle, autoescape=True)
            )
        with self._session() as db:
            total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
            rows = db.execute(
                statement.order_by(models.PollingUnit.code)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            items = [_summary(tuple(row)) for row in rows]
        return Page(items=items, total=total, page=page, page_size=page_size)

    def get_polling_unit(self, polling_unit_id: uuid.UUID) -> PollingUnitDetail | None:
        with self._session() as db:
            row = db.execute(_units().where(models.PollingUnit.id == polling_unit_id)).first()
            if row is None:
                return None
            notices = db.scalars(
                select(models.PollingUnitNotice)
                .where(models.PollingUnitNotice.polling_unit_id == polling_unit_id)
                .order_by(models.PollingUnitNotice.received_at.desc())
            ).all()
            count, first, last = db.execute(
                select(
                    func.count(),
                    func.min(models.RelocationReport.reported_at),
                    func.max(models.RelocationReport.reported_at),
                ).where(models.RelocationReport.polling_unit_id == polling_unit_id)
            ).one()
        summary = _summary(tuple(row))
        reports = None
        if count and first and last:
            reports = RelocationReportSummary(
                report_count=count,
                first_reported_at=_aware(first) or first,
                last_reported_at=_aware(last) or last,
            )
        return PollingUnitDetail(
            **summary.model_dump(),
            official_notices=[
                OfficialNotice(
                    id=n.id,
                    kind="relocation" if n.kind == "relocation" else "temporary_closure",
                    source_name=n.source_name,
                    source_url=n.source_url,
                    reference=n.reference,
                    new_location_description=n.new_location_description,
                    effective_date=n.effective_date,
                    received_at=_aware(n.received_at) or n.received_at,
                    verification_status=NoticeVerificationStatus(n.verification_status),
                )
                for n in notices
            ],
            relocation_reports=reports,
        )

    def list_all_polling_units(self) -> list[PollingUnitSummary]:
        with self._session() as db:
            rows = db.execute(_units().order_by(models.PollingUnit.code)).all()
            return [_summary(tuple(row)) for row in rows]

    def list_updates(self, query: UpdateQuery, page: int, page_size: int) -> Page[ElectionUpdate]:
        statement = select(models.ElectionUpdate)
        if query.category:
            statement = statement.where(models.ElectionUpdate.category == query.category)
        if query.verification_status:
            statement = statement.where(
                models.ElectionUpdate.verification_status == query.verification_status
            )
        if query.published_from:
            statement = statement.where(
                models.ElectionUpdate.published_at >= _utc(query.published_from)
            )
        if query.published_to:
            statement = statement.where(
                models.ElectionUpdate.published_at <= _utc(query.published_to)
            )
        with self._session() as db:
            total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
            rows = db.scalars(
                statement.order_by(models.ElectionUpdate.published_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            items = [_update_out(row) for row in rows]
        return Page(items=items, total=total, page=page, page_size=page_size)

    def get_update(self, update_id: uuid.UUID) -> ElectionUpdate | None:
        with self._session() as db:
            row = db.get(models.ElectionUpdate, update_id)
            return _update_out(row) if row else None

    def list_elections(self) -> list[Election]:
        with self._session() as db:
            rows = db.scalars(
                select(models.Election).order_by(
                    models.Election.election_date, models.Election.name
                )
            )
            return [election_out(row) for row in rows]

    def get_election(self, election_id: uuid.UUID) -> Election | None:
        with self._session() as db:
            row = db.get(models.Election, election_id)
            return election_out(row) if row else None

    def create_update(
        self, payload: ElectionUpdateCreate, published_by: uuid.UUID
    ) -> ElectionUpdate:
        with self._session() as db:
            if payload.polling_unit_id and not db.get(models.PollingUnit, payload.polling_unit_id):
                raise AppError("not_found", "Polling unit not found.", status_code=404)
            row = models.ElectionUpdate(
                id=uuid.uuid4(),
                title=payload.title.strip(),
                description=payload.description.strip(),
                category=payload.category,
                source_name=payload.source_name.strip(),
                source_url=str(payload.source_url) if payload.source_url else None,
                reference=payload.reference,
                verification_status=payload.verification_status,
                polling_unit_id=payload.polling_unit_id,
                published_at=datetime.now(UTC),
                published_by=published_by,
            )
            db.add(row)
            append_event(
                db,
                entity_type=ENTITY_ELECTION_UPDATE,
                entity_id=row.id,
                action="update.published",
                actor_id=published_by,
                details={
                    "category": payload.category.value,
                    "verification_status": payload.verification_status.value,
                    "source_name": row.source_name,
                },
            )
            db.commit()
            return _update_out(row)
