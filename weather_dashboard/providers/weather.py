from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import requests

from ..models import (
    DailyForecast,
    DataFreshness,
    HourlyForecast,
    WeatherAlert,
    WeatherStation,
)


def _english(value: Any) -> Any:
    return value.get("en") if isinstance(value, dict) else value


def _number(value: Any) -> float | None:
    value = _english(value)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _precipitation(forecast: dict) -> str:
    accumulation = forecast.get("precipitation", {}).get("accumulation", {})
    amount = _english(accumulation.get("amount", {}).get("value"))
    unit = _english(accumulation.get("amount", {}).get("units")) or ""
    name = _english(accumulation.get("name")) or "precipitation"
    if amount is not None:
        return f"{amount} {unit} {name}".strip()
    summary = _english(forecast.get("textSummary")) or ""
    match = re.search(r"(\d+)\s*percent\s*chance", summary, re.IGNORECASE)
    if match:
        return f"{match.group(1)}% chance"
    if any(word in summary.lower() for word in ("rain", "snow", "shower")):
        return "Likely"
    return "None"


def parse_weather_payload(payload: dict) -> tuple[WeatherStation, ...]:
    stations: list[WeatherStation] = []
    for feature_index, feature in enumerate(payload.get("features", [])):
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        if len(coordinates) < 2:
            continue
        longitude, latitude = coordinates[:2]
        city = _english(properties.get("name")) or "Unknown city"
        current = properties.get("currentConditions") or {}

        alerts = tuple(
            WeatherAlert(
                id=f"weather:{feature_index}:{warning_index}",
                city=city,
                latitude=float(latitude),
                longitude=float(longitude),
                alert_type=_english((warning or {}).get("type")) or "Weather alert",
                description=_english((warning or {}).get("description"))
                or "No description available.",
            )
            for warning_index, warning in enumerate(properties.get("warnings") or [])
            if warning
        )

        hourly: list[HourlyForecast] = []
        for forecast in (
            properties.get("hourlyForecastGroup", {}).get("hourlyForecasts") or []
        ):
            date_times = forecast.get("dateTime") or []
            label = "Upcoming"
            if date_times:
                preferred = date_times[1] if len(date_times) > 1 else date_times[0]
                label = preferred.get("textSummary") or label
            hourly.append(
                HourlyForecast(
                    period=label,
                    temperature_c=_number(forecast.get("temperature", {}).get("value")),
                )
            )

        daily: list[DailyForecast] = []
        for forecast in properties.get("forecastGroup", {}).get("forecasts") or []:
            temperatures = forecast.get("temperatures", {}).get("temperature") or []
            temperature = None
            if temperatures:
                temperature = _number(temperatures[0].get("value"))
            daily.append(
                DailyForecast(
                    period=_english(
                        forecast.get("period", {}).get("textForecastName")
                    )
                    or "Upcoming",
                    summary=_english(forecast.get("textSummary")) or "Unavailable",
                    temperature_c=temperature,
                    precipitation=_precipitation(forecast),
                )
            )

        stations.append(
            WeatherStation(
                city=city,
                latitude=float(latitude),
                longitude=float(longitude),
                condition=_english(current.get("condition")) or "Unknown",
                temperature_c=_number(current.get("temperature", {}).get("value")),
                wind_speed_kmh=_number(current.get("wind", {}).get("speed", {}).get("value")),
                wind_direction=_english(
                    current.get("wind", {}).get("direction", {}).get("value")
                ),
                wind_gust_kmh=_number(current.get("wind", {}).get("gust", {}).get("value")),
                visibility_km=_number(current.get("visibility", {}).get("value")),
                humidity_percent=_number(current.get("relativeHumidity", {}).get("value")),
                pressure_kpa=_number(current.get("pressure", {}).get("value")),
                wind_chill_c=_number(current.get("windChill", {}).get("value")),
                alerts=alerts,
                hourly=tuple(hourly),
                daily=tuple(daily),
            )
        )
    return tuple(stations)


def fetch_weather(
    url: str,
    timeout_seconds: int,
    user_agent: str,
    session: requests.Session | None = None,
) -> tuple[tuple[WeatherStation, ...], DataFreshness]:
    attempted_at = datetime.now(UTC)
    client = session or requests.Session()
    try:
        response = client.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": user_agent, "Accept": "application/geo+json"},
        )
        response.raise_for_status()
        stations = parse_weather_payload(response.json())
        if not stations:
            raise ValueError("Weather response contained no usable stations")
        return stations, DataFreshness(
            source="Environment and Climate Change Canada",
            attempted_at=attempted_at,
            successful_at=datetime.now(UTC),
        )
    except (requests.RequestException, ValueError, TypeError) as exc:
        return (), DataFreshness(
            source="Environment and Climate Change Canada",
            attempted_at=attempted_at,
            successful_at=None,
            error=str(exc),
        )

