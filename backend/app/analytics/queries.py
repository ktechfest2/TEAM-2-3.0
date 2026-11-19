"""Read side of the aggregation engine.

Every level is computed from `polling_unit_results` (one row per unit) and
`polling_unit_result_metrics` with indexed GROUP BY queries, so a request touches only
the rows of the requested area. Expected counts always come from the register."""

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.analytics.policy import TOTAL_METRICS
from app.analytics.refresh import submission_state
from app.analytics.registry import Registry, RegistryUnit, registry_for
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.enums import EvidenceStatus, ResultStream
from app.db.enums import PollingUnitResultStatus as R
from app.db.models import EvidenceSubmission, PollingUnitResult, PollingUnitResultMetric
from app.directory.repository import DirectoryRepository
from app.evidence.service import approvals_for, latest_validation
from app.evidence.templates import party_key
from app.schemas.analytics import (
    CIVIC_NOTICE,
    DEMO_LABEL,
    PARTIAL_NOTICE,
    AlertSummary,
    AreaListResponse,
    AreaRef,
    AreaResponse,
    AreaSummary,
    Coverage,
    DataStatus,
    ElectionRef,
    Level,
    PartyBreakdown,
    PartyResultsResponse,
    PartyTotal,
    PollingUnitPage,
    PollingUnitResultResponse,
    PollingUnitRow,
    ProgressPoint,
    ProgressResponse,
    Provenance,
    SourceRecord,
    StreamTotals,
    VerificationReport,
)
from app.schemas.elections import Election

PU = PollingUnitResult
M = PollingUnitResultMetric
REPORTING = (R.REPORTED, R.CONFLICT, R.VERIFIED)
CHILD_LEVEL: dict[Level, Level | None] = {
    "national": "state",
    "state": "lga",
    "lga": "ward",
    "ward": "polling_unit",
    "polling_unit": None,
}
_COLUMN = {"state": PU.state_id, "lga": PU.lga_id, "ward": PU.ward_id}
_METRIC_COLUMN = {"state": M.state_id, "lga": M.lga_id, "ward": M.ward_id}
METHOD = (
    "One result per polling unit. Rejected submissions are ignored; accepted submissions "
    "(validation passed) that agree are counted once; disagreeing submissions are a "
    "conflict and contribute to neither total; verified figures require the configured "
    "number of independent human approvals."
)
STREAM_DESCRIPTION = {
    "reported": (
        "Accepted submissions that passed validation, including those not yet verified. "
        "Polling units with conflicting submissions are excluded."
    ),
    "verified": "Only polling units whose agreed result passed the required human approvals.",
}
SHARE_BASIS = "Share of the party votes counted in this stream for this area."

@dataclass(frozen=True)
class Context:
    db: Session
    directory: DirectoryRepository
    election: Election
    registry: Registry

    @property
    def data_status(self) -> DataStatus:
        demo = self.election.is_demo or self.directory.source.kind == "demo"
        return "demonstration" if demo else "live"

    @property
    def demo_label(self) -> str | None:
        return DEMO_LABEL if self.data_status == "demonstration" else None

    @property
    def election_ref(self) -> ElectionRef:
        e = self.election
        return ElectionRef(id=e.id, name=e.name, election_label=e.election_label, is_demo=e.is_demo)

def context(db: Session, directory: DirectoryRepository, election_id: uuid.UUID) -> Context:
    election = directory.get_election(election_id)
    if election is None:
        raise AppError("not_found", "Election not found.", 404)
    return Context(db, directory, election, registry_for(directory, election))

def _now() -> datetime:
    return datetime.now(UTC)

def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

def _pct(part: int, whole: int) -> float | None:
    return None if whole <= 0 else round(100 * part / whole, 1)

def _coverage_text(value: float | None, suffix: str) -> str:
    if value is None:
        return f", {suffix} not available"
    return f", {value:g}% {suffix}"

def _area_filter(level: Level, area_id: uuid.UUID | None, column_map: dict) -> list:
    if level in column_map and area_id is not None:
        return [column_map[level] == area_id]
    return []

