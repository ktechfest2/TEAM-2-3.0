"""Import a polling-unit register from CSV into the directory tables.

The file is validated in full before anything is written: one bad row rejects the
whole import, so the directory never holds half a register. Existing rows are
matched by code and updated in place, which keeps their ids (and every evidence
record that points at them) stable across re-imports.

Columns (header names are case-insensitive; spaces and dashes count as underscores):
  required  state, lga, ward, polling_unit_code, polling_unit_name
  optional  state_code, lga_code, ward_code, address, latitude, longitude,
            registered_voters
Codes are taken from the INEC-style polling-unit code (SS-LL-WW-PPP) when the
separate code columns are absent.
"""

import csv
import hashlib
import io
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.enums import PollingUnitStatus
from app.evidence.audit import append_event

ENTITY_DIRECTORY_IMPORT = "directory_import"
MAX_ROWS = 250_000
MAX_REPORTED_ERRORS = 50

_ALIASES = {
    "state": ("state", "state_name"),
    "lga": ("lga", "lga_name", "local_government", "local_government_area"),
    "ward": ("ward", "ward_name", "registration_area", "ra"),
    "polling_unit_code": ("polling_unit_code", "pu_code", "delimitation", "code"),
    "polling_unit_name": ("polling_unit_name", "pu_name", "polling_unit", "name"),
    "state_code": ("state_code",),
    "lga_code": ("lga_code",),
    "ward_code": ("ward_code", "ra_code"),
    "address": ("address", "address_description", "location_description", "remark"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lng", "lon", "long"),
    "registered_voters": ("registered_voters", "registered_voter", "voters"),
}
_REQUIRED = ("state", "lga", "ward", "polling_unit_code", "polling_unit_name")
_INEC_CODE = re.compile(r"^(\d{2})[-/](\d{2})[-/](\d{2})[-/](\d{3})$")
_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/-]{0,31}$")
_PART_CODE = re.compile(r"^[A-Za-z0-9]{1,16}$")

# ISO 3166-2:NG subdivision codes. A published standard, used to join boundary data.
_STATE_ISO = {
    "abia": "NG-AB", "adamawa": "NG-AD", "akwa ibom": "NG-AK", "anambra": "NG-AN",
    "bauchi": "NG-BA", "bayelsa": "NG-BY", "benue": "NG-BE", "borno": "NG-BO",
    "cross river": "NG-CR", "delta": "NG-DE", "ebonyi": "NG-EB", "edo": "NG-ED",
    "ekiti": "NG-EK", "enugu": "NG-EN", "gombe": "NG-GO", "imo": "NG-IM",
    "jigawa": "NG-JI", "kaduna": "NG-KD", "kano": "NG-KN", "katsina": "NG-KT",
    "kebbi": "NG-KE", "kogi": "NG-KO", "kwara": "NG-KW", "lagos": "NG-LA",
    "nasarawa": "NG-NA", "niger": "NG-NI", "ogun": "NG-OG", "ondo": "NG-ON",
    "osun": "NG-OS", "oyo": "NG-OY", "plateau": "NG-PL", "rivers": "NG-RI",
    "sokoto": "NG-SO", "taraba": "NG-TA", "yobe": "NG-YO", "zamfara": "NG-ZA",
    "federal capital territory": "NG-FC", "fct": "NG-FC", "abuja": "NG-FC",
}  # fmt: skip


@dataclass(frozen=True)
class RowError:
    row: int
    message: str


@dataclass
class ImportReport:
    rows: int = 0
    states_created: int = 0
    lgas_created: int = 0
    wards_created: int = 0
    units_created: int = 0
    units_updated: int = 0
    units_unchanged: int = 0
    errors: list[RowError] = field(default_factory=list)
    error_count: int = 0
    sha256: str = ""
    applied: bool = False
    import_id: uuid.UUID | None = None


