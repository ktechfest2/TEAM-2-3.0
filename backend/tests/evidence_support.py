"""TEST DATA ONLY. Generated images and OCR tokens for automated tests. Nothing here is
a real result sheet, a real polling unit result or real election data."""

import io
import random
import uuid
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageDraw

from app.directory.repository import DemoDirectoryRepository, PollingUnitQuery
from app.evidence.ocr import OcrResult, OcrToken
from tests.helpers import make_token

TEST_DATA_LABEL = "TEST DATA - NOT A REAL RESULT SHEET"

def make_sheet_image(
    seed: int = 1, size: tuple[int, int] = (900, 1200), fmt: str = "JPEG", quality: int = 90
) -> bytes:
    """A synthetic, clearly labelled page. Different seeds give visually different images."""
    rng = random.Random(seed)
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 30), TEST_DATA_LABEL, fill="black")
    for row in range(14):
        y = 90 + row * 70
        width = rng.randint(size[0] // 4, max(size[0] // 4 + 1, size[0] - 120))
        shade = rng.randint(0, 160)
        draw.rectangle((40, y, 40 + width, y + 30), fill=(shade, shade, shade))
    for _ in range(40):
        x, y = rng.randint(0, size[0] - 60), rng.randint(0, size[1] - 60)
        draw.ellipse((x, y, x + rng.randint(10, 60), y + rng.randint(10, 60)), outline="black")
    buffer = io.BytesIO()
    if fmt == "JPEG":
        image.save(buffer, fmt, quality=quality)
    else:
        image.save(buffer, fmt)
    return buffer.getvalue()

def reencode(data: bytes, quality: int = 70) -> bytes:
    with Image.open(io.BytesIO(data)) as source:
        buffer = io.BytesIO()
        source.convert("RGB").save(buffer, "JPEG", quality=quality)
        return buffer.getvalue()

def sheet_tokens(
    lines: list[str], confidence: float = 0.96, overrides: dict[str, float] | None = None
) -> list[OcrToken]:
    """Turn text lines into positioned tokens. `overrides` sets confidence per word."""
    overrides = overrides or {}
    tokens: list[OcrToken] = []
    for row, line in enumerate(lines):
        left = 40
        for word in line.split():
            tokens.append(
                OcrToken(
                    text=word,
                    confidence=overrides.get(word, confidence),
                    left=left,
                    top=60 + row * 50,
                    width=12 * len(word),
                    height=30,
                    line_key=f"1-1-{row}",
                )
            )
            left += 12 * len(word) + 14
    return tokens

def sheet_lines(
    code: str,
    *,
    accredited: int = 300,
    registered: int = 800,
    rejected: int = 10,
    parties: dict[str, int] | None = None,
    valid: int | None = None,
    cast: int | None = None,
    election: str = "GOVERNORSHIP",
) -> list[str]:
    parties = parties or {"PA": 120, "PB": 90, "PC": 50, "PD": 20}
    valid = sum(parties.values()) if valid is None else valid
    cast = valid + rejected if cast is None else cast
    return [
        f"ELECTION: {election}",
        f"POLLING UNIT CODE: {code}",
        f"VOTERS ON THE REGISTER {registered}",
        f"ACCREDITED VOTERS {accredited}",
        *[f"{party} {votes}" for party, votes in parties.items()],
        f"TOTAL VALID VOTES {valid}",
        f"REJECTED VOTES {rejected}",
        f"TOTAL VOTES CAST {cast}",
    ]

@dataclass
class FakeOcr:
    """Stands in for Tesseract. Returns whatever tokens the test configures."""

    name: str = "fake-ocr"
    available: bool = True
    tokens: list[OcrToken] = field(default_factory=list)
    fail: bool = False

    def is_available(self) -> bool:
        return self.available

    def detect_rotation(self, image: Any) -> int | None:
        return 0

    def recognize(self, image: Any) -> OcrResult:
        if self.fail:
            raise RuntimeError("simulated engine crash")
        return OcrResult(provider=self.name, provider_version="test-1", tokens=list(self.tokens))

@dataclass
class Actor:
    user_id: str
    roles: list[str]

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(roles=self.roles, subject=self.user_id)}"}

def actor(*roles: str) -> Actor:
    return Actor(user_id=str(uuid.uuid4()), roles=list(roles))

def demo_targets() -> tuple[Any, Any, Any]:
    """(election, polling_unit, second_polling_unit) from the fictional demo directory."""
    directory = DemoDirectoryRepository()
    election = directory.list_elections()[0]
    units = directory.search_polling_units(PollingUnitQuery(), 1, 50).items
    first = directory.get_polling_unit(units[0].id)
    second = directory.get_polling_unit(units[1].id)
    return election, first, second