def _counts(
    ctx: Context, where: list, group: Level | None = None
) -> dict[uuid.UUID | None, dict[str, Any]]:
    one = 1
    columns = [
        func.sum(case((PU.submission_count > 0, one), else_=0)).label("with_submissions"),
        func.sum(case((PU.status.in_(REPORTING), one), else_=0)).label("reporting"),
        func.sum(case((PU.status == R.VERIFIED, one), else_=0)).label("verified"),
        func.sum(case((PU.status == R.CONFLICT, one), else_=0)).label("conflicts"),
        func.sum(case((or_(PU.has_flagged, PU.status == R.CONFLICT), one), else_=0)).label(
            "flagged"
        ),
        func.sum(
            case((and_(PU.submission_count > 0, PU.status != R.VERIFIED), one), else_=0)
        ).label("pending"),
        func.sum(case((PU.has_anomaly, one), else_=0)).label("anomalies"),
        func.sum(PU.submission_count).label("submissions"),
        func.sum(PU.independent_count).label("independent"),
        func.sum(PU.rejected_count).label("rejected"),
        func.max(PU.updated_at).label("last_updated"),
    ]
    key_column = _COLUMN[group] if group in _COLUMN else None
    query = select(*([key_column] if key_column is not None else []), *columns).where(
        PU.election_id == ctx.election.id, *where
    )
    if key_column is not None:
        query = query.group_by(key_column)
    result: dict[uuid.UUID | None, dict[str, Any]] = {}
    for row in ctx.db.execute(query).mappings():
        data = dict(row)
        key = data.pop(key_column.key) if key_column is not None else None
        result[key] = data
    return result

def _coverage(expected: int, counts: dict[str, Any] | None, incomplete: int) -> Coverage:
    c = counts or {}

    def n(name: str) -> int:
        return int(c.get(name) or 0)

    reporting, verified = n("reporting"), n("verified")
    reporting_pct, verified_pct = _pct(reporting, expected), _pct(verified, expected)
    return Coverage(
        expected_polling_units=expected,
        polling_units_with_submissions=n("with_submissions"),
        reporting_polling_units=reporting,
        verified_polling_units=verified,
        pending_polling_units=n("pending"),
        flagged_polling_units=n("flagged"),
        conflict_polling_units=n("conflicts"),
        anomaly_polling_units=n("anomalies"),
        submission_count=n("submissions"),
        independent_submission_count=n("independent"),
        rejected_submission_count=n("rejected"),
        incomplete_registry_entries=incomplete,
        reporting_coverage_pct=reporting_pct,
        verification_coverage_pct=verified_pct,
        reporting_label=(
            f"{reporting:,} / {expected:,} polling units reporting"
            + _coverage_text(reporting_pct, "coverage")
        ),
        verification_label=(
            f"{verified:,} / {expected:,} polling units verified"
            + _coverage_text(verified_pct, "verification coverage")
        ),
    )

def _area_ref(ctx: Context, level: Level, area_id: uuid.UUID | None) -> AreaRef:
    reg = ctx.registry
    if level == "national":
        return AreaRef(level="national", id=None, name="Nigeria (all states and the FCT)")
    source: Any
    if level == "state":
        source = reg.states.get(area_id)  # type: ignore[arg-type]
    elif level == "lga":
        source = reg.lgas.get(area_id)  # type: ignore[arg-type]
    elif level == "ward":
        source = reg.wards.get(area_id)  # type: ignore[arg-type]
    else:
        source = reg.units.get(area_id)  # type: ignore[arg-type]
    if source is None:
        raise AppError("not_found", "Area not found in the polling-unit register.", 404)
    return AreaRef(level=level, id=source.id, name=source.name, code=source.code)

def _breadcrumbs(ctx: Context, level: Level, area_id: uuid.UUID | None) -> list[AreaRef]:
    reg = ctx.registry
    crumbs = [_area_ref(ctx, "national", None)]
    if level == "national" or area_id is None:
        return crumbs
    state_id = lga_id = ward_id = None
    if level == "state":
        state_id = area_id
    elif level == "lga":
        lga_id = area_id
        state_id = reg.lgas[area_id].state_id
    elif level == "ward":
        ward_id = area_id
        lga_id = reg.wards[area_id].lga_id
        state_id = reg.lgas[lga_id].state_id
    else:
        unit = reg.units[area_id]
        ward_id, lga_id, state_id = unit.ward_id, unit.lga_id, unit.state_id
    crumbs.append(_area_ref(ctx, "state", state_id))
    if lga_id:
        crumbs.append(_area_ref(ctx, "lga", lga_id))
    if ward_id:
        crumbs.append(_area_ref(ctx, "ward", ward_id))
    if level == "polling_unit":
        crumbs.append(_area_ref(ctx, "polling_unit", area_id))
    return crumbs

