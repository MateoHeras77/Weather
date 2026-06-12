from __future__ import annotations

from .geo import bounding_box, haversine_km
from .models import (
    RouteAnalysis,
    RouteRequest,
    RouteResult,
    Severity,
    TrafficIncident,
    WeatherStation,
)


def route_sample_points(
    points: tuple[tuple[float, float], ...],
    target_count: int = 9,
) -> tuple[tuple[float, float], ...]:
    if not points:
        return ()
    if len(points) <= target_count:
        return points
    indices = {
        round(index * (len(points) - 1) / (target_count - 1))
        for index in range(target_count)
    }
    return tuple(points[index] for index in sorted(indices))


def route_weather_stations(
    route: RouteResult,
    stations: tuple[WeatherStation, ...],
    max_distance_km: float = 75,
) -> tuple[WeatherStation, ...]:
    selected: list[WeatherStation] = []
    seen_cities: set[str] = set()
    for latitude, longitude in route_sample_points(route.points):
        if not stations:
            break
        station = min(
            stations,
            key=lambda item: haversine_km(
                latitude,
                longitude,
                item.latitude,
                item.longitude,
            ),
        )
        distance = haversine_km(
            latitude,
            longitude,
            station.latitude,
            station.longitude,
        )
        if distance <= max_distance_km and station.city not in seen_cities:
            selected.append(station)
            seen_cities.add(station.city)
    return tuple(selected)


def route_scan_boxes(
    points: tuple[tuple[float, float], ...],
    radius_km: float = 25,
) -> tuple[str, ...]:
    samples = route_sample_points(points, target_count=18)
    return tuple(
        dict.fromkeys(
            bounding_box(round(latitude, 2), round(longitude, 2), radius_km)
            for latitude, longitude in samples
        )
    )


def incidents_near_route(
    incidents: tuple[TrafficIncident, ...],
    route: RouteResult,
    max_distance_km: float = 15,
) -> tuple[TrafficIncident, ...]:
    samples = route_sample_points(route.points, target_count=80)
    selected: dict[str, TrafficIncident] = {}
    for incident in incidents:
        material = (
            incident.is_closed
            or (incident.delay_seconds or 0) >= 300
            or incident.magnitude >= 3
        )
        if not material:
            continue
        if any(
            haversine_km(
                incident.latitude,
                incident.longitude,
                latitude,
                longitude,
            )
            <= max_distance_km
            for latitude, longitude in samples
        ):
            selected[incident.id] = incident
    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (
                not item.is_closed,
                -(item.delay_seconds or 0),
                -item.magnitude,
            ),
        )
    )


def route_severity(
    stations: tuple[WeatherStation, ...],
    incidents: tuple[TrafficIncident, ...],
) -> Severity:
    if any(incident.is_closed for incident in incidents):
        return Severity.CRITICAL
    if any(station.alerts or (station.wind_gust_kmh or 0) >= 70 for station in stations):
        return Severity.HIGH
    if any((incident.delay_seconds or 0) >= 900 for incident in incidents):
        return Severity.HIGH
    if incidents or any((station.wind_gust_kmh or 0) >= 50 for station in stations):
        return Severity.MODERATE
    return Severity.LOW


def build_route_analysis(
    request: RouteRequest,
    route: RouteResult,
    stations: tuple[WeatherStation, ...],
    incidents: tuple[TrafficIncident, ...],
    errors: tuple[str, ...] = (),
) -> RouteAnalysis:
    weather = route_weather_stations(route, stations)
    nearby_incidents = incidents_near_route(incidents, route)
    return RouteAnalysis(
        request=request,
        route=route,
        weather_stations=weather,
        incidents=nearby_incidents,
        severity=route_severity(weather, nearby_incidents),
        errors=errors,
    )
