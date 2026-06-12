from __future__ import annotations

from datetime import UTC, datetime

from .config import AppSettings
from .geo import distance_to_corridor_km, haversine_km
from .models import (
    Corridor,
    Hub,
    OperationalRisk,
    Severity,
    TrafficIncident,
    WeatherStation,
)


CRITICAL_WEATHER_WORDS = (
    "tornado",
    "blizzard",
    "freezing rain",
    "snow squall",
    "extreme cold",
    "hurricane",
)


def _deduplicate_traffic_risks(
    risks: list[OperationalRisk],
) -> tuple[OperationalRisk, ...]:
    unique: dict[tuple, OperationalRisk] = {}
    for risk in sorted(risks, key=lambda item: (-item.score, item.title)):
        if risk.kind != "traffic":
            unique[("risk", risk.id)] = risk
            continue
        incident: TrafficIncident = risk.details["incident"]
        key = (
            "traffic",
            incident.description.strip().lower(),
            tuple(sorted(road.upper() for road in incident.road_numbers)),
            round(risk.latitude, 1),
            round(risk.longitude, 1),
        )
        unique.setdefault(key, risk)
    return tuple(sorted(unique.values(), key=lambda risk: (-risk.score, risk.title)))


def _severity(score: int, settings: AppSettings) -> Severity:
    for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MODERATE):
        if score >= settings.risk_thresholds[severity]:
            return severity
    return Severity.LOW


def _affected_assets(
    latitude: float,
    longitude: float,
    hubs: tuple[Hub, ...],
    corridors: tuple[Corridor, ...],
    hub_radius_km: float = 150,
    corridor_radius_km: float = 90,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    hubs_by_id = {hub.id: hub for hub in hubs}
    affected_hubs = tuple(
        hub.id
        for hub in hubs
        if haversine_km(latitude, longitude, hub.latitude, hub.longitude)
        <= hub_radius_km
    )
    affected_corridors = tuple(
        corridor.id
        for corridor in corridors
        if distance_to_corridor_km(latitude, longitude, corridor, hubs_by_id)
        <= corridor_radius_km
    )
    return affected_hubs, affected_corridors


def _asset_score(
    hub_ids: tuple[str, ...],
    corridor_ids: tuple[str, ...],
    hubs_by_id: dict[str, Hub],
    corridors_by_id: dict[str, Corridor],
) -> int:
    return min(
        25,
        sum(hubs_by_id[item].priority * 2 for item in hub_ids)
        + sum(corridors_by_id[item].priority * 2 for item in corridor_ids),
    )


def build_operational_risks(
    stations: tuple[WeatherStation, ...],
    incidents: tuple[TrafficIncident, ...],
    hubs: tuple[Hub, ...],
    corridors: tuple[Corridor, ...],
    settings: AppSettings,
) -> tuple[OperationalRisk, ...]:
    risks: list[OperationalRisk] = []
    hubs_by_id = {hub.id: hub for hub in hubs}
    corridors_by_id = {corridor.id: corridor for corridor in corridors}

    for station in stations:
        affected_hubs, affected_corridors = _affected_assets(
            station.latitude, station.longitude, hubs, corridors
        )
        asset_score = _asset_score(
            affected_hubs, affected_corridors, hubs_by_id, corridors_by_id
        )
        for alert in station.alerts:
            text = f"{alert.alert_type} {alert.description}".lower()
            score = 60 + asset_score
            if any(word in text for word in CRITICAL_WEATHER_WORDS):
                score += 20
            risks.append(
                OperationalRisk(
                    id=alert.id,
                    kind="weather",
                    title=f"{alert.alert_type}: {station.city}",
                    summary=alert.description,
                    latitude=station.latitude,
                    longitude=station.longitude,
                    severity=_severity(score, settings),
                    score=score,
                    affected_hub_ids=affected_hubs,
                    affected_corridor_ids=affected_corridors,
                    source_id=station.city,
                    source="Environment Canada",
                    details={"station": station},
                )
            )

        gust = station.wind_gust_kmh or 0
        if gust >= 70 and not station.alerts:
            score = 52 + asset_score + min(int((gust - 70) / 5), 15)
            risks.append(
                OperationalRisk(
                    id=f"wind:{station.city}",
                    kind="weather",
                    title=f"High wind: {station.city}",
                    summary=f"Wind gusts of {gust:.0f} km/h may affect high-profile vehicles.",
                    latitude=station.latitude,
                    longitude=station.longitude,
                    severity=_severity(score, settings),
                    score=score,
                    affected_hub_ids=affected_hubs,
                    affected_corridor_ids=affected_corridors,
                    source_id=station.city,
                    source="Environment Canada",
                    details={"station": station},
                )
            )

    now = datetime.now(UTC)
    for incident in incidents:
        affected_hubs, affected_corridors = _affected_assets(
            incident.latitude,
            incident.longitude,
            hubs,
            corridors,
            hub_radius_km=45,
            corridor_radius_km=30,
        )
        if not affected_hubs and not affected_corridors:
            continue
        incident_roads = {road.strip().upper() for road in incident.road_numbers}
        monitored_roads = {
            road.strip().upper()
            for corridor_id in affected_corridors
            for road in corridors_by_id[corridor_id].road_numbers
        }
        on_priority_road = bool(incident_roads & monitored_roads)
        close_to_hub = any(
            haversine_km(
                incident.latitude,
                incident.longitude,
                hubs_by_id[hub_id].latitude,
                hubs_by_id[hub_id].longitude,
            )
            <= 12
            for hub_id in affected_hubs
        )
        material_closure = incident.is_closed and (
            on_priority_road
            or incident.length_m >= 5000
            or (close_to_hub and incident.length_m >= 1000)
        )
        material_delay = (incident.delay_seconds or 0) >= 900 or (
            incident.magnitude >= 3 and (incident.delay_seconds or 0) >= 300
        )
        if not material_closure and not material_delay:
            continue
        if incident.time_validity == "future" and not (
            material_closure and on_priority_road
        ):
            continue
        score = 35 + incident.magnitude * 10
        if incident.is_closed:
            score += 35
        elif (incident.delay_seconds or 0) >= 900:
            score += 20
        if incident.time_validity == "future":
            score -= 8
        score += _asset_score(
            affected_hubs, affected_corridors, hubs_by_id, corridors_by_id
        )
        delay = (
            f"{round(incident.delay_seconds / 60)} minute delay"
            if incident.delay_seconds
            else "indefinite impact"
        )
        started = None
        if incident.start_time:
            started = max(0, int((now - incident.start_time).total_seconds() / 60))
        generic_closure = incident.description.strip().lower() in {
            "closed",
            "closure",
            "road closed",
        }
        closure_location = (
            incident.road_numbers[0]
            if incident.road_numbers
            else incident.from_name
        )
        title = incident.description
        if incident.is_closed:
            title = (
                f"Road closed: {closure_location}"
                if generic_closure
                else f"Road closed: {incident.description}"
            )
        risks.append(
            OperationalRisk(
                id=f"traffic:{incident.id}",
                kind="traffic",
                title=title,
                summary=f"{incident.from_name} to {incident.to_name}; {delay}.",
                latitude=incident.latitude,
                longitude=incident.longitude,
                severity=_severity(score, settings),
                score=score,
                affected_hub_ids=affected_hubs,
                affected_corridor_ids=affected_corridors,
                source_id=incident.id,
                source="TomTom",
                details={"incident": incident, "started_minutes_ago": started},
            )
        )
    return _deduplicate_traffic_risks(risks)
