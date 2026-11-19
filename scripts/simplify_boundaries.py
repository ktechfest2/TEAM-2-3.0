"""Reduce the geoBoundaries Nigeria ADM1 file to a size suitable for the browser.

Source: geoBoundaries gbOpen NGA ADM1 (commit 9469f09), derived from GRID3 Nigeria state
boundaries, licensed CC BY 4.0. Download the simplified GeoJSON from
https://www.geoboundaries.org/api/current/gbOpen/NGA/ADM1/ and run:

    python3 scripts/simplify_boundaries.py input.geojson frontend/public/geo/nigeria-states.geojson

Only geometry precision changes (Ramer-Douglas-Peucker plus coordinate rounding). Boundary
lines are not edited, and no state is added or removed."""

import json
import sys

TOLERANCE = 0.008  # degrees, roughly 900 m
DECIMALS = 3

def _perpendicular(point, start, end):
    (x, y), (x1, y1), (x2, y2) = point, start, end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / (dx * dx + dy * dy) ** 0.5

def _rdp(points, tolerance):
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        index, distance = 0, 0.0
        for i in range(first + 1, last):
            d = _perpendicular(points[i], points[first], points[last])
            if d > distance:
                index, distance = i, d
        if distance > tolerance:
            keep[index] = True
            stack.extend([(first, index), (index, last)])
    return [p for p, k in zip(points, keep, strict=True) if k]

def _ring(ring):
    simplified = _rdp(ring, TOLERANCE)
    if len(simplified) < 4:
        simplified = ring
    rounded = [[round(x, DECIMALS), round(y, DECIMALS)] for x, y in simplified]
    return [p for i, p in enumerate(rounded) if i == 0 or p != rounded[i - 1]]

def _geometry(geometry):
    if geometry["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [_ring(r) for r in geometry["coordinates"]]}
    if geometry["type"] == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "coordinates": [[_ring(r) for r in poly] for poly in geometry["coordinates"]],
        }
    raise ValueError(f"Unsupported geometry {geometry['type']}")

def main(source: str, target: str) -> None:
    with open(source, encoding="utf-8") as handle:
        data = json.load(handle)
    features = [
        {
            "type": "Feature",
            "properties": {
                "iso_code": f["properties"]["shapeISO"],
                "name": f["properties"]["shapeName"],
            },
            "geometry": _geometry(f["geometry"]),
        }
        for f in data["features"]
    ]
    output = {
        "type": "FeatureCollection",
        "attribution": (
            "State boundaries: geoBoundaries (gbOpen NGA ADM1, source GRID3), CC BY 4.0. "
            "Simplified for display; not for legal or survey use."
        ),
        "features": sorted(features, key=lambda f: f["properties"]["iso_code"]),
    }
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(output, handle, separators=(",", ":"))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
