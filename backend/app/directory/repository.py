import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.enums import PollingUnitStatus, UpdateCategory, UpdateVerificationStatus
from app.directory.demo_data import DEMO_SOURCE, DemoDataset, build_demo_dataset
from app.schemas.common import DataSource
from app.schemas.elections import Election
from app.schemas.locations import Lga, State, Ward
from app.schemas.polling_units import PollingUnitDetail, PollingUnitSummary
from app.schemas.updates import ElectionUpdate, ElectionUpdateCreate


@dataclass(frozen=True)
class PollingUnitQuery:
    state_id: uuid.UUID | None = None
    lga_id: uuid.UUID | None = None
    ward_id: uuid.UUID | None = None
    text: str | None = None
    code: str | None = None
    status: PollingUnitStatus | None = None


@dataclass(frozen=True)
class UpdateQuery:
    category: UpdateCategory | None = None
    verification_status: UpdateVerificationStatus | None = None
    published_from: datetime | None = None
    published_to: datetime | None = None


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total / self.page_size))


class PersistenceUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "persistence_unavailable",
            "Publishing requires the database-backed directory, which is not configured.",
            status_code=503,
        )


class DirectoryRepository(Protocol):
    source: DataSource

    def list_states(self) -> list[State]: ...
    def list_lgas(self, state_id: uuid.UUID) -> list[Lga]: ...
    def list_wards(self, lga_id: uuid.UUID) -> list[Ward]: ...
    def search_polling_units(
        self, query: PollingUnitQuery, page: int, page_size: int
    ) -> Page[PollingUnitSummary]: ...
    def get_polling_unit(self, polling_unit_id: uuid.UUID) -> PollingUnitDetail | None: ...
    def list_all_polling_units(self) -> list[PollingUnitSummary]: ...
    def list_updates(
        self, query: UpdateQuery, page: int, page_size: int
    ) -> Page[ElectionUpdate]: ...
    def get_update(self, update_id: uuid.UUID) -> ElectionUpdate | None: ...
    def list_elections(self) -> list[Election]: ...
    def get_election(self, election_id: uuid.UUID) -> Election | None: ...
    def create_update(
        self, payload: ElectionUpdateCreate, published_by: uuid.UUID
    ) -> ElectionUpdate: ...


def _paginate[T](items: list[T], page: int, page_size: int) -> Page[T]:
    start = (page - 1) * page_size
    return Page(
        items=items[start : start + page_size], total=len(items), page=page, page_size=page_size
    )


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


class DemoDirectoryRepository:
    """Serves the fictional demo dataset. Read-only: publishing is refused."""

    source = DEMO_SOURCE

    def __init__(self, dataset: DemoDataset | None = None) -> None:
        self._data = dataset or build_demo_dataset()

    def list_states(self) -> list[State]:
        return sorted(self._data.states, key=lambda s: s.name)

    def list_lgas(self, state_id: uuid.UUID) -> list[Lga]:
        lgas = (lga for lga in self._data.lgas if lga.state_id == state_id)
        return sorted(lgas, key=lambda lga: lga.name)

    def list_wards(self, lga_id: uuid.UUID) -> list[Ward]:
        return sorted((w for w in self._data.wards if w.lga_id == lga_id), key=lambda w: w.name)

    def search_polling_units(
        self, query: PollingUnitQuery, page: int, page_size: int
    ) -> Page[PollingUnitSummary]:
        needle = _normalise(query.text) if query.text else None
        code = query.code.upper() if query.code else None
        matches: list[PollingUnitSummary] = []
        for unit in self._data.polling_units:
            if query.state_id and unit.state.id != query.state_id:
                continue
            if query.lga_id and unit.lga.id != query.lga_id:
                continue
            if query.ward_id and unit.ward.id != query.ward_id:
                continue
            if query.status and unit.status != query.status:
                continue
            if code and not unit.code.upper().startswith(code):
                continue
            if needle and needle not in _normalise(f"{unit.name} {unit.code}"):
                continue
            matches.append(
                PollingUnitSummary(**unit.model_dump(include=set(PollingUnitSummary.model_fields)))
            )
        matches.sort(key=lambda u: u.code)
        return _paginate(matches, page, page_size)

    def get_polling_unit(self, polling_unit_id: uuid.UUID) -> PollingUnitDetail | None:
        return next((u for u in self._data.polling_units if u.id == polling_unit_id), None)

    def list_all_polling_units(self) -> list[PollingUnitSummary]:
        fields = set(PollingUnitSummary.model_fields)
        return [
            PollingUnitSummary(**unit.model_dump(include=fields))
            for unit in sorted(self._data.polling_units, key=lambda u: u.code)
        ]

    def list_updates(self, query: UpdateQuery, page: int, page_size: int) -> Page[ElectionUpdate]:
        items = [
            u
            for u in self._data.updates
            if (query.category is None or u.category == query.category)
            and (
                query.verification_status is None
                or u.verification_status == query.verification_status
            )
            and (query.published_from is None or u.published_at >= query.published_from)
            and (query.published_to is None or u.published_at <= query.published_to)
        ]
        items.sort(key=lambda u: u.published_at, reverse=True)
        return _paginate(items, page, page_size)

    def get_update(self, update_id: uuid.UUID) -> ElectionUpdate | None:
        return next((u for u in self._data.updates if u.id == update_id), None)

    def list_elections(self) -> list[Election]:
        return sorted(self._data.elections, key=lambda e: (e.election_date, e.name))

    def get_election(self, election_id: uuid.UUID) -> Election | None:
        return next((e for e in self._data.elections if e.id == election_id), None)

    def create_update(
        self, payload: ElectionUpdateCreate, published_by: uuid.UUID
    ) -> ElectionUpdate:
        raise PersistenceUnavailableError()


@lru_cache
def _demo_repository() -> DemoDirectoryRepository:
    return DemoDirectoryRepository()


def get_directory() -> DirectoryRepository:
    if get_settings().directory_source == "demo":
        return _demo_repository()
    from app.directory.database import DatabaseDirectoryRepository
    from app.evidence.db import evidence_session_factory

    return DatabaseDirectoryRepository(evidence_session_factory())
