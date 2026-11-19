import uuid
from datetime import datetime

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from app.db.enums import UpdateCategory, UpdateVerificationStatus
from app.schemas.common import ApiModel


class ElectionUpdate(ApiModel):
    id: uuid.UUID
    title: str
    description: str
    category: UpdateCategory
    source_name: str
    source_url: str | None
    reference: str | None
    verification_status: UpdateVerificationStatus
    polling_unit_id: uuid.UUID | None
    published_at: datetime
    is_demo: bool


class ElectionUpdateCreate(ApiModel):
    """Payload for staff publishing. Clients cannot set ids, timestamps or authorship."""

    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=4000)
    category: UpdateCategory
    source_name: str = Field(min_length=2, max_length=200)
    source_url: AnyHttpUrl | None = None
    reference: str | None = Field(default=None, max_length=200)
    verification_status: UpdateVerificationStatus
    polling_unit_id: uuid.UUID | None = None

    @field_validator("source_url")
    @classmethod
    def https_only(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("source_url must use https")
        return value

    @model_validator(mode="after")
    def official_needs_traceable_source(self) -> "ElectionUpdateCreate":
        if self.verification_status == UpdateVerificationStatus.OFFICIALLY_CONFIRMED and not (
            self.reference or self.source_url
        ):
            raise ValueError("officially_confirmed updates need a reference or a source_url")
        return self
