import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from app.db.enums import NoticeVerificationStatus, PollingUnitStatus
from app.schemas.common import ApiModel
from app.schemas.locations import LocationRef


class Coordinates(ApiModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    precision: Literal["surveyed", "source_reported", "demo_approximate"]


class OfficialNotice(ApiModel):
    """Staff-entered notice. A missing source means it is not officially confirmed."""

    id: uuid.UUID
    kind: Literal["relocation", "temporary_closure"]
    source_name: str | None
    source_url: str | None = None
    reference: str | None = None
    new_location_description: str | None = None
    effective_date: date | None = None
    received_at: datetime
    verification_status: NoticeVerificationStatus

    @property
    def is_official(self) -> bool:
        return self.verification_status == NoticeVerificationStatus.OFFICIALLY_CONFIRMED and bool(
            self.source_name
        )


class RelocationReportSummary(ApiModel):
    """Aggregate of crowd reports. Contains no reporter information."""

    report_count: int = Field(ge=0)
    first_reported_at: datetime
    last_reported_at: datetime


class PollingUnitSummary(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    state: LocationRef
    lga: LocationRef
    ward: LocationRef
    address_description: str | None
    coordinates: Coordinates | None
    status: PollingUnitStatus
    source_name: str | None
    source_updated_at: datetime | None
    updated_at: datetime


class PollingUnitDetail(PollingUnitSummary):
    official_notices: list[OfficialNotice]
    relocation_reports: RelocationReportSummary | None

    @model_validator(mode="after")
    def official_status_requires_confirmed_notice(self) -> "PollingUnitDetail":
        has_official_relocation = any(
            notice.kind == "relocation" and notice.is_official for notice in self.official_notices
        )
        if self.status == PollingUnitStatus.OFFICIALLY_RELOCATED and not has_official_relocation:
            raise ValueError(
                "officially_relocated requires an officially confirmed relocation notice "
                "with a named source"
            )
        return self
