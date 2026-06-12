from __future__ import annotations

import math
from typing import Any

from .models import MapBounds, OperationalRisk


TORONTO_CENTER = (43.6777, -79.6248)
TORONTO_ZOOM = 8
TORONTO_BOUNDS = MapBounds(
    south=42.6,
    west=-83.2,
    north=45.4,
    east=-76.2,
)


def parse_leaflet_bounds(value: Any) -> MapBounds | None:
    if not isinstance(value, dict):
        return None
    southwest = value.get("_southWest") or {}
    northeast = value.get("_northEast") or {}
    try:
        bounds = MapBounds(
            south=float(southwest["lat"]),
            west=float(southwest["lng"]),
            north=float(northeast["lat"]),
            east=float(northeast["lng"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if bounds.south > bounds.north:
        return None
    return bounds


def bounds_changed(
    current: MapBounds,
    candidate: MapBounds,
    tolerance: float = 0.001,
) -> bool:
    return any(
        abs(left - right) > tolerance
        for left, right in (
            (current.south, candidate.south),
            (current.west, candidate.west),
            (current.north, candidate.north),
            (current.east, candidate.east),
        )
    )


def risks_in_bounds(
    risks: tuple[OperationalRisk, ...],
    bounds: MapBounds,
) -> tuple[OperationalRisk, ...]:
    return tuple(
        risk for risk in risks if bounds.contains(risk.latitude, risk.longitude)
    )


def bounds_around(
    center: tuple[float, float],
    latitude_span: float = 0.8,
    longitude_span: float = 1.2,
) -> MapBounds:
    latitude, longitude = center
    return MapBounds(
        south=latitude - latitude_span / 2,
        west=longitude - longitude_span / 2,
        north=latitude + latitude_span / 2,
        east=longitude + longitude_span / 2,
    )


def bounds_for_points(
    points: tuple[tuple[float, float], ...],
    padding_ratio: float = 0.12,
) -> MapBounds:
    latitudes = [point[0] for point in points]
    longitudes = [point[1] for point in points]
    latitude_span = max(max(latitudes) - min(latitudes), 0.15)
    longitude_span = max(max(longitudes) - min(longitudes), 0.15)
    return MapBounds(
        south=min(latitudes) - latitude_span * padding_ratio,
        west=min(longitudes) - longitude_span * padding_ratio,
        north=max(latitudes) + latitude_span * padding_ratio,
        east=max(longitudes) + longitude_span * padding_ratio,
    )


def zoom_for_bounds(bounds: MapBounds) -> int:
    span = max(bounds.north - bounds.south, bounds.east - bounds.west)
    if span <= 0.4:
        return 10
    if span <= 0.9:
        return 9
    if span <= 1.8:
        return 8
    if span <= 3.5:
        return 7
    if span <= 7:
        return 6
    if span <= 14:
        return 5
    return 4


def centers_are_close(
    left: tuple[float, float],
    right: tuple[float, float],
    tolerance: float = 0.05,
) -> bool:
    return math.isclose(left[0], right[0], abs_tol=tolerance) and math.isclose(
        left[1], right[1], abs_tol=tolerance
    )