def _expected(ctx: Context, level: Level, area_id: uuid.UUID | None) -> tuple[int, int]:
    reg = ctx.registry
    if level == "national":
        return reg.expected_total, sum(1 for u in reg.units.values() if u.is_incomplete)
    if level == "state":
        return reg.expected_by_state[area_id], reg.incomplete_by_state[area_id]  # type: ignore[index]
    if level == "lga":
        return reg.expected_by_lga[area_id], reg.incomplete_by_lga[area_id]  # type: ignore[index]
    if level == "ward":
        return reg.expected_by_ward[area_id], reg.incomplete_by_ward[area_id]  # type: ignore[index]
    unit = reg.units[area_id]  # type: ignore[index]
    return 1, int(unit.is_incomplete)

def _child_ids(ctx: Context, level: Level, area_id: uuid.UUID | None) -> list[uuid.UUID]:
    reg = ctx.registry
    if level == "national":
        return sorted(reg.states, key=lambda i: reg.states[i].name)
    if level == "state":
        return sorted(reg.lgas_by_state.get(area_id, []), key=lambda i: reg.lgas[i].name)  # type: ignore[arg-type]
    if level == "lga":
        return sorted(reg.wards_by_lga.get(area_id, []), key=lambda i: reg.wards[i].name)  # type: ignore[arg-type]
    if level == "ward":
        return sorted(reg.units_by_ward.get(area_id, []), key=lambda i: reg.units[i].code)  # type: ignore[arg-type]
    return []

def _summary(
    ctx: Context, level: Level, area_id: uuid.UUID | None, counts: dict[str, Any] | None
) -> AreaSummary:
    expected, incomplete = _expected(ctx, level, area_id)
    iso = ctx.registry.states[area_id].iso_code if level == "state" and area_id else None
    return AreaSummary(
        area=_area_ref(ctx, level, area_id),
        iso_code=iso,
        coverage=_coverage(expected, counts, incomplete),
        last_updated_at=_utc((counts or {}).get("last_updated")),
    )

def _children(ctx: Context, level: Level, area_id: uuid.UUID | None) -> list[AreaSummary]:
    child = CHILD_LEVEL[level]
    if child is None:
        return []
    ids = _child_ids(ctx, level, area_id)
    if child == "polling_unit":
        rows = _rows_by_unit(ctx, ids)
        return [_summary(ctx, child, i, _row_counts(rows.get(i))) for i in ids]
    grouped = _counts(ctx, _area_filter(level, area_id, _COLUMN), group=child)
    return [_summary(ctx, child, i, grouped.get(i)) for i in ids]

def _rows_by_unit(ctx: Context, ids: list[uuid.UUID]) -> dict[uuid.UUID, PollingUnitResult]:
    if not ids:
        return {}
    rows = ctx.db.scalars(
        select(PU).where(PU.election_id == ctx.election.id, PU.polling_unit_id.in_(ids))
    )
    return {row.polling_unit_id: row for row in rows}

def _row_counts(row: PollingUnitResult | None) -> dict[str, Any] | None:
    if row is None:
        return None
    status = R(row.status)
    return {
        "with_submissions": int(row.submission_count > 0),
        "reporting": int(status in REPORTING),
        "verified": int(status == R.VERIFIED),
        "conflicts": int(status == R.CONFLICT),
        "flagged": int(row.has_flagged or status == R.CONFLICT),
        "pending": int(row.submission_count > 0 and status != R.VERIFIED),
        "anomalies": int(row.has_anomaly),
        "submissions": row.submission_count,
        "independent": row.independent_count,
        "rejected": row.rejected_count,
        "last_updated": row.updated_at,
    }

