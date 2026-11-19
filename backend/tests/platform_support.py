"""TEST DATA ONLY. A whole-API harness on a temporary SQLite store and private storage,
over the fictional demo directory. Nothing here is a real report, result or person."""

import io
import random
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from app.analytics.demo_seed import OBSERVER, DemoPipeline, demo_values
from app.core.config import get_settings
from app.directory.repository import DemoDirectoryRepository, PollingUnitQuery
from app.evidence.db import create_dev_engine, get_evidence_db
from app.evidence.storage import LocalStorage, get_storage
from app.main import create_app

DIRECTORY = DemoDirectoryRepository()
ELECTIONS = DIRECTORY.list_elections()
# USSD and SMS answer for the latest election, which is also the demo-seeded one.
CHANNEL_ELECTION = ELECTIONS[-1]
UNITS = DIRECTORY.search_polling_units(PollingUnitQuery(), 1, 50).items

def unit_by_code(code: str):
    return next(u for u in UNITS if u.code == code)

class Platform:
    def __init__(self, tmp_path) -> None:
        get_settings.cache_clear()
        self.app = create_app()
        engine = create_dev_engine(str(tmp_path / "platform.sqlite3"))
        self.factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        self.storage = LocalStorage(str(tmp_path / "storage"), "evidence")

        def db_override() -> Iterator[Session]:
            with self.factory() as session:
                yield session

        self.app.dependency_overrides[get_evidence_db] = db_override
        self.app.dependency_overrides[get_storage] = lambda: self.storage
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def pipeline(self, db: Session) -> DemoPipeline:
        return DemoPipeline(db, self.storage, get_settings(), DIRECTORY, CHANNEL_ELECTION)

    def seed_results(self, verified: list[str], reported: list[str]) -> None:
        """Drive generated sheets through the real evidence workflow: some units end
        verified, others reported (accepted, not yet reviewed)."""
        with self.factory() as db:
            pipe = self.pipeline(db)
            for seed, code in enumerate(verified + reported, start=1):
                unit = DIRECTORY.get_polling_unit(unit_by_code(code).id)
                values = demo_values(unit, CHANNEL_ELECTION, random.Random(f"{code}/{seed}"))
                submission = pipe.accepted(unit.id, OBSERVER, values, seed)
                if code in verified:
                    pipe.verify(submission)

    def report(
        self,
        *,
        unit_code: str = "FC1-A1",
        headers: dict[str, str] | None = None,
        file: tuple[str, bytes, str] | None = None,
        key: str | None = None,
        **overrides: Any,
    ):
        unit = unit_by_code(unit_code)
        form: dict[str, Any] = {
            "election_id": str(CHANNEL_ELECTION.id),
            "category": "vote_buying",
            "description": (
                "TEST DATA. People were handing out cash and rice to voters in the queue "
                "near the polling unit entrance."
            ),
            "state_id": str(unit.state.id),
            "lga_id": str(unit.lga.id),
            "ward_id": str(unit.ward.id),
            "polling_unit_id": str(unit.id),
            "occurred_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "time_is_approximate": "true",
        }
        form.update({k: v for k, v in overrides.items() if v is not None})
        for name in [k for k, v in overrides.items() if v is None]:
            form.pop(name, None)
        return self.client.post(
            "/api/v1/incidents",
            data=form,
            files={"file": file} if file else None,
            headers={"Idempotency-Key": key or str(uuid.uuid4()), **(headers or {})},
        )

def photo(size: tuple[int, int] = (640, 480), *, with_exif: bool = False) -> bytes:
    image = Image.new("RGB", size, (200, 120, 60))
    buffer = io.BytesIO()
    if with_exif:
        exif = Image.Exif()
        exif[0x010F] = "TestCameraMaker"  # Make
        exif[0x0110] = "TestCameraModel"  # Model
        image.save(buffer, "JPEG", exif=exif.tobytes())
    else:
        image.save(buffer, "JPEG")
    return buffer.getvalue()
