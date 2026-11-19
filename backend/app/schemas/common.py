from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DataSource(ApiModel):
    """Provenance attached to every directory response."""

    kind: Literal["demo", "official"]
    label: str
    description: str


class ListResponse[T](ApiModel):
    items: list[T]
    data_source: DataSource
    generated_at: datetime


class PageResponse[T](ApiModel):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int
    data_source: DataSource
    generated_at: datetime


class ItemResponse[T](ApiModel):
    item: T
    data_source: DataSource
    generated_at: datetime