def _metric_sums(
    ctx: Context, where: list, group: Level | None = None
) -> dict[uuid.UUID | None, dict[str, dict[str, int]]]:
    key_column = _METRIC_COLUMN[group] if group in _METRIC_COLUMN else None
    query = select(
        *([key_column] if key_column is not None else []),
        M.stream,
        M.metric,
        func.sum(M.value).label("total"),
    ).where(M.election_id == ctx.election.id, *where)
    query = query.group_by(*([key_column] if key_column is not None else []), M.stream, M.metric)
    sums: dict[uuid.UUID | None, dict[str, dict[str, int]]] = defaultdict(
        lambda: {"reported": {}, "verified": {}}
    )
    for row in ctx.db.execute(query):
        key = row[0] if key_column is not None else None
        stream, metric, total = row[-3], row[-2], row[-1]
        sums[key][ResultStream(stream).value][metric] = int(total or 0)
    return sums

def _stream(
    ctx: Context, stream: str, metrics: dict[str, int], included: int, expected: int
) -> StreamTotals:
    parties = [(p.code, p.name, metrics.get(party_key(p.code), 0)) for p in ctx.election.parties]
    party_sum = sum(votes for _, _, votes in parties)
    return StreamTotals(
        stream=stream,  # type: ignore[arg-type]
        description=STREAM_DESCRIPTION[stream],
        polling_units_included=included,
        expected_polling_units=expected,
        **{name: metrics.get(name, 0) for name in TOTAL_METRICS},
        parties=[
            PartyTotal(code=code, name=name, votes=votes, share_pct=_pct(votes, party_sum))
            for code, name, votes in parties
        ],
        share_basis=SHARE_BASIS,
    )

def _streams(
    ctx: Context, metrics: dict[str, dict[str, int]], coverage: Coverage
) -> tuple[StreamTotals, StreamTotals]:
    reported_units = coverage.reporting_polling_units - coverage.conflict_polling_units
    return (
        _stream(
            ctx, "reported", metrics["reported"], reported_units, coverage.expected_polling_units
        ),
        _stream(
            ctx,
            "verified",
            metrics["verified"],
            coverage.verified_polling_units,
            coverage.expected_polling_units,
        ),
    )

def _alerts(coverage: Coverage, query: str) -> list[AlertSummary]:
    base = f"/api/v1/analytics/discrepancies?{query}"
    return [
        AlertSummary(
            kind="unresolved_discrepancies",
            count=coverage.conflict_polling_units,
            title="Unresolved discrepancies",
            description=(
                "Polling units where accepted submissions disagree. Their figures are left "
                "out of both totals until reviewers resolve the disagreement."
            ),
            href=f"{base}&kind=conflict",
        ),
        AlertSummary(
            kind="records_requiring_review",
            count=coverage.flagged_polling_units,
            title="Records requiring review",
            description="Polling units with evidence flagged for human review.",
            href=f"{base}&kind=flagged",
        ),
        AlertSummary(
            kind="unusual_patterns",
            count=coverage.anomaly_polling_units,
            title="Unusual reporting patterns",
            description=(
                "VoteTrace AI flagged unusual figures. Human review is required. An alert is not "
                "a finding of wrongdoing."
            ),
            href=f"{base}&kind=anomaly",
        ),
        AlertSummary(
            kind="incomplete",
            count=coverage.incomplete_registry_entries,
            title="Incomplete location records",
            description=(
                "Register entries without coordinates or an address description, or whose "
                "status is still unconfirmed."
            ),
            href=f"{base}&kind=incomplete",
        ),
    ]

