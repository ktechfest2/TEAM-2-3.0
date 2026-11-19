"""Shared, read-only information service for USSD and SMS.

Every figure comes from the aggregation engine (app/analytics/queries.py), every place
from the polling-unit register, and every update from the announcements service. This
module only formats; it never computes totals or coverage itself and never writes."""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.analytics import queries
from app.core.config import Settings
from app.core.errors import AppError
from app.db.enums import PollingUnitResultStatus as R
from app.db.enums import PollingUnitStatus, UpdateVerificationStatus
from app.directory.repository import DirectoryRepository, UpdateQuery
from app.schemas.analytics import StreamTotals
from app.schemas.elections import Election
from app.schemas.updates import ElectionUpdate

Level = Literal["polling_unit", "ward", "lga", "state", "national"]
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,31}$")
LEVEL_NAME: dict[Level, str] = {
    "polling_unit": "polling unit",
    "ward": "ward",
    "lga": "LGA",
    "state": "state",
    "national": "national",
}
RESULT_STATUS_TEXT = {
    R.NOT_REPORTING: "No accepted result yet",
    R.PENDING: "Submitted, awaiting checks",
    R.REPORTED: "Reported, not yet verified",
    R.CONFLICT: "Conflicting submissions, under review",
    R.VERIFIED: "Verified by VoteTrace reviewers",
}
UNIT_STATUS_TEXT = {
    PollingUnitStatus.ACTIVE: "Active",
    PollingUnitStatus.RELOCATION_REPORTED: "Relocation reported by the public, not confirmed",
    PollingUnitStatus.OFFICIALLY_RELOCATED: "Officially relocated",
    PollingUnitStatus.TEMPORARILY_UNAVAILABLE: "Temporarily unavailable",
    PollingUnitStatus.PENDING_VERIFICATION: "Location details not yet confirmed",
}
UPDATE_STATUS_TEXT = {
    UpdateVerificationStatus.OFFICIALLY_CONFIRMED: "Official",
    UpdateVerificationStatus.INDEPENDENTLY_VERIFIED: "Verified",
    UpdateVerificationStatus.REPORTED_UNVERIFIED: "Unverified report",
}
DISCLAIMER = "Not INEC results."
DEMO_TAG = "Sample data, not official."


class UnknownLocationError(AppError):
    def __init__(self, level: Level, code: str) -> None:
        super().__init__(
            "unknown_location", f"No {LEVEL_NAME[level]} has the code {code}.", status_code=404
        )
        self.level = level
        self.code = code


def normalise_code(value: str) -> str | None:
    code = value.strip().upper()
    return code if CODE_PATTERN.fullmatch(code) else None


def channel_election(directory: DirectoryRepository, settings: Settings) -> Election:
    if settings.channel_election_id:
        try:
            election = directory.get_election(uuid.UUID(settings.channel_election_id))
        except ValueError:
            election = None
        if election is None:
            raise AppError(
                "channel_election_unavailable", "The configured election was not found.", 503
            )
        return election
    elections = directory.list_elections()
    if not elections:
        raise AppError("channel_election_unavailable", "No election is configured.", 503)
    return elections[-1]


def _fmt_time(value: datetime | None) -> str:
    if value is None:
        return "no data yet"
    stamp = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return stamp.strftime("%d %b %H:%M UTC")