@dataclass(frozen=True)
class _Row:
    number: int
    state: str
    state_code: str
    lga: str
    lga_code: str
    ward: str
    ward_code: str
    code: str
    name: str
    address: str | None
    latitude: float | None
    longitude: float | None
    registered_voters: int | None


def _key(header: str) -> str:
    return re.sub(r"[\s\-]+", "_", header.strip().casefold())


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


def iso_code_for(state_name: str) -> str | None:
    name = _clean(state_name).casefold().removesuffix(" state").strip()
    return _STATE_ISO.get(name)


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="strict")


def _columns(headers: Iterable[str]) -> dict[str, str]:
    by_key = {_key(h): h for h in headers if h}
    mapping: dict[str, str] = {}
    for column, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in by_key:
                mapping[column] = by_key[alias]
                break
    return mapping


def _parse_rows(text: str, report: ImportReport) -> list[_Row]:
    def fail(row: int, message: str) -> None:
        report.error_count += 1
        if len(report.errors) < MAX_REPORTED_ERRORS:
            report.errors.append(RowError(row, message))

    reader = csv.DictReader(io.StringIO(text, newline=""))
    columns = _columns(reader.fieldnames or [])
    missing = [c for c in _REQUIRED if c not in columns]
    if missing:
        fail(1, "Missing required column(s): " + ", ".join(missing) + ".")
        return []

    rows: list[_Row] = []
    seen: dict[str, int] = {}
    for number, raw in enumerate(reader, start=2):
        if number - 1 > MAX_ROWS:
            fail(number, f"The file has more than {MAX_ROWS} rows.")
            break

        def get(column: str, raw: dict[str, str | None] = raw) -> str:
            header = columns.get(column)
            return _clean(raw.get(header)) if header else ""

        if not any(_clean(v) for v in raw.values() if isinstance(v, str)):
            continue
        report.rows += 1
        problems: list[str] = []
        state, lga, ward = get("state"), get("lga"), get("ward")
        code, name = get("polling_unit_code").upper(), get("polling_unit_name")
        for label, value, limit in (
            ("state", state, 120),
            ("lga", lga, 120),
            ("ward", ward, 120),
            ("polling_unit_name", name, 200),
        ):
            if not value:
                problems.append(f"{label} is empty")
            elif len(value) > limit:
                problems.append(f"{label} is longer than {limit} characters")
        if not _CODE.fullmatch(code):
            problems.append("polling_unit_code is missing or has unexpected characters")

        inec = _INEC_CODE.fullmatch(code)
        state_code = get("state_code") or (inec.group(1) if inec else "")
        lga_code = get("lga_code") or (inec.group(2) if inec else "")
        ward_code = get("ward_code") or (inec.group(3) if inec else "")
        for label, value in (("state_code", state_code), ("lga_code", lga_code)):
            if not _PART_CODE.fullmatch(value):
                problems.append(f"{label} is missing (add the column or use SS-LL-WW-PPP codes)")
        if not _PART_CODE.fullmatch(ward_code):
            problems.append("ward_code is missing (add the column or use SS-LL-WW-PPP codes)")

        latitude = longitude = None
        lat_text, lng_text = get("latitude"), get("longitude")
        if lat_text or lng_text:
            try:
                latitude, longitude = float(lat_text), float(lng_text)
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise ValueError
            except ValueError:
                problems.append("latitude and longitude must both be valid coordinates")
                latitude = longitude = None
        voters = None
        if voters_text := get("registered_voters").replace(",", ""):
            if voters_text.isdigit() and int(voters_text) <= 100_000:
                voters = int(voters_text)
            else:
                problems.append("registered_voters must be a whole number")

        if code in seen:
            problems.append(f"polling_unit_code {code} already appears on row {seen[code]}")
        else:
            seen[code] = number

        if problems:
            fail(number, "; ".join(problems) + ".")
            continue
        address = get("address")
        rows.append(
            _Row(
                number=number,
                state=state,
                state_code=state_code.upper(),
                lga=lga,
                lga_code=lga_code.upper(),
                ward=ward,
                ward_code=ward_code.upper(),
                code=code,
                name=name,
                address=address[:1000] or None,
                latitude=latitude,
                longitude=longitude,
                registered_voters=voters,
            )
        )
    if report.rows == 0 and report.error_count == 0:
        fail(1, "The file has no polling-unit rows.")
    return rows


