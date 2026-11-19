"""Public, read-only aggregation API, plus one administrative rebuild route.

No route accepts figures, totals or statuses from a client: everything is derived on the
server from evidence records that went through the verification workflow. Responses
never include submitter identities, images or storage locations."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.analytics import queries
from app.analytics.events import TooManySubscribersError, broker, stream_events
from app.analytics.refresh import rebuild_election
from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.db.enums import PollingUnitResultStatus, Role
from app.directory.repository import DirectoryRepository, get_directory
from app.evidence.db import get_evidence_db
from app.schemas.analytics import (
    AreaListResponse,
    AreaResponse,
    Level,
    PartyResultsResponse,
    PollingUnitPage,
    PollingUnitResultResponse,
    ProgressResponse,
    RebuildResult,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])
admin_router = APIRouter(prefix="/admin/analytics", tags=["admin"])

Db = Annotated[Session, Depends(get_evidence_db)]
Directory = Annotated[DirectoryRepository, Depends(get_directory)]
ElectionId = Annotated[uuid.UUID, Query(description="Election to aggregate.")]
PageNumber = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]
OptionalId = Annotated[uuid.UUID | None, Query()]
AreaLevel = Literal["national", "state", "lga", "ward"]


def _ctx(db: Session, directory: DirectoryRepository, election_id: uuid.UUID) -> queries.Context:
    return queries.context(db, directory, election_id)


def _scope(
    state_id: uuid.UUID | None, lga_id: uuid.UUID | None, ward_id: uuid.UUID | None
) -> tuple[Level, uuid.UUID | None]:
    """The most specific area given. Only one may be supplied."""
    given = [(lvl, i) for lvl, i in (("ward", ward_id), ("lga", lga_id), ("state", state_id)) if i]
    if len(given) > 1:
        raise AppError("invalid_scope", "Give at most one of state_id, lga_id or ward_id.", 422)
    return given[0] if given else ("national", None)  # type: ignore[return-value]


@router.get("/national", response_model=AreaResponse)
def national(db: Db, directory: Directory, election_id: ElectionId) -> AreaResponse:
    return queries.area(_ctx(db, directory, election_id), "national", None)


@router.get("/states", response_model=AreaListResponse)
def states(
    db: Db,
    directory: Directory,
    election_id: ElectionId,
    page: PageNumber = 1,
    page_size: PageSize = 50,
) -> AreaListResponse:
    ctx = _ctx(db, directory, election_id)
    return queries.area_list(ctx, "state", "national", None, page, page_size, sort="name")


@router.get("/states/{state_id}", response_model=AreaResponse)
def state(db: Db, directory: Directory, state_id: uuid.UUID, election_id: ElectionId):
    return queries.area(_ctx(db, directory, election_id), "state", state_id)


@router.get("/lgas/{lga_id}", response_model=AreaResponse)
def lga(db: Db, directory: Directory, lga_id: uuid.UUID, election_id: ElectionId):
    return queries.area(_ctx(db, directory, election_id), "lga", lga_id)


@router.get("/wards/{ward_id}", response_model=AreaResponse)
def ward(db: Db, directory: Directory, ward_id: uuid.UUID, election_id: ElectionId):
    return queries.area(_ctx(db, directory, election_id), "ward", ward_id)


@router.get("/polling-units", response_model=PollingUnitPage)
def polling_units(
    db: Db,
    directory: Directory,
    election_id: ElectionId,
    state_id: OptionalId = None,
    lga_id: OptionalId = None,
    ward_id: OptionalId = None,
    status: PollingUnitResultStatus | None = None,
    page: PageNumber = 1,
    page_size: PageSize = 50,
) -> PollingUnitPage:
    level, area_id = _scope(state_id, lga_id, ward_id)
    return queries.polling_units(
        _ctx(db, directory, election_id),
        level,
        area_id,
        status=status,
        kind=None,
        page=page,
        page_size=page_size,
    )


@router.get("/polling-units/{polling_unit_id}", response_model=PollingUnitResultResponse)
def polling_unit(
    db: Db, directory: Directory, polling_unit_id: uuid.UUID, election_id: ElectionId
) -> PollingUnitResultResponse:
    return queries.polling_unit_result(_ctx(db, directory, election_id), polling_unit_id)


def _coverage_list(
    db: Session,
    directory: DirectoryRepository,
    election_id: uuid.UUID,
    level: Literal["state", "lga", "ward"],
    parent_id: uuid.UUID | None,
    page: int,
    page_size: int,
    sort: str,
) -> AreaListResponse:
    parent: Level = {"state": "national", "lga": "state", "ward": "lga"}[level]  # type: ignore[assignment]
    if parent != "national" and parent_id is None:
        raise AppError("parent_required", f"parent_id is required for level {level}.", 422)
    ctx = _ctx(db, directory, election_id)
    if parent_id is not None:
        queries._area_ref(ctx, parent, parent_id)
    return queries.area_list(ctx, level, parent, parent_id, page, page_size, sort)


@router.get("/reporting-coverage", response_model=AreaListResponse)
def reporting_coverage(
    db: Db,
    directory: Directory,
    election_id: ElectionId,
    level: Literal["state", "lga", "ward"] = "state",
    parent_id: OptionalId = None,
    page: PageNumber = 1,
    page_size: PageSize = 50,
) -> AreaListResponse:
    """Areas ordered from lowest to highest reporting coverage."""
    return _coverage_list(
        db, directory, election_id, level, parent_id, page, page_size, "reporting"
    )


@router.get("/verification-coverage", response_model=AreaListResponse)
def verification_coverage(
    db: Db,
    directory: Directory,
    election_id: ElectionId,
    level: Literal["state", "lga", "ward"] = "state",
    parent_id: OptionalId = None,
    page: PageNumber = 1,
    page_size: PageSize = 50,
) -> AreaListResponse:
    """Areas ordered from lowest to highest verification coverage."""
    return _coverage_list(
        db, directory, election_id, level, parent_id, page, page_size, "verification"
    )


@router.get("/party-results", response_model=PartyResultsResponse)
def party_results(
    db: Db,
    directory: Directory,
    election_id: ElectionId,
    state_id: OptionalId = None,
    lga_id: OptionalId = None,
    ward_id: OptionalId = None,
) -> PartyResultsResponse:
    level, area_id = _scope(state_id, lga_id, ward_id)
    return queries.party_results(_ctx(db, directory, election_id), level, area_id)


@router.get("/discrepancies", response_model=PollingUnitPage)
def discrepancies(
    db: Db,
    directory: Directory,
    election_id: ElectionId,
    kind: Literal["conflict", "flagged", "anomaly", "pending", "incomplete"] = "conflict",
    state_id: OptionalId = None,
    lga_id: OptionalId = None,
    ward_id: OptionalId = None,
    page: PageNumber = 1,
    page_size: PageSize = 50,
) -> PollingUnitPage:
    level, area_id = _scope(state_id, lga_id, ward_id)
    return queries.polling_units(
        _ctx(db, directory, election_id),
        level,
        area_id,
        status=None,
        kind=kind,
        page=page,
        page_size=page_size,
    )


@router.get("/progress", response_model=ProgressResponse)
def progress(
    db: Db,
    directory: Directory,
    election_id: ElectionId,
    state_id: OptionalId = None,
    lga_id: OptionalId = None,
    ward_id: OptionalId = None,
) -> ProgressResponse:
    level, area_id = _scope(state_id, lga_id, ward_id)
    return queries.progress(_ctx(db, directory, election_id), level, area_id)


@router.get(
    "/updates",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def updates(
    request: Request,
    directory: Directory,
    election_id: ElectionId,
    last_event_id: Annotated[int | None, Header(alias="Last-Event-ID", ge=0)] = None,
) -> StreamingResponse:
    """Server-Sent Events: one `aggregation` event per polling unit whose aggregation
    changed, with identifiers only. Clients refetch the affected summaries."""
    if directory.get_election(election_id) is None:
        raise AppError("not_found", "Election not found.", 404)
    try:
        subscription = broker.subscribe()
    except TooManySubscribersError as exc:
        raise AppError(
            "too_many_listeners", "Live updates are at capacity. The page will refresh.", 503
        ) from exc
    return StreamingResponse(
        stream_events(
            broker,
            subscription,
            request.is_disconnected,
            election_id=str(election_id),
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@admin_router.post("/rebuild", response_model=RebuildResult)
def rebuild(
    db: Db,
    directory: Directory,
    election_id: ElectionId,
    _principal: Annotated[
        Principal, Depends(require_roles(Role.SYSTEM_ADMIN, Role.ELECTION_ADMIN))
    ],
) -> RebuildResult:
    """Recompute every polling-unit aggregation for an election from source records.
    Used after a deployment or restore. Takes no figures from the request."""
    if directory.get_election(election_id) is None:
        raise AppError("not_found", "Election not found.", 404)
    changes = rebuild_election(db, election_id, directory)
    db.commit()
    for change in changes:
        broker.publish(change)
    return RebuildResult(
        election_id=election_id,
        polling_units_changed=len(changes),
        generated_at=datetime.now(UTC),
    )