@dataclass
class InfoService:
    db: Session
    directory: DirectoryRepository
    election: Election

    @property
    def ctx(self) -> queries.Context:
        return queries.context(self.db, self.directory, self.election.id)

    def example_code(self, level: Level) -> str | None:
        reg = self.ctx.registry
        source = {"state": reg.states, "lga": reg.lgas, "ward": reg.wards}.get(level)
        items = list(source.values()) if source is not None else list(reg.units.values())
        codes = sorted(item.code for item in items)
        return codes[0] if codes else None

    def find(self, level: Level, raw_code: str) -> uuid.UUID:
        code = normalise_code(raw_code)
        if code is None:
            raise UnknownLocationError(level, raw_code.strip().upper()[:32] or "(blank)")
        reg = self.ctx.registry
        sources = {
            "state": reg.states,
            "lga": reg.lgas,
            "ward": reg.wards,
            "polling_unit": reg.units,
        }
        for item in sources[level].values():
            if item.code.upper() == code:
                return item.id
        raise UnknownLocationError(level, code)

    def _footer(self, ctx: queries.Context) -> list[str]:
        lines = [DISCLAIMER]
        if ctx.data_status == "demonstration":
            lines.insert(0, DEMO_TAG)
        return lines

    @staticmethod
    def _votes(label: str, stream: StreamTotals) -> str:
        counted = [p for p in stream.parties if p.votes > 0]
        if stream.polling_units_included == 0 or not counted:
            return f"{label}: none yet"
        parts = ", ".join(f"{p.code} {p.votes:,}" for p in counted)
        return f"{label} ({stream.polling_units_included:,} PUs): {parts}"

    def area_lines(self, level: Level, area_id: uuid.UUID | None) -> list[str]:
        ctx = self.ctx
        api_level = "national" if level == "national" else level
        response = queries.area(ctx, api_level, area_id)  # type: ignore[arg-type]
        cov = response.summary.coverage
        area = response.summary.area
        expected = cov.expected_polling_units
        title = area.name if not area.code else f"{area.name} ({area.code})"
        lines = [
            ascii_title(title),
            f"Expected PUs: {expected:,}",
            f"Reporting: {cov.reporting_polling_units:,} ({_pct(cov.reporting_coverage_pct)})",
            f"Verified: {cov.verified_polling_units:,} ({_pct(cov.verification_coverage_pct)})",
            f"Pending: {cov.pending_polling_units:,}",
        ]
        if cov.reporting_polling_units < expected:
            lines.append("Incomplete: not all PUs reporting.")
        if cov.conflict_polling_units:
            lines.append(f"Conflicts left out of totals: {cov.conflict_polling_units:,}")
        lines.append(self._votes("Reported", response.reported))
        lines.append(self._votes("Verified", response.verified))
        lines.append(f"Updated: {_fmt_time(response.summary.last_updated_at)}")
        return lines + self._footer(ctx)

    def polling_unit_lines(self, unit_id: uuid.UUID) -> list[str]:
        ctx = self.ctx
        response = queries.polling_unit_result(ctx, unit_id)
        unit = response.unit
        status = R(unit.status)
        lines = [
            ascii_title(f"{unit.name} ({unit.code})"),
            f"{unit.ward.name}, {unit.lga.name}, {unit.state.name}",
            f"Result: {RESULT_STATUS_TEXT[status]}",
        ]
        if status in (R.NOT_REPORTING, R.PENDING):
            lines.append("Incomplete: no accepted result for this PU yet.")
        lines.append(self._votes("Reported", response.reported))
        lines.append(self._votes("Verified", response.verified))
        lines.append(f"Submissions: {unit.submission_count}")
        lines.append(f"Updated: {_fmt_time(unit.updated_at)}")
        return lines + self._footer(ctx)

    def status_lines(self, unit_id: uuid.UUID) -> list[str]:
        ctx = self.ctx
        detail = self.directory.get_polling_unit(unit_id)
        result = queries.polling_unit_result(ctx, unit_id)
        if detail is None:
            raise UnknownLocationError("polling_unit", "?")
        lines = [
            ascii_title(f"{detail.name} ({detail.code})"),
            f"Location: {UNIT_STATUS_TEXT[PollingUnitStatus(detail.status)]}",
        ]
        confirmed = [n for n in detail.official_notices if n.new_location_description]
        if detail.status == PollingUnitStatus.OFFICIALLY_RELOCATED and confirmed:
            lines.append(f"New location: {confirmed[0].new_location_description}")
        lines.append(f"Result: {RESULT_STATUS_TEXT[R(result.unit.status)]}")
        lines.append(
            f"Verification: {result.verification.approvals_on_verified_result}"
            f"/{result.verification.required_approvals} approvals"
        )
        return lines + self._footer(ctx)

    def updates(self, page: int, page_size: int) -> tuple[list[ElectionUpdate], int]:
        result = self.directory.list_updates(UpdateQuery(), page, page_size)
        return result.items, result.total_pages

    def update_lines(self, update: ElectionUpdate) -> list[str]:
        lines = [
            update.title,
            f"{UPDATE_STATUS_TEXT[UpdateVerificationStatus(update.verification_status)]}, "
            f"{_fmt_time(update.published_at)}",
            update.description,
            f"Source: {update.source_name}",
        ]
        if update.is_demo:
            lines.append(DEMO_TAG)
        return lines

    def update_headline(self, update: ElectionUpdate) -> str:
        tag = UPDATE_STATUS_TEXT[UpdateVerificationStatus(update.verification_status)]
        return f"{update.title} [{tag}]"


def ascii_title(value: str) -> str:
    return " ".join(value.split())


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:g}%"
