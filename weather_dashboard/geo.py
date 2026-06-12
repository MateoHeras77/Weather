from __future__ import annotations

import math

from .models import Corridor, Hub


EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bounding_box(lat: float, lon: float, radius_km: float) -> str:
    lat_delta = radius_km / 111.0
    lon_scale = max(math.cos(math.radians(lat)), 0.2)
    lon_delta = radius_km / (111.0 * lon_scale)
    return (
        f"{lon - lon_delta:.5f},{lat - lat_delta:.5f},"
        f"{lon + lon_delta:.5f},{lat + lat_delta:.5f}"
    )


def network_scan_boxes(
    hubs: tuple[Hub, ...],
    corridors: tuple[Corridor, ...],
) -> tuple[str, ...]:
    points = [(hub.latitude, hub.longitude, 45.0) for hub in hubs]
    for corridor in corridors:
        points.extend((lat, lon, 35.0) for lat, lon in corridor.scan_points)
    unique = {
        bounding_box(round(lat, 1), round(lon, 1), radius)
        for lat, lon, radius in points
    }
    return tuple(sorted(unique))


def corridor_points(corridor: Corridor, hubs_by_id: dict[str, Hub]) -> tuple[tuple[float, float], ...]:
    origin = hubs_by_id[corridor.origin_hub_id]
    destination = hubs_by_id[corridor.destination_hub_id]
    return (
        (origin.latitude, origin.longitude),
        *corridor.scan_points,
        (destination.latitude, destination.longitude),
    )


def distance_to_corridor_km(
    latitude: float,
    longitude: float,
    corridor: Corridor,
    hubs_by_id: dict[str, Hub],
) -> float:
    return min(
        haversine_km(latitude, longitude, point_lat, point_lon)
        for point_lat, point_lon in corridor_points(corridor, hubs_by_id)
    )