def area(ctx: Context, level: Level, area_id: uuid.UUID | None) -> AreaResponse:
    _area_ref(ctx, level, area_id)
    where = _area_filter(level, area_id, _COLUMN)
    summary = _summary(ctx, level, area_id, _counts(ctx, where).get(None))
    metrics = _metric_sums(ctx, _area_filter(level, area_id, _METRIC_COLUMN)).get(None) or {
        "reported": {},
        "verified": {},
    }
    reported, verified = _streams(ctx, metrics, summary.coverage)
    children = _children(ctx, level, area_id)
    query = f"election_id={ctx.election.id}"
    if level in _COLUMN and area_id:
        query += f"&{level}_id={area_id}"
    return AreaResponse(
        election=ctx.election_ref,
        level=level,
        summary=summary,
        breadcrumbs=_breadcrumbs(ctx, level, area_id),
        reported=reported,
        verified=verified,
        child_level=CHILD_LEVEL[level],
        children=children,
        child_areas_reporting=sum(1 for c in children if c.coverage.reporting_polling_units > 0),
        child_areas_outstanding=sum(
            1
            for c in children
            if c.coverage.reporting_polling_units < c.coverage.expected_polling_units
            or c.coverage.pending_polling_units > 0
        ),
        alerts=_alerts(summary.coverage, query),
        data_status=ctx.data_status,
        demo_label=ctx.demo_label,
        notice=CIVIC_NOTICE,
        partial_notice=PARTIAL_NOTICE,
        provenance=Provenance(
            aggregation_level=level,
            registry_source=ctx.directory.source,
            method=METHOD,
            source_records_path=f"/api/v1/analytics/polling-units?{query}",
        ),
        generated_at=_now(),
    )

def area_list(
    ctx: Context,
    level: Level,
    parent_level: Level,
    parent_id: uuid.UUID | None,
    page: int,
    page_size: int,
    sort: str,
) -> AreaListResponse:
    items = _children(ctx, parent_level, parent_id)
    if sort == "reporting":
        items.sort(key=lambda s: (s.coverage.reporting_coverage_pct or 0, s.area.name))
    elif sort == "verification":
        items.sort(key=lambda s: (s.coverage.verification_coverage_pct or 0, s.area.name))
    total = len(items)
    start = (page - 1) * page_size
    return AreaListResponse(
        election=ctx.election_ref,
        level=level,
        items=items[start : start + page_size],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=max(1, math.ceil(total / page_size)),
        data_status=ctx.data_status,
        demo_label=ctx.demo_label,
        notice=CIVIC_NOTICE,
        generated_at=_now(),
    )

def party_results(ctx: Context, level: Level, area_id: uuid.UUID | None) -> PartyResultsResponse:
    _area_ref(ctx, level, area_id)
    where = _area_filter(level, area_id, _COLUMN)
    coverage = _summary(ctx, level, area_id, _counts(ctx, where).get(None)).coverage
    metric_where = _area_filter(level, area_id, _METRIC_COLUMN)
    metrics = _metric_sums(ctx, metric_where).get(None) or {"reported": {}, "verified": {}}
    reported, verified = _streams(ctx, metrics, coverage)
    child = CHILD_LEVEL[level]
    breakdown: list[PartyBreakdown] = []
    if child in _COLUMN:
        grouped_metrics = _metric_sums(ctx, metric_where, group=child)
        grouped_counts = _counts(ctx, where, group=child)
        for child_id in _child_ids(ctx, level, area_id):
            child_cov = _summary(ctx, child, child_id, grouped_counts.get(child_id)).coverage
            child_metrics = grouped_metrics.get(child_id) or {"reported": {}, "verified": {}}
            r, v = _streams(ctx, child_metrics, child_cov)
            breakdown.append(
                PartyBreakdown(area=_area_ref(ctx, child, child_id), reported=r, verified=v)
            )
    return PartyResultsResponse(
        election=ctx.election_ref,
        area=_area_ref(ctx, level, area_id),
        reported=reported,
        verified=verified,
        breakdown_level=child if child in _COLUMN else None,
        breakdown=breakdown,
        data_status=ctx.data_status,
        demo_label=ctx.demo_label,
        notice=CIVIC_NOTICE,
        partial_notice=PARTIAL_NOTICE,
        generated_at=_now(),
    )

