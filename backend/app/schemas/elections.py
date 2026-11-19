import uuid
from datetime import date

from pydantic import Field

from app.schemas.common import ApiModel


class Party(ApiModel):
    code: str = Field(pattern=r"^[A-Z0-9]{1,12}$")
    name: str


class Election(ApiModel):
    id: uuid.UUID
    name: str
    # Text printed on the result sheet, used to cross-check the sheet against the submission.
    election_label: str
    election_date: date
    template_id: str
    # Parties on the ballot for this election. Configuration, not code.
    parties: list[Party]
    is_demo: bool
