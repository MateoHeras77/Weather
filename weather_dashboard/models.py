from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
import math
from typing import Any


class Severity(IntEnum):
    LOW = 1
    MODERATE = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.title()


@dataclass(frozen=True)
class HourlyForecast:
    period: str
    temperature_c: float | None


@dataclass(frozen=True)
class DailyForecast:
    period: str
    summary: str
    temperature_c: float | None
    precipitation: str


@dataclass(frozen=True)
class WeatherAlert:
    id: str
    city: str
    latitude: float
    longitude: float
    alert_type: str
    description: str


@dataclass(frozen=True)
class WeatherStation:
    city: str
    latitude: float
    longitude: float
    condition: str
    temperature_c: float | None
    wind_speed_kmh: float | None
    wind_direction: str | None
    wind_gust_kmh: float | None
    visibility_km: float | None
    humidity_percent: float | None
    pressure_kpa: float | None
    wind_chill_c: float | None
    alerts: tuple[WeatherAlert, ...] = ()
    hourly: tuple[HourlyForecast, ...] = ()
    daily: tuple[DailyForecast, ...] = ()


@dataclass(frozen=True)
class TrafficIncident:
    id: str
    latitude: float
    longitude: float
    category: int
    description: str
    magnitude: int
    start_time: datetime | None
    end_time: datetime | None
    from_name: str
    to_name: str
    length_m: float
    delay_seconds: int | None
    road_numbers: tuple[str, ...]
    time_validity: str
    probability: str
    number_of_reports: int | None
    last_report_time: datetime | None

    @property
    def is_closed(self) -> bool:
        return self.category == 8


@dataclass(frozen=True)
class Hub:
    id: str
    name: str
    city: str
    province: str
    latitude: float
    longitude: float
    priority: int


@dataclass(frozen=True)
class Corridor:
    id: str
    name: str
    origin_hub_id: str
    destination_hub_id: str
    priority: int
    scan_points: tuple[tuple[float, float], ...] = ()
    road_numbers: tuple[str, ...] = ()


@dataclass(frozen=True)
class TruckProfile:
    name: str
    max_speed_kmh: int
    weight_kg: int
    axle_weight_kg: int
    axles: int
    length_m: float
    width_m: float
    height_m: float


@dataclass(frozen=True)
class DataFreshness:
    source: str
    attempted_at: datetime
    successful_at: datetime | None
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.successful_at is not None


@dataclass(frozen=True)
class MapBounds:
    south: float
    west: float
    north: float
    east: float

    @property
    def center(self) -> tuple[float, float]:
        south_y = math.log(
            math.tan(math.pi / 4 + math.radians(self.south) / 2)
        )
        north_y = math.log(
            math.tan(math.pi / 4 + math.radians(self.north) / 2)
        )
        latitude = math.degrees(
            2 * math.atan(math.exp((south_y + north_y) / 2)) - math.pi / 2
        )
        longitude = (self.west + self.east) / 2
        return latitude, longitude

    def contains(self, latitude: float, longitude: float) -> bool:
        latitude_matches = self.south <= latitude <= self.north
        if self.west <= self.east:
            longitude_matches = self.west <= longitude <= self.east
        else:
            longitude_matches = longitude >= self.west or longitude <= self.east
        return latitude_matches and longitude_matches


@dataclass(frozen=True)
class OperationalRisk:
    id: str
    kind: str
    title: str
    summary: str
    latitude: float
    longitude: float
    severity: Severity
    score: int
    affected_hub_ids: tuple[str, ...]
    affected_corridor_ids: tuple[str, ...]
    source_id: str
    source: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteEndpoint:
    id: str
    name: str
    latitude: float
    longitude: float
    source: str


@dataclass(frozen=True)
class RouteRequest:
    id: str
    label: str
    origin: RouteEndpoint
    destination: RouteEndpoint
    corridor_id: str | None = None


@dataclass(frozen=True)
class RouteResult:
    request_id: str
    points: tuple[tuple[float, float], ...]
    distance_m: int
    travel_time_seconds: int
    traffic_delay_seconds: int


@dataclass(frozen=True)
class RouteAnalysis:
    request: RouteRequest
    route: RouteResult
    weather_stations: tuple[WeatherStation, ...]
    incidents: tuple[TrafficIncident, ...]
    severity: Severity
    errors: tuple[str, ...] = ()
