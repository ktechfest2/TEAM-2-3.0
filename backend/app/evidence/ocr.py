"""Replaceable OCR providers.

- Tesseract needs the system binary (apt install tesseract-ocr, brew install tesseract).
- RapidOCR runs PaddleOCR models through ONNX Runtime and installs with pip alone
  (see requirements-ocr.txt), so it works where the binary cannot be installed.
`OCR_PROVIDER=auto` uses Tesseract when present, then RapidOCR, else manual entry."""

import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import metadata
from typing import Any, Protocol

from app.core.config import get_settings


@dataclass(frozen=True)
class OcrToken:
    text: str
    # Normalised to 0..1. Engines report this differently; it is a ranking signal,
    # not a probability that the reading is correct.
    confidence: float
    left: int
    top: int
    width: int
    height: int
    line_key: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
            "line_key": self.line_key,
        }


@dataclass(frozen=True)
class OcrResult:
    provider: str
    provider_version: str | None
    tokens: list[OcrToken] = field(default_factory=list)

    @property
    def text(self) -> str:
        lines: dict[str, list[str]] = {}
        for token in self.tokens:
            lines.setdefault(token.line_key, []).append(token.text)
        return "\n".join(" ".join(words) for words in lines.values())


class OcrUnavailableError(RuntimeError):
    pass


class OcrProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...
    def detect_rotation(self, image: Any) -> int | None:
        """Clockwise degrees (0, 90, 180, 270) needed to make text upright, if known."""
        ...

    def recognize(self, image: Any) -> OcrResult: ...


class TesseractProvider:
    name = "tesseract"

    def __init__(self, languages: str = "eng", page_segmentation: int = 6) -> None:
        self.languages = languages
        self.page_segmentation = page_segmentation

    def _version(self) -> str | None:
        import pytesseract

        try:
            return str(pytesseract.get_tesseract_version())
        except (pytesseract.TesseractNotFoundError, OSError):
            return None

    def is_available(self) -> bool:
        return self._version() is not None

    def detect_rotation(self, image: Any) -> int | None:
        import pytesseract

        try:
            osd = pytesseract.image_to_osd(image)
        except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, OSError):
            return None
        match = re.search(r"Rotate:\s*(\d+)", osd)
        return int(match.group(1)) % 360 if match else None

    def recognize(self, image: Any) -> OcrResult:
        import pytesseract

        version = self._version()
        if version is None:
            raise OcrUnavailableError("Tesseract is not installed on the server")
        data = pytesseract.image_to_data(
            image,
            lang=self.languages,
            config=f"--psm {self.page_segmentation}",
            output_type=pytesseract.Output.DICT,
        )
        tokens = []
        for index, text in enumerate(data["text"]):
            word = str(text).strip()
            confidence = float(data["conf"][index])
            if not word or confidence < 0:
                continue
            tokens.append(
                OcrToken(
                    text=word,
                    confidence=max(0.0, min(confidence / 100.0, 1.0)),
                    left=int(data["left"][index]),
                    top=int(data["top"][index]),
                    width=int(data["width"][index]),
                    height=int(data["height"][index]),
                    line_key=f"{data['block_num'][index]}-{data['par_num'][index]}-"
                    f"{data['line_num'][index]}",
                )
            )
        return OcrResult(provider=self.name, provider_version=version, tokens=tokens)