def _unit_row(ctx: Context, unit: RegistryUnit, row: PollingUnitResult | None) -> PollingUnitRow:
    reg = ctx.registry
    state, lga, ward = reg.states[unit.state_id], reg.lgas[unit.lga_id], reg.wards[unit.ward_id]
    return PollingUnitRow(
        id=unit.id,
        code=unit.code,
        name=unit.name,
        ward=AreaRef(level="ward", id=ward.id, name=ward.name, code=ward.code),
        lga=AreaRef(level="lga", id=lga.id, name=lga.name, code=lga.code),
        state=AreaRef(level="state", id=state.id, name=state.name, code=state.code),
        status=R(row.status) if row else R.NOT_REPORTING,
        submission_count=row.submission_count if row else 0,
        accepted_count=row.accepted_count if row else 0,
        independent_count=row.independent_count if row else 0,
        distinct_results=row.distinct_results if row else 0,
        has_flagged=row.has_flagged if row else False,
        has_anomaly=row.has_anomaly if row else False,
        reported_result_hash=row.reported_result_hash if row else None,
        verified_result_hash=row.verified_result_hash if row else None,
        registry_incomplete=unit.is_incomplete,
        revision=row.revision if row else None,
        updated_at=_utc(row.updated_at) if row else None,
    )

def _units_in(ctx: Context, level: Level, area_id: uuid.UUID | None) -> list[RegistryUnit]:
    units = ctx.registry.units.values()
    if level == "state":
        units = [u for u in units if u.state_id == area_id]  # type: ignore[assignment]
    elif level == "lga":
        units = [u for u in units if u.lga_id == area_id]  # type: ignore[assignment]
    elif level == "ward":
        units = [u for u in units if u.ward_id == area_id]  # type: ignore[assignment]
    return sorted(units, key=lambda u: u.code)

KINDS = ("conflict", "flagged", "anomaly", "pending", "incomplete")

def polling_units(
    ctx: Context,
    level: Level,
    area_id: uuid.UUID | None,
    *,
    status: R | None,
    kind: str | None,
    page: int,
    page_size: int,
) -> PollingUnitPage:
    if area_id is not None:
        _area_ref(ctx, level, area_id)
    units = _units_in(ctx, level, area_id)
    if kind == "incomplete":
        units = [u for u in units if u.is_incomplete]
    rows = _rows_by_unit(ctx, [u.id for u in units]) if units else {}

    def keep(unit: RegistryUnit) -> bool:
        row = rows.get(unit.id)
        current = R(row.status) if row else R.NOT_REPORTING
        if status is not None and current != status:
            return False
        if kind == "conflict":
            return current == R.CONFLICT
        if kind == "flagged":
            return bool(row) and (row.has_flagged or current == R.CONFLICT)  # type: ignore[union-attr]
        if kind == "anomaly":
            return bool(row) and row.has_anomaly  # type: ignore[union-attr]
        if kind == "pending":
            return bool(row) and row.submission_count > 0 and current != R.VERIFIED  # type: ignore[union-attr]
        return True

    selected = [u for u in units if keep(u)]
    start = (page - 1) * page_size
    return PollingUnitPage(
        election=ctx.election_ref,
        items=[_unit_row(ctx, u, rows.get(u.id)) for u in selected[start : start + page_size]],
        page=page,
        page_size=page_size,
        total=len(selected),
        total_pages=max(1, math.ceil(len(selected) / page_size)),
        data_status=ctx.data_status,
        demo_label=ctx.demo_label,
        notice=CIVIC_NOTICE,
        generated_at=_now(),
    )

def check_counts(report: dict[str, Any]) -> tuple[int, int, int]:
    """(passed, failed, warnings) from a stored validation report.

    Each stored check carries an `outcome` (passed, failed or not_evaluated) and a
    `severity`. Only error-severity failures count as failed. Warning-severity failures
    and checks that could not be evaluated are counted once, as warnings, using the
    same list the validator publishes."""
    checks = report.get("checks", [])
    passed = sum(1 for c in checks if c.get("outcome") == "passed")
    failed = sum(
        1 for c in checks if c.get("outcome") == "failed" and c.get("severity", "error") == "error"
    )
    return passed, failed, len(report.get("warnings", []))


