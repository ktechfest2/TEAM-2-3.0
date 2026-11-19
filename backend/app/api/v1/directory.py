import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.db.enums import PollingUnitStatus, Role, UpdateCategory, UpdateVerificationStatus
from app.directory.repository import (
    DirectoryRepository,
    Page,
    PollingUnitQuery,
    UpdateQuery,
    get_directory,
)
from app.schemas.common import ItemResponse, ListResponse, PageResponse
from app.schemas.elections import Election
from app.schemas.locations import Lga, State, Ward
from app.schemas.polling_units import PollingUnitDetail, PollingUnitSummary
from app.schemas.updates import ElectionUpdate, ElectionUpdateCreate

router = APIRouter()
admin_router = APIRouter(prefix="/admin", tags=["admin"])

Directory = Annotated[DirectoryRepository, Depends(get_directory)]
PageNumber = Annotated[int, Query(ge=1, le=1000)]
PageSize = Annotated[int, Query(ge=1, le=50)]

# Letters (any script), digits, spaces and common punctuation in place names.
_SEARCH_TEXT = r"^[\w\s\-'.,/()]+$"
_CODE = r"^[A-Za-z0-9-]{2,24}$"


def _now() -> datetime:
    return datetime.now(UTC)


def _page[T](page: Page[T], directory: DirectoryRepository) -> PageResponse[T]:
    return PageResponse[T](
        items=page.items,
        page=page.page,
        page_size=page.page_size,
        total=page.total,
        total_pages=page.total_pages,
        data_source=directory.source,
        generated_at=_now(),
    )


def _not_found(what: str) -> AppError:
    return AppError("not_found", f"{what} not found.", status_code=404)


@router.get("/elections", response_model=ListResponse[Election], tags=["elections"])
def list_elections(directory: Directory) -> ListResponse[Election]:
    return ListResponse[Election](
        items=directory.list_elections(), data_source=directory.source, generated_at=_now()
    )


@router.get("/locations/states", response_model=ListResponse[State], tags=["locations"])
def list_states(directory: Directory) -> ListResponse[State]:
    return ListResponse[State](
        items=directory.list_states(), data_source=directory.source, generated_at=_now()
    )


@router.get("/locations/lgas", response_model=ListResponse[Lga], tags=["locations"])
def list_lgas(directory: Directory, state_id: uuid.UUID) -> ListResponse[Lga]:
    return ListResponse[Lga](
        items=directory.list_lgas(state_id), data_source=directory.source, generated_at=_now()
    )


@router.get("/locations/wards", response_model=ListResponse[Ward], tags=["locations"])
def list_wards(directory: Directory, lga_id: uuid.UUID) -> ListResponse[Ward]:
    return ListResponse[Ward](
        items=directory.list_wards(lga_id), data_source=directory.source, generated_at=_now()
    )


@router.get(
    "/polling-units", response_model=PageResponse[PollingUnitSummary], tags=["polling-units"]
)
def search_polling_units(
    directory: Directory,
    state_id: uuid.UUID | None = None,
    lga_id: uuid.UUID | None = None,
    ward_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(min_length=2, max_length=80, pattern=_SEARCH_TEXT)] = None,
    code: Annotated[str | None, Query(pattern=_CODE)] = None,
    status_filter: Annotated[PollingUnitStatus | None, Query(alias="status")] = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> PageResponse[PollingUnitSummary]:
    query = PollingUnitQuery(
        state_id=state_id,
        lga_id=lga_id,
        ward_id=ward_id,
        text=q.strip() if q else None,
        code=code,
        status=status_filter,
    )
    return _page(directory.search_polling_units(query, page, page_size), directory)


@router.get(
    "/polling-units/{polling_unit_id}",
    response_model=ItemResponse[PollingUnitDetail],
    tags=["polling-units"],
)
def get_polling_unit(
    directory: Directory, polling_unit_id: uuid.UUID
) -> ItemResponse[PollingUnitDetail]:
    unit = directory.get_polling_unit(polling_unit_id)
    if unit is None:
        raise _not_found("Polling unit")
    return ItemResponse[PollingUnitDetail](
        item=unit, data_source=directory.source, generated_at=_now()
    )


@router.get("/updates", response_model=PageResponse[ElectionUpdate], tags=["updates"])
def list_updates(
    directory: Directory,
    category: UpdateCategory | None = None,
    verification_status: UpdateVerificationStatus | None = None,
    published_from: datetime | None = None,
    published_to: datetime | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 20,
) -> PageResponse[ElectionUpdate]:
    if published_from and published_to and published_from > published_to:
        raise AppError(
            "validation_error",
            "published_from must be on or before published_to.",
            status_code=422,
        )
    query = UpdateQuery(
        category=category,
        verification_status=verification_status,
        published_from=published_from,
        published_to=published_to,
    )
    return _page(directory.list_updates(query, page, page_size), directory)


@router.get("/updates/{update_id}", response_model=ItemResponse[ElectionUpdate], tags=["updates"])
def get_update(directory: Directory, update_id: uuid.UUID) -> ItemResponse[ElectionUpdate]:
    update = directory.get_update(update_id)
    if update is None:
        raise _not_found("Update")
    return ItemResponse[ElectionUpdate](
        item=update, data_source=directory.source, generated_at=_now()
    )


@admin_router.post(
    "/updates",
    response_model=ItemResponse[ElectionUpdate],
    status_code=status.HTTP_201_CREATED,
)
def publish_update(
    payload: ElectionUpdateCreate,
    directory: Directory,
    principal: Annotated[Principal, Depends(require_roles(Role.ELECTION_ADMIN, Role.SYSTEM_ADMIN))],
) -> ItemResponse[ElectionUpdate]:
    created = directory.create_update(payload, published_by=principal.user_id)
    return ItemResponse[ElectionUpdate](
        item=created, data_source=directory.source, generated_at=_now()
    )