class RapidOcrProvider:
    """PaddleOCR models through ONNX Runtime. The recogniser returns whole lines with
    per-character boxes; lines are split into words so the field mapper sees the same
    word tokens Tesseract produces. The recogniser's own spaces are used when it emits
    them; character gaps are only a fallback for lines it returned without spaces."""

    name = "rapidocr"
    # Without spaces, a gap wider than this share of the median character width
    # separates two words. Character boxes are coarse, so the margin is generous.
    WORD_GAP = 0.8

    def __init__(self) -> None:
        self._engine: Any = None
        self._lock = threading.Lock()

    def _version(self) -> str | None:
        try:
            return metadata.version("rapidocr_onnxruntime")
        except metadata.PackageNotFoundError:
            return None

    def is_available(self) -> bool:
        return self._version() is not None

    def detect_rotation(self, image: Any) -> int | None:
        # The engine's own angle classifier handles upside-down lines during recognition.
        return None

    def _load(self) -> Any:
        with self._lock:
            if self._engine is None:
                from rapidocr_onnxruntime import RapidOCR

                self._engine = RapidOCR()
            return self._engine

    def recognize(self, image: Any) -> OcrResult:
        import numpy as np

        version = self._version()
        if version is None:
            raise OcrUnavailableError("RapidOCR is not installed on the server")
        array = np.asarray(image)
        if array.ndim == 2:
            array = np.stack([array] * 3, axis=-1)
        lines, _ = self._load()(array, return_word_box=True)
        tokens: list[OcrToken] = []
        for index, line in enumerate(lines or []):
            tokens += self._words(line, f"line-{index}")
        return OcrResult(provider=self.name, provider_version=version, tokens=tokens)

    def _words(self, line: list[Any], line_key: str) -> list[OcrToken]:
        box, text, score = line[0], str(line[1]), float(line[2])
        chars: list[str] = list(line[4]) if len(line) > 4 and line[4] else []
        char_boxes: list[Any] = list(line[3]) if len(line) > 3 and line[3] else []
        confidence = max(0.0, min(score, 1.0))
        if not chars or len(chars) != len(char_boxes):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            return [
                OcrToken(
                    word,
                    confidence,
                    int(min(xs)),
                    int(min(ys)),
                    int(max(xs) - min(xs)),
                    int(max(ys) - min(ys)),
                    line_key,
                )  # fmt: skip
                for word in text.split()
            ]
        spans = [
            (min(p[0] for p in b), min(p[1] for p in b), max(p[0] for p in b), max(p[1] for p in b))
            for b in char_boxes
        ]
        widths = sorted(right - left for left, _, right, _ in spans)
        median = max(widths[len(widths) // 2], 1)
        use_gaps = not any(char.isspace() for char in chars)
        words: list[list[int]] = []
        for i, char in enumerate(chars):
            if char.isspace():
                words.append([])
                continue
            gap = spans[i][0] - spans[i - 1][2] if i else 0
            wide = use_gaps and gap > self.WORD_GAP * median
            # "VOTES:412" reads as one run; a colon always ends the label.
            if not words or not words[-1] or wide or chars[i - 1] == ":":
                words.append([i])
            else:
                words[-1].append(i)
        tokens = []
        for indices in (w for w in words if w):
            left = min(spans[i][0] for i in indices)
            top = min(spans[i][1] for i in indices)
            right = max(spans[i][2] for i in indices)
            bottom = max(spans[i][3] for i in indices)
            tokens.append(
                OcrToken(
                    "".join(chars[i] for i in indices),
                    confidence,
                    int(left),
                    int(top),
                    int(right - left),
                    int(bottom - top),
                    line_key,
                )  # fmt: skip
            )
        return tokens


class NullProvider:
    """Used when OCR is disabled. Every field then requires manual transcription."""

    name = "none"

    def is_available(self) -> bool:
        return False

    def detect_rotation(self, image: Any) -> int | None:
        return None

    def recognize(self, image: Any) -> OcrResult:
        raise OcrUnavailableError("OCR is disabled")


@lru_cache
def _rapidocr() -> RapidOcrProvider:
    return RapidOcrProvider()


def get_ocr_provider() -> OcrProvider:
    choice = get_settings().ocr_provider
    if choice == "tesseract":
        return TesseractProvider()
    if choice == "rapidocr":
        return _rapidocr()
    if choice == "auto":
        tesseract = TesseractProvider()
        if tesseract.is_available():
            return tesseract
        if _rapidocr().is_available():
            return _rapidocr()
    return NullProvider()
