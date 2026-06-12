from __future__ import annotations

import requests

from ..models import RouteRequest, RouteResult, TruckProfile


def fetch_route(
    base_url: str,
    route_request: RouteRequest,
    truck: TruckProfile,
    api_key: str,
    timeout_seconds: int,
    user_agent: str,
    session: requests.Session | None = None,
) -> RouteResult | None:
    origin = route_request.origin
    destination = route_request.destination
    locations = (
        f"{origin.latitude},{origin.longitude}:"
        f"{destination.latitude},{destination.longitude}"
    )
    url = f"{base_url}/{locations}/json"
    params = {
        "key": api_key,
        "traffic": "true",
        "routeType": "fastest",
        "travelMode": "truck",
        "vehicleCommercial": "true",
        "vehicleMaxSpeed": truck.max_speed_kmh,
        "vehicleWeight": truck.weight_kg,
        "vehicleAxleWeight": truck.axle_weight_kg,
        "vehicleNumberOfAxles": truck.axles,
        "vehicleLength": truck.length_m,
        "vehicleWidth": truck.width_m,
        "vehicleHeight": truck.height_m,
    }
    client = session or requests.Session()
    try:
        response = client.get(
            url,
            params=params,
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        routes = response.json().get("routes") or []
        if not routes:
            return None
        route = routes[0]
        points = tuple(
            (float(point["latitude"]), float(point["longitude"]))
            for leg in route.get("legs", [])
            for point in leg.get("points", [])
        )
        summary = route.get("summary") or {}
        return RouteResult(
            request_id=route_request.id,
            points=points,
            distance_m=int(summary.get("lengthInMeters") or 0),
            travel_time_seconds=int(summary.get("travelTimeInSeconds") or 0),
            traffic_delay_seconds=int(summary.get("trafficDelayInSeconds") or 0),
        )
    except (requests.RequestException, ValueError, TypeError, KeyError):
        return None
