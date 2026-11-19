import uuid

from app.schemas.common import ApiModel


class LocationRef(ApiModel):
    id: uuid.UUID
    name: str


class State(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    # ISO 3166-2 subdivision code (for example NG-LA). Joins the state to boundary data.
    iso_code: str | None = None


class Lga(ApiModel):
    id: uuid.UUID
    state_id: uuid.UUID
    code: str
    name: str


class Ward(ApiModel):
    id: uuid.UUID
    lga_id: uuid.UUID
    code: str
    name: str
