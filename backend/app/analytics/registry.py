"""The expected polling-unit register used as the denominator for coverage.

Coverage is always counted against the actual units in the register for each area,
never against an assumed number per ward, LGA or state."""

import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

from app.db.enums import PollingUnitStatus
from app.directory.repository import DirectoryRepository
from app.schemas.elections import Election
from app.schemas.locations import Lga, State, Ward


@dataclass(frozen=True)
class RegistryUnit:
    id: uuid.UUID
    code: str
    name: str
    ward_id: uuid.UUID
    lga_id: uuid.UUID
    state_id: uuid.UUID
    status: PollingUnitStatus
    has_coordinates: bool
    has_address: bool

    @property
    def is_incomplete(self) -> bool:
        """The register entry lacks location detail or its status is unconfirmed."""
        return (
            not self.has_coordinates
            or not self.has_address
            or self.status == PollingUnitStatus.PENDING_VERIFICATION
        )


@dataclass(frozen=True)
class Registry:
    states: dict[uuid.UUID, State]
    lgas: dict[uuid.UUID, Lga]
    wards: dict[uuid.UUID, Ward]
    units: dict[uuid.UUID, RegistryUnit]
    lgas_by_state: dict[uuid.UUID, list[uuid.UUID]]
    wards_by_lga: dict[uuid.UUID, list[uuid.UUID]]
    units_by_ward: dict[uuid.UUID, list[uuid.UUID]]
    expected_by_state: Counter[uuid.UUID]
    expected_by_lga: Counter[uuid.UUID]
    expected_by_ward: Counter[uuid.UUID]
    incomplete_by_state: Counter[uuid.UUID]
    incomplete_by_lga: Counter[uuid.UUID]
    incomplete_by_ward: Counter[uuid.UUID]

    @property
    def expected_total(self) -> int:
        return len(self.units)


@lru_cache(maxsize=4)
def _build(directory: DirectoryRepository) -> Registry:
    states = {s.id: s for s in directory.list_states()}
    lgas: dict[uuid.UUID, Lga] = {}
    wards: dict[uuid.UUID, Ward] = {}
    lgas_by_state: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    wards_by_lga: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for state_id in states:
        for lga in directory.list_lgas(state_id):
            lgas[lga.id] = lga
            lgas_by_state[state_id].append(lga.id)
            for ward in directory.list_wards(lga.id):
                wards[ward.id] = ward
                wards_by_lga[lga.id].append(ward.id)

    units: dict[uuid.UUID, RegistryUnit] = {}
    units_by_ward: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for summary in directory.list_all_polling_units():
        unit = RegistryUnit(
            id=summary.id,
            code=summary.code,
            name=summary.name,
            ward_id=summary.ward.id,
            lga_id=summary.lga.id,
            state_id=summary.state.id,
            status=summary.status,
            has_coordinates=summary.coordinates is not None,
            has_address=bool(summary.address_description),
        )
        units[unit.id] = unit
        units_by_ward[unit.ward_id].append(unit.id)

    def count(attr: str, only_incomplete: bool = False) -> Counter[uuid.UUID]:
        return Counter(
            getattr(u, attr) for u in units.values() if not only_incomplete or u.is_incomplete
        )

    return Registry(
        states=states,
        lgas=lgas,
        wards=wards,
        units=units,
        lgas_by_state=dict(lgas_by_state),
        wards_by_lga=dict(wards_by_lga),
        units_by_ward=dict(units_by_ward),
        expected_by_state=count("state_id"),
        expected_by_lga=count("lga_id"),
        expected_by_ward=count("ward_id"),
        incomplete_by_state=count("state_id", True),
        incomplete_by_lga=count("lga_id", True),
        incomplete_by_ward=count("ward_id", True),
    )


def register(directory: DirectoryRepository) -> Registry:
    """The whole polling-unit register, for name and code lookups."""
    return _build(directory)


def registry_for(directory: DirectoryRepository, election: Election) -> Registry:
    """Polling units expected to report for `election`.

    The demonstration directory defines no per-election scope, so every registered unit
    is expected for every demo election. A production register must restrict this to
    the units in the election's constituency (for example one state for a governorship
    election) so coverage is not understated."""
    del election
    return _build(directory)