def polling_unit_result(ctx: Context, polling_unit_id: uuid.UUID) -> PollingUnitResultResponse:
    unit = ctx.registry.units.get(polling_unit_id)
    if unit is None:
        raise AppError("not_found", "Polling unit not found in the register.", 404)
    row = _rows_by_unit(ctx, [unit.id]).get(unit.id)
    metrics: dict[str, dict[str, int]] = {"reported": {}, "verified": {}}
    if row is not None:
        for metric in ctx.db.scalars(select(M).where(M.result_id == row.id)):
            metrics[ResultStream(metric.stream).value][metric.metric] = metric.value
    unit_row = _unit_row(ctx, unit, row)
    coverage = _coverage(1, _row_counts(row), int(unit.is_incomplete))
    reported, verified = _streams(ctx, metrics, coverage)

    submissions = ctx.db.scalars(
        select(EvidenceSubmission)
        .where(
            EvidenceSubmission.election_id == ctx.election.id,
            EvidenceSubmission.polling_unit_id == unit.id,
        )
        .order_by(EvidenceSubmission.received_at)
    ).all()
    contributing = set(row.contributing_submission_ids) if row else set()
    records: list[SourceRecord] = []
    representative = None
    for submission in submissions:
        state = submission_state(ctx.db, submission)
        records.append(
            SourceRecord(
                submission_id=submission.id,
                workflow_status=state.status,
                received_at=state.received_at,
                result_fingerprint=state.result_hash,
                validation_passed=state.validation_passed,
                agrees_with_reported=(
                    None
                    if not row or not row.reported_result_hash or state.result_hash is None
                    else state.result_hash == row.reported_result_hash
                ),
                contributes=str(submission.id) in contributing,
            )
        )
        if str(submission.id) in contributing and (
            representative is None or state.status == EvidenceStatus.VERIFIED
        ):
            representative = submission

    approvals = 0
    checks_passed = checks_failed = warnings = 0
    if representative is not None:
        validation = latest_validation(ctx.db, representative.id)
        if validation is not None:
            checks_passed, checks_failed, warnings = check_counts(validation.report)
            if row and row.verified_result_hash:
                approvals = len(approvals_for(ctx.db, representative, validation.result_hash))

    return PollingUnitResultResponse(
        election=ctx.election_ref,
        unit=unit_row,
        breadcrumbs=_breadcrumbs(ctx, "polling_unit", unit.id),
        reported=reported,
        verified=verified,
        verification=VerificationReport(
            status=unit_row.status,
            required_approvals=get_settings().verification_required_approvals,
            approvals_on_verified_result=approvals,
            verified_at=_utc(row.verified_at) if row else None,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            warnings=warnings,
            disclaimer=(
                "Arithmetic consistency is not proof of authenticity. Verification means "
                "VoteTrace reviewers approved this transcription against the submitted "
                "evidence; it is not an INEC declaration."
            ),
        ),
        source_records=records,
        data_status=ctx.data_status,
        demo_label=ctx.demo_label,
        notice=CIVIC_NOTICE,
        generated_at=_now(),
    )

def progress(ctx: Context, level: Level, area_id: uuid.UUID | None) -> ProgressResponse:
    _area_ref(ctx, level, area_id)
    where = _area_filter(level, area_id, _COLUMN)
    rows = ctx.db.execute(
        select(PU.first_reported_at, PU.verified_at, PU.status).where(
            PU.election_id == ctx.election.id, *where
        )
    ).all()
    reported_times = sorted(
        t for t, _, s in ((_utc(a), b, c) for a, b, c in rows) if t and R(s) in REPORTING
    )
    verified_times = sorted(
        t for _, t, s in ((a, _utc(b), c) for a, b, c in rows) if t and R(s) == R.VERIFIED
    )

    def hour(value: datetime) -> datetime:
        return value.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    buckets = sorted({hour(t) for t in reported_times + verified_times})
    points = [
        ProgressPoint(
            at=bucket,
            reporting_polling_units=sum(1 for t in reported_times if t < bucket),
            verified_polling_units=sum(1 for t in verified_times if t < bucket),
        )
        for bucket in buckets
    ]
    expected, _ = _expected(ctx, level, area_id)
    return ProgressResponse(
        election=ctx.election_ref,
        area=_area_ref(ctx, level, area_id),
        expected_polling_units=expected,
        bucket="hour",
        points=points,
        description=(
            "Cumulative polling units currently reporting and currently verified, by the hour "
            "their first accepted submission was validated and their verification completed."
        ),
        data_status=ctx.data_status,
        demo_label=ctx.demo_label,
        generated_at=_now(),
    )
