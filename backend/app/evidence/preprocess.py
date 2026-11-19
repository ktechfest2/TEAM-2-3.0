"""OpenCV preprocessing. Works on a decoded copy; the original bytes are untouched.
The output is a processed derivative stored separately with its own hash."""

import io
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.evidence.hashing import difference_hash
from app.evidence.ocr import OcrProvider

MAX_WORKING_SIDE = 3000


@dataclass(frozen=True)
class Preprocessed:
    image: Any  # grayscale numpy array, ready for OCR
    png_bytes: bytes
    width: int
    height: int
    perceptual_hash: str
    steps: list[dict[str, Any]]


def decode_upright(original: bytes) -> tuple[Any, bool]:
    """Decode and apply EXIF orientation. Returns (RGB array, orientation_applied)."""
    with Image.open(io.BytesIO(original)) as source:
        applied = source.getexif().get(0x0112, 1) not in (0, 1)
        upright = ImageOps.exif_transpose(source)
        rgb = np.array(upright.convert("RGB"))
    return rgb, applied


def original_perceptual_hash(original: bytes) -> str:
    rgb, _ = decode_upright(original)
    return difference_hash(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))


def _order_corners(points: Any) -> Any:
    pts = points.reshape(4, 2).astype("float32")
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(sums)], pts[np.argmin(diffs)], pts[np.argmax(sums)], pts[np.argmax(diffs)]],
        dtype="float32",
    )


def find_document(gray: Any) -> tuple[Any | None, float]:
    """Largest four-sided contour covering a meaningful share of the frame."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = float(gray.shape[0] * gray.shape[1])
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        area_ratio = cv2.contourArea(approx) / frame_area
        if len(approx) == 4 and area_ratio >= 0.3:
            return _order_corners(approx), area_ratio
    return None, 0.0


def _warp(gray: Any, corners: Any) -> Any:
    tl, tr, br, bl = corners
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], "float32")
    matrix = cv2.getPerspectiveTransform(corners, target)
    return cv2.warpPerspective(gray, matrix, (width, height))


_ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def preprocess(original: bytes, provider: OcrProvider) -> Preprocessed:
    steps: list[dict[str, Any]] = []
    rgb, exif_applied = decode_upright(original)
    steps.append({"step": "exif_orientation", "applied": exif_applied})
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    perceptual = difference_hash(gray)

    scale = MAX_WORKING_SIDE / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        steps.append({"step": "downscale_working_copy", "applied": True, "scale": f"{scale:.3f}"})

    rotation = provider.detect_rotation(gray) if provider.is_available() else None
    if rotation in _ROTATIONS:
        gray = cv2.rotate(gray, _ROTATIONS[rotation])
    steps.append(
        {
            "step": "text_orientation",
            "applied": rotation in _ROTATIONS,
            "rotation_degrees": rotation,
            "detected": rotation is not None,
        }
    )

    corners, area_ratio = find_document(gray)
    if corners is not None:
        gray = _warp(gray, corners)
    steps.append(
        {
            "step": "document_boundary",
            "applied": corners is not None,
            "area_ratio": f"{area_ratio:.2f}",
        }
    )

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    steps.append({"step": "contrast_enhancement", "applied": True, "method": "CLAHE"})

    gray = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    steps.append({"step": "noise_reduction", "applied": True, "method": "non-local means"})

    ok, encoded = cv2.imencode(".png", gray)
    if not ok:
        raise RuntimeError("could not encode processed image")
    return Preprocessed(
        image=gray,
        png_bytes=encoded.tobytes(),
        width=int(gray.shape[1]),
        height=int(gray.shape[0]),
        perceptual_hash=perceptual,
        steps=steps,
    )
