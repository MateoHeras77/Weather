from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import Corridor, Hub, Severity, TruckProfile


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


@dataclass(frozen=True)
class AppSettings:
    weather_api_url: str
    tomtom_incident_url: str
    tomtom_route_url: str
    request_timeout_seconds: int
    weather_cache_seconds: int
    traffic_cache_seconds: int
    route_cache_seconds: int
    stale_after_minutes: int
    user_agent: str
    risk_thresholds: dict[Severity, int]


def _read_json(filename: str) -> dict:
    with (CONFIG_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_settings() -> AppSettings:
    data = _read_json("settings.json")
    return AppSettings(
        weather_api_url=data["weather_api_url"],
        tomtom_incident_url=data["tomtom_incident_url"],
        tomtom_route_url=data["tomtom_route_url"],
        request_timeout_seconds=data["request_timeout_seconds"],
        weather_cache_seconds=data["weather_cache_seconds"],
        traffic_cache_seconds=data["traffic_cache_seconds"],
        route_cache_seconds=data["route_cache_seconds"],
        stale_after_minutes=data["stale_after_minutes"],
        user_agent=data["user_agent"],
        risk_thresholds={
            Severity.CRITICAL: data["risk_thresholds"]["critical"],
            Severity.HIGH: data["risk_thresholds"]["high"],
            Severity.MODERATE: data["risk_thresholds"]["moderate"],
            Severity.LOW: 0,
        },
    )


def load_network() -> tuple[tuple[Hub, ...], tuple[Corridor, ...], TruckProfile]:
    data = _read_json("network.json")
    hubs = tuple(Hub(**item) for item in data["hubs"])
    corridors = tuple(
        Corridor(
            id=item["id"],
            name=item["name"],
            origin_hub_id=item["origin_hub_id"],
            destination_hub_id=item["destination_hub_id"],
            priority=item["priority"],
            scan_points=tuple(tuple(point) for point in item.get("scan_points", [])),
            road_numbers=tuple(item.get("road_numbers", [])),
        )
        for item in data["corridors"]
    )
    truck = TruckProfile(**data["truck_profile"])
    return hubs, corridors, truck
