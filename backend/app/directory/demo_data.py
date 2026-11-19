"""Demonstration directory. NOT INEC data.

State and LGA names are real place names. Every ward, polling unit, code,
address and notice below is fictional and labelled as such. Coordinates are
rough LGA-area points with a small offset so markers do not overlap; they
are marked `demo_approximate` and do not locate any real polling unit.

Replace this module with an import of the official INEC polling-unit register
(see docs/data-sources.md) before any public use.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.db.enums import (
    NoticeVerificationStatus,
    PollingUnitStatus,
    UpdateCategory,
    UpdateVerificationStatus,
)
from app.schemas.common import DataSource
from app.schemas.elections import Election, Party
from app.schemas.locations import Lga, LocationRef, State, Ward
from app.schemas.polling_units import (
    Coordinates,
    OfficialNotice,
    PollingUnitDetail,
    RelocationReportSummary,
)
from app.schemas.updates import ElectionUpdate

DEMO_SOURCE = DataSource(
    kind="demo",
    label="Sample data",
    description=(
        "Sample directory for development. Names, codes, addresses and notices are not INEC data."
    ),
)

DEMO_SOURCE_NAME = "VoteTrace demonstration dataset (not INEC)"
DEMO_NOTICE_SOURCE = "Sample notice (not from INEC)"

_NAMESPACE = uuid.UUID("6f6b1c1e-6a39-4e43-9a49-3f1b8a2f6d10")
_DATASET_DATE = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def _id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, "/".join(parts))


@dataclass(frozen=True)
class _LgaSeed:
    name: str
    centre: tuple[float, float]
    # Polling units in each fictional ward. Deliberately uneven, as real registers are.
    units_per_ward: tuple[int, ...]


# ISO 3166-2 codes are the real codes for these states. They join the registry to the
# state boundary layer without relying on names.
_STATE_ISO = {"Federal Capital Territory": "NG-FC", "Lagos": "NG-LA", "Kano": "NG-KN"}
_ABBREV = {"Federal Capital Territory": "FC", "Lagos": "LA", "Kano": "KN"}

_STATES: dict[str, list[_LgaSeed]] = {
    "Federal Capital Territory": [
        _LgaSeed("Abuja Municipal", (9.0579, 7.4951), (3, 4, 2)),
        _LgaSeed("Bwari", (9.2833, 7.3833), (3, 2)),
    ],
    "Lagos": [
        _LgaSeed("Ikeja", (6.6018, 3.3515), (4, 3, 3)),
        _LgaSeed("Eti-Osa", (6.4590, 3.6015), (3, 2)),
    ],
    "Kano": [
        _LgaSeed("Kano Municipal", (12.0000, 8.5167), (3, 5)),
        _LgaSeed("Nassarawa", (11.9833, 8.5500), (2, 3, 2)),
    ],
}


@dataclass(frozen=True)
class DemoDataset:
    states: list[State]
    lgas: list[Lga]
    wards: list[Ward]
    polling_units: list[PollingUnitDetail]
    updates: list[ElectionUpdate]
    elections: list[Election]


# Fictional parties: codes and names deliberately do not match any registered party.
DEMO_PARTIES = [
    Party(code="PA", name="Party A"),
    Party(code="PB", name="Party B"),
    Party(code="PC", name="Party C"),
    Party(code="PD", name="Party D"),
]


def _demo_elections() -> list[Election]:
    return [
        Election(
            id=_id("election", "demo-governorship-2026"),
            name="Governorship Election 2026 (sample)",
            election_label="GOVERNORSHIP",
            election_date=date(2026, 12, 5),
            template_id="generic-pu-result-v1",
            parties=DEMO_PARTIES,
            is_demo=True,
        ),
        Election(
            id=_id("election", "demo-house-of-assembly-2026"),
            name="State House of Assembly Election 2026 (sample)",
            election_label="HOUSE OF ASSEMBLY",
            election_date=date(2026, 12, 5),
            template_id="generic-pu-result-v1",
            parties=DEMO_PARTIES[:3],
            is_demo=True,
        ),
        Election(
            id=_id("election", "demo-presidential-2027"),
            name="Presidential Election 2027 (sample)",
            election_label="PRESIDENTIAL",
            election_date=date(2027, 2, 20),
            template_id="generic-pu-result-v1",
            parties=DEMO_PARTIES,
            is_demo=True,
        ),
    ]


def _special_cases(key: str) -> dict:
    """A handful of units carry non-default statuses so every state is visible."""
    received = datetime(2026, 11, 10, 14, 30, tzinfo=UTC)
    if key.endswith("01-01-01-002"):
        return {
            "status": PollingUnitStatus.OFFICIALLY_RELOCATED,
            "official_notices": [
                OfficialNotice(
                    id=_id("notice", key),
                    kind="relocation",
                    source_name=DEMO_NOTICE_SOURCE,
                    reference="DEMO-REF-0001",
                    new_location_description=("Moved to the community hall across the road."),
                    effective_date=date(2026, 11, 20),
                    received_at=received,
                    verification_status=NoticeVerificationStatus.OFFICIALLY_CONFIRMED,
                )
            ],
        }
    if key.endswith("01-01-02-001"):
        return {
            "status": PollingUnitStatus.RELOCATION_REPORTED,
            "relocation_reports": RelocationReportSummary(
                report_count=3,
                first_reported_at=datetime(2026, 11, 12, 8, 0, tzinfo=UTC),
                last_reported_at=datetime(2026, 11, 13, 17, 45, tzinfo=UTC),
            ),
        }
    if key.endswith("02-01-01-003"):
        return {
            "status": PollingUnitStatus.TEMPORARILY_UNAVAILABLE,
            "official_notices": [
                OfficialNotice(
                    id=_id("notice", key),
                    kind="temporary_closure",
                    source_name=None,
                    received_at=received,
                    verification_status=NoticeVerificationStatus.AWAITING_CONFIRMATION,
                )
            ],
        }
    if key.endswith("03-02-02-003"):
        return {"status": PollingUnitStatus.PENDING_VERIFICATION, "source_name": None}
    return {}


def build_demo_dataset() -> DemoDataset:
    states: list[State] = []
    lgas: list[Lga] = []
    wards: list[Ward] = []
    units: list[PollingUnitDetail] = []

    for s_index, (state_name, lga_seeds) in enumerate(_STATES.items(), start=1):
        abbrev = _ABBREV[state_name]
        state = State(
            id=_id("state", state_name),
            code=abbrev,
            name=state_name,
            iso_code=_STATE_ISO[state_name],
        )
        states.append(state)
        for l_index, seed in enumerate(lga_seeds, start=1):
            lga = Lga(
                id=_id("lga", state_name, seed.name),
                state_id=state.id,
                code=f"{abbrev}{l_index}",
                name=seed.name,
            )
            lgas.append(lga)
            for w_index, unit_count in enumerate(seed.units_per_ward, start=1):
                ward_letter = chr(ord("A") + w_index - 1)
                ward = Ward(
                    id=_id("ward", state_name, seed.name, ward_letter),
                    lga_id=lga.id,
                    code=f"{abbrev}{l_index}-{ward_letter}",
                    name=f"Ward {ward_letter}",
                )
                wards.append(ward)
                for p_index in range(1, unit_count + 1):
                    # The id stays on the original key so existing submissions still match.
                    key = f"DEMO-{s_index:02d}-{l_index:02d}-{w_index:02d}-{p_index:03d}"
                    code = f"{abbrev}{l_index}-{ward_letter}{p_index}"
                    # Every third unit has no coordinates, to exercise the no-map path.
                    coordinates = None
                    if p_index % 3 != 0:
                        lat, lng = seed.centre
                        offset = 0.004 * (w_index * 3 + p_index)
                        coordinates = Coordinates(
                            latitude=round(lat + offset, 5),
                            longitude=round(lng + offset / 2, 5),
                            precision="demo_approximate",
                        )
                    fields: dict = {
                        "id": _id("pu", key),
                        "code": code,
                        "name": f"Polling Unit {ward_letter}{p_index:02d}",
                        "state": LocationRef(id=state.id, name=state.name),
                        "lga": LocationRef(id=lga.id, name=lga.name),
                        "ward": LocationRef(id=ward.id, name=ward.name),
                        "address_description": (
                            None if p_index % 3 == 0 else f"Sample address, {seed.name}"
                        ),
                        "coordinates": coordinates,
                        "status": PollingUnitStatus.ACTIVE,
                        "source_name": DEMO_SOURCE_NAME,
                        "source_updated_at": _DATASET_DATE,
                        "updated_at": _DATASET_DATE,
                        "official_notices": [],
                        "relocation_reports": None,
                    }
                    fields.update(_special_cases(key))
                    units.append(PollingUnitDetail(**fields))

    relocated = next(u for u in units if u.status == PollingUnitStatus.OFFICIALLY_RELOCATED)
    reported = next(u for u in units if u.status == PollingUnitStatus.RELOCATION_REPORTED)

    updates = [
        ElectionUpdate(
            id=_id("update", "relocation-official"),
            title=f"Relocation confirmed for {relocated.code}",
            description="Sample confirmed relocation. A real entry cites the INEC notice.",
            category=UpdateCategory.POLLING_UNIT_RELOCATION,
            source_name=DEMO_NOTICE_SOURCE,
            source_url=None,
            reference="DEMO-REF-0001",
            verification_status=UpdateVerificationStatus.OFFICIALLY_CONFIRMED,
            polling_unit_id=relocated.id,
            published_at=datetime(2026, 11, 10, 15, 0, tzinfo=UTC),
            is_demo=True,
        ),
        ElectionUpdate(
            id=_id("update", "relocation-reported"),
            title=f"Relocation reported for {reported.code}",
            description="Members of the public say this unit has moved. Not yet confirmed.",
            category=UpdateCategory.POLLING_UNIT_RELOCATION,
            source_name="Public reports",
            source_url=None,
            reference=None,
            verification_status=UpdateVerificationStatus.REPORTED_UNVERIFIED,
            polling_unit_id=reported.id,
            published_at=datetime(2026, 11, 13, 18, 0, tzinfo=UTC),
            is_demo=True,
        ),
        ElectionUpdate(
            id=_id("update", "schedule"),
            title="Election schedule notice",
            description="Sample schedule notice. Not a real timetable.",
            category=UpdateCategory.ELECTION_SCHEDULE,
            source_name=DEMO_SOURCE_NAME,
            source_url=None,
            reference="DEMO-REF-0002",
            verification_status=UpdateVerificationStatus.INDEPENDENTLY_VERIFIED,
            polling_unit_id=None,
            published_at=datetime(2026, 11, 5, 10, 0, tzinfo=UTC),
            is_demo=True,
        ),
        ElectionUpdate(
            id=_id("update", "delay"),
            title="Voting delay reported",
            description="Unconfirmed report of a late opening. Treat with caution.",
            category=UpdateCategory.VOTING_DELAY,
            source_name="Public reports",
            source_url=None,
            reference=None,
            verification_status=UpdateVerificationStatus.REPORTED_UNVERIFIED,
            polling_unit_id=None,
            published_at=datetime(2026, 11, 14, 8, 30, tzinfo=UTC),
            is_demo=True,
        ),
        ElectionUpdate(
            id=_id("update", "security"),
            title="Public security notice",
            description="Sample safety notice. Real notices name the issuing agency.",
            category=UpdateCategory.SECURITY_NOTICE,
            source_name=DEMO_SOURCE_NAME,
            source_url=None,
            reference="DEMO-REF-0003",
            verification_status=UpdateVerificationStatus.INDEPENDENTLY_VERIFIED,
            polling_unit_id=None,
            published_at=datetime(2026, 11, 8, 12, 0, tzinfo=UTC),
            is_demo=True,
        ),
        ElectionUpdate(
            id=_id("update", "general"),
            title="How to check your polling unit",
            description=(
                "Search by state, LGA, ward, name or code. "
                "Confirm your polling unit with INEC before election day."
            ),
            category=UpdateCategory.GENERAL_INFORMATION,
            source_name="VoteTrace",
            source_url=None,
            reference=None,
            verification_status=UpdateVerificationStatus.INDEPENDENTLY_VERIFIED,
            polling_unit_id=None,
            published_at=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
            is_demo=True,
        ),
    ]

    return DemoDataset(
        states=states,
        lgas=lgas,
        wards=wards,
        polling_units=units,
        updates=updates,
        elections=_demo_elections(),
    )
