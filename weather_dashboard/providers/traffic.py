from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import requests

from ..models import DataFreshness, TrafficIncident


TRAFFIC_FIELDS = (
    "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,"
    "magnitudeOfDelay,events{description,code,iconCategory},startTime,endTime,"
    "from,to,length,delay,roadNumbers,timeValidity,probabilityOfOccurrence,"
    "numberOfReports,lastReportTime}}}"
)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _first_coordinate(geometry: dict) -> tuple[float, float] | None:
    coordinates = geometry.get("coordinates") or []
    if not coordinates:
        return None
    point = coordinates[0] if isinstance(coordinates[0], list) else coordinates
    if len(point) < 2:
        return None
    return float(point[1]), float(point[0])


def parse_traffic_payload(payload: dict) -> tuple[TrafficIncident, ...]:
    parsed: list[TrafficIncident] = []
    for incident in payload.get("incidents", []):
        properties = incident.get("properties") or {}
        coordinate = _first_coordinate(incident.get("geometry") or {})
        incident_id = properties.get("id")
        if coordinate is None or not incident_id:
            continue
        events = properties.get("events") or []
        description = events[0].get("description") if events else "Traffic incident"
        latitude, longitude = coordinate
        parsed.append(
            TrafficIncident(
                id=str(incident_id),
                latitude=latitude,
                longitude=longitude,
                category=int(properties.get("iconCategory", 0)),
                description=description or "Traffic incident",
                magnitude=int(properties.get("magnitudeOfDelay", 0)),
                start_time=_parse_datetime(properties.get("startTime")),
                end_time=_parse_datetime(properties.get("endTime")),
                from_name=properties.get("from") or "Unknown",
                to_name=properties.get("to") or "Unknown",
                length_m=float(properties.get("length") or 0),
                delay_seconds=(
                    int(properties["delay"])
                    if properties.get("delay") is not None
                    else None
                ),
                road_numbers=tuple(properties.get("roadNumbers") or []),
                time_validity=properties.get("timeValidity") or "present",
                probability=properties.get("probabilityOfOccurrence") or "certain",
                number_of_reports=properties.get("numberOfReports"),
                last_report_time=_parse_datetime(properties.get("lastReportTime")),
            )
        )
    return tuple(parsed)


def fetch_incidents(
    url: str,
    bounding_boxes: tuple[str, ...],
    api_key: str,
    timeout_seconds: int,
    user_agent: str,
    session: requests.Session | None = None,
) -> tuple[tuple[TrafficIncident, ...], DataFreshness]:
    attempted_at = datetime.now(UTC)
    incidents: dict[str, TrafficIncident] = {}
    errors: list[str] = []

    def fetch_box(bbox: str) -> tuple[tuple[TrafficIncident, ...], str | None]:
        try:
            getter = session.get if session else requests.get
            response = getter(
                url,
                params={
                    "key": api_key,
                    "bbox": bbox,
                    "fields": TRAFFIC_FIELDS,
                    "language": "en-GB",
                    "categoryFilter": "1,3,5,6,7,8,9,10,11,14",
                    "timeValidityFilter": "present,future",
                },
                headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return parse_traffic_payload(response.json()), None
        except (requests.RequestException, ValueError, TypeError) as exc:
            return (), str(exc)

    if session:
        results = [fetch_box(bbox) for bbox in bounding_boxes]
    else:
        with ThreadPoolExecutor(
            max_workers=min(6, max(1, len(bounding_boxes))),
            thread_name_prefix="tomtom-traffic",
        ) as executor:
            results = list(executor.map(fetch_box, bounding_boxes))

    for box_incidents, error in results:
        for incident in box_incidents:
            incidents[incident.id] = incident
        if error:
            errors.append(error)
    successful_at = datetime.now(UTC) if incidents or not errors else None
    return tuple(incidents.values()), DataFreshness(
        source="TomTom Traffic",
        attempted_at=attempted_at,
        successful_at=successful_at,
        error="; ".join(errors[:2]) if errors else None,
    )