def import_register(
    db: Session,
    content: bytes,
    *,
    source_name: str,
    source_reference: str | None,
    actor_id: uuid.UUID | None,
    filename: str | None = None,
    dry_run: bool = False,
) -> ImportReport:
    """Validate and, unless `dry_run`, apply the register. Commits on success."""
    report = ImportReport(sha256=hashlib.sha256(content).hexdigest())
    try:
        text = _decode(content)
    except UnicodeDecodeError:
        report.errors.append(RowError(1, "The file is not UTF-8 or Windows-1252 text."))
        report.error_count = 1
        return report
    rows = _parse_rows(text, report)
    if report.error_count:
        return report

    states = {s.code: s for s in db.scalars(select(models.State))}
    lgas = {(lga.state_id, lga.code): lga for lga in db.scalars(select(models.Lga))}
    wards = {(w.lga_id, w.code): w for w in db.scalars(select(models.Ward))}
    units = {u.code: u for u in db.scalars(select(models.PollingUnit))}
    now = datetime.now(UTC)

    for row in rows:
        state = states.get(row.state_code)
        if state is None:
            state = models.State(
                id=uuid.uuid4(), code=row.state_code, name=row.state, iso_code=None
            )
            iso = iso_code_for(row.state)
            if iso and iso not in {s.iso_code for s in states.values()}:
                state.iso_code = iso
            states[row.state_code] = state
            db.add(state)
            report.states_created += 1
        lga = lgas.get((state.id, row.lga_code))
        if lga is None:
            lga = models.Lga(id=uuid.uuid4(), state_id=state.id, code=row.lga_code, name=row.lga)
            lgas[(state.id, row.lga_code)] = lga
            db.add(lga)
            report.lgas_created += 1
        ward = wards.get((lga.id, row.ward_code))
        if ward is None:
            ward = models.Ward(id=uuid.uuid4(), lga_id=lga.id, code=row.ward_code, name=row.ward)
            wards[(lga.id, row.ward_code)] = ward
            db.add(ward)
            report.wards_created += 1

        values = {
            "ward_id": ward.id,
            "name": row.name,
            "address_description": row.address,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "registered_voters": row.registered_voters,
            "source_name": source_name,
            "source_reference": source_reference,
        }
        unit = units.get(row.code)
        if unit is None:
            units[row.code] = unit = models.PollingUnit(
                id=uuid.uuid4(),
                code=row.code,
                status=PollingUnitStatus.ACTIVE,
                source_updated_at=now,
                **values,
            )
            db.add(unit)
            report.units_created += 1
        elif any(getattr(unit, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(unit, k, v)
            unit.source_updated_at = now
            report.units_updated += 1
        else:
            report.units_unchanged += 1

    if dry_run:
        db.rollback()
        return report

    report.import_id = uuid.uuid4()
    append_event(
        db,
        entity_type=ENTITY_DIRECTORY_IMPORT,
        entity_id=report.import_id,
        action="directory.imported",
        actor_id=actor_id,
        details={
            "source_name": source_name,
            "source_reference": source_reference,
            "filename": (filename or "")[:200] or None,
            "sha256": report.sha256,
            "rows": report.rows,
            "states_created": report.states_created,
            "lgas_created": report.lgas_created,
            "wards_created": report.wards_created,
            "units_created": report.units_created,
            "units_updated": report.units_updated,
        },
    )
    db.commit()
    report.applied = True
    return report
