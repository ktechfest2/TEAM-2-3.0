"""Administration of the database-backed directory: the polling-unit register and
election configuration. Every change is written to the hash-chained audit log."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import Principal, require_roles
from app.db import models
from app.db.enums import ElectionStatus, Role
from app.directory.database import election_out
from app.directory.importer import ENTITY_DIRECTORY_IMPORT, import_register
from app.evidence.audit import append_event
from app.evidence.db import get_evidence_db
from app.evidence.templates import load_templates
from app.schemas.elections import Election, Party
from app.schemas.evidence import UtcDateTime

router = APIRouter(prefix="/admin", tags=["admin"])

Db = Annotated[Session, Depends(get_evidence_db)]
Manager = Annotated[Principal, Depends(require_roles(Role.ELECTION_ADMIN, Role.SYSTEM_ADMIN))]

ENTITY_ELECTION = "election"
MAX_IMPORT_BYTES = 60 * 1024 * 1024


def _require_database_directory() -> None:
    if get_settings().directory_source != "database":
        raise AppError(
            "directory_is_demo",
            "The API is serving the demo directory. Set DIRECTORY_SOURCE=database to manage "
            "the real register.",
            status_code=409,
        )


class ImportErrorOut(BaseModel):
    row: int
    message: str


class ImportReportOut(BaseModel):
    applied: bool
    import_id: uuid.UUID | None
    sha256: str
    rows: int
    states_created: int
    lgas_created: int
    wards_created: int
    units_created: int
    units_updated: int
    units_unchanged: int
    error_count: int
    errors: list[ImportErrorOut]


class ImportRecordOut(BaseModel):
    id: uuid.UUID
    imported_at: UtcDateTime
    actor_email: str | None
    details: dict[str, Any]


class RegisterSummaryOut(BaseModel):
    states: int
    lgas: int
    wards: int
    polling_units: int
    with_coordinates: int
    imports: list[ImportRecordOut]


class TemplateOut(BaseModel):
    id: str
    name: str
    notice: str


class AdminElectionOut(BaseModel):
    election: Election
    status: ElectionStatus
    submissions: int


class ElectionIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    election_label: str = Field(min_length=2, max_length=200)
    election_date: date
    template_id: str
    parties: list[Party] = Field(min_length=1, max_length=40)
    status: ElectionStatus = ElectionStatus.SCHEDULED

    @field_validator("name", "election_label")
    @classmethod
    def tidy(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def unique_parties(self) -> "ElectionIn":
        codes = [p.code for p in self.parties]
        if len(set(codes)) != len(codes):
            raise ValueError("party codes must be unique")
        return self


class ElectionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    election_label: str | None = Field(default=None, min_length=2, max_length=200)
    election_date: date | None = None
    template_id: str | None = None
    parties: list[Party] | None = Field(default=None, min_length=1, max_length=40)
    status: ElectionStatus | None = None

    @model_validator(mode="after")
    def unique_parties(self) -> "ElectionPatch":
        if self.parties is not None:
            codes = [p.code for p in self.parties]
            if len(set(codes)) != len(codes):
                raise ValueError("party codes must be unique")
        return self


def _check_template(template_id: str) -> None:
    if template_id not in load_templates():
        raise AppError("unknown_template", "That result-sheet template does not exist.", 422)


def _submission_count(db: Session, election_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(models.EvidenceSubmission)
            .where(models.EvidenceSubmission.election_id == election_id)
        )
        or 0
    )


def _admin_election(db: Session, row: models.Election) -> AdminElectionOut:
    return AdminElectionOut(
        election=election_out(row),
        status=row.status,
        submissions=_submission_count(db, row.id),
    )


@router.get("/register", response_model=RegisterSummaryOut)
def register_summary(db: Db, _: Manager) -> RegisterSummaryOut:
    def count(model: type[models.Base]) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    events = db.execute(
        select(models.AuditEvent, models.User.email)
        .outerjoin(models.User, models.User.id == models.AuditEvent.actor_id)
        .where(models.AuditEvent.entity_type == ENTITY_DIRECTORY_IMPORT)
        .order_by(models.AuditEvent.created_at.desc())
        .limit(10)
    ).all()
    return RegisterSummaryOut(
        states=count(models.State),
        lgas=count(models.Lga),
        wards=count(models.Ward),
        polling_units=count(models.PollingUnit),
        with_coordinates=db.scalar(
            select(func.count())
            .select_from(models.PollingUnit)
            .where(models.PollingUnit.latitude.is_not(None))
        )
        or 0,
        imports=[
            ImportRecordOut(
                id=event.entity_id,
                imported_at=event.created_at,
                actor_email=email,
                details=event.details,
            )
            for event, email in events
        ],
    )


@router.post("/register/import", response_model=ImportReportOut)
async def import_polling_units(
    request: Request,
    db: Db,
    principal: Manager,
    file: Annotated[UploadFile, File(description="Polling-unit register as CSV")],
    source_name: Annotated[str, Form(min_length=3, max_length=200)],
    source_reference: Annotated[str | None, Form(max_length=200)] = None,
    dry_run: Annotated[bool, Form()] = False,
) -> ImportReportOut:
    _require_database_directory()
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_IMPORT_BYTES + 64 * 1024:
        raise AppError("file_too_large", "The register file is larger than 60 MB.", 413)
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise AppError("file_too_large", "The register file is larger than 60 MB.", 413)
    if not content.strip():
        raise AppError("empty_file", "The register file is empty.", 422)
    report = import_register(
        db,
        content,
        source_name=" ".join(source_name.split()),
        source_reference=(" ".join(source_reference.split()) or None) if source_reference else None,
        actor_id=principal.user_id,
        filename=file.filename,
        dry_run=dry_run,
    )
    return ImportReportOut(
        applied=report.applied,
        import_id=report.import_id,
        sha256=report.sha256,
        rows=report.rows,
        states_created=report.states_created,
        lgas_created=report.lgas_created,
        wards_created=report.wards_created,
        units_created=report.units_created,
        units_updated=report.units_updated,
        units_unchanged=report.units_unchanged,
        error_count=report.error_count,
        errors=[ImportErrorOut(row=e.row, message=e.message) for e in report.errors],
    )


@router.get("/election-templates", response_model=list[TemplateOut])
def list_templates(_: Manager) -> list[TemplateOut]:
    return [TemplateOut(id=t.id, name=t.name, notice=t.notice) for t in load_templates().values()]


@router.get("/elections", response_model=list[AdminElectionOut])
def list_admin_elections(db: Db, _: Manager) -> list[AdminElectionOut]:
    _require_database_directory()
    rows = db.scalars(
        select(models.Election).order_by(models.Election.election_date.desc(), models.Election.name)
    ).all()
    return [_admin_election(db, row) for row in rows]


@router.post("/elections", response_model=AdminElectionOut, status_code=status.HTTP_201_CREATED)
def create_election(payload: ElectionIn, db: Db, principal: Manager) -> AdminElectionOut:
    _require_database_directory()
    _check_template(payload.template_id)
    row = models.Election(
        id=uuid.uuid4(),
        name=payload.name,
        election_label=payload.election_label.upper(),
        election_date=payload.election_date,
        template_id=payload.template_id,
        parties=[p.model_dump() for p in payload.parties],
        status=payload.status,
        created_by=principal.user_id,
    )
    db.add(row)
    append_event(
        db,
        entity_type=ENTITY_ELECTION,
        entity_id=row.id,
        action="election.created",
        actor_id=principal.user_id,
        details={
            "name": row.name,
            "election_date": row.election_date.isoformat(),
            "template_id": row.template_id,
            "parties": [p.code for p in payload.parties],
            "status": row.status.value,
        },
    )
    db.commit()
    return _admin_election(db, row)


@router.patch("/elections/{election_id}", response_model=AdminElectionOut)
def update_election(
    election_id: uuid.UUID, payload: ElectionPatch, db: Db, principal: Manager
) -> AdminElectionOut:
    _require_database_directory()
    row = db.get(models.Election, election_id)
    if row is None:
        raise AppError("not_found", "Election not found.", 404)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return _admin_election(db, row)
    if {"template_id", "parties", "election_label"} & changes.keys() and _submission_count(
        db, election_id
    ):
        raise AppError(
            "election_has_evidence",
            "Evidence has already been submitted for this election, so its result-sheet "
            "label, template and party list can no longer change.",
            409,
        )
    if "template_id" in changes:
        _check_template(changes["template_id"])
    if "election_label" in changes:
        changes["election_label"] = " ".join(changes["election_label"].split()).upper()
    if "name" in changes:
        changes["name"] = " ".join(changes["name"].split())
    for key, value in changes.items():
        setattr(row, key, value)
    details: dict[str, Any] = {
        k: (v.isoformat() if isinstance(v, date) else v) for k, v in changes.items()
    }
    if "parties" in details:
        details["parties"] = [p["code"] for p in details["parties"]]
    append_event(
        db,
        entity_type=ENTITY_ELECTION,
        entity_id=row.id,
        action="election.updated",
        actor_id=principal.user_id,
        details=details,
    )
    db.commit()
    return _admin_election(db, row)
