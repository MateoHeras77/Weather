from __future__ import annotations

from .models import Corridor, Hub, RouteEndpoint, RouteRequest, WeatherStation


def endpoint_for_hub(hub: Hub) -> RouteEndpoint:
    return RouteEndpoint(
        id=f"hub:{hub.id}",
        name=f"{hub.name} ({hub.province})",
        latitude=hub.latitude,
        longitude=hub.longitude,
        source="configured hub",
    )


def request_for_corridor(
    corridor: Corridor,
    hubs_by_id: dict[str, Hub],
) -> RouteRequest:
    return RouteRequest(
        id=f"saved:{corridor.id}",
        label=corridor.name,
        origin=endpoint_for_hub(hubs_by_id[corridor.origin_hub_id]),
        destination=endpoint_for_hub(hubs_by_id[corridor.destination_hub_id]),
        corridor_id=corridor.id,
    )


def custom_route_endpoints(
    hubs: tuple[Hub, ...],
    stations: tuple[WeatherStation, ...],
) -> tuple[RouteEndpoint, ...]:
    endpoints: dict[str, RouteEndpoint] = {}
    configured_cities: set[str] = set()
    for hub in hubs:
        endpoint = endpoint_for_hub(hub)
        endpoints[endpoint.id] = endpoint
        configured_cities.add(hub.city.casefold())
    for station in stations:
        if station.city.casefold() in configured_cities:
            continue
        endpoint = RouteEndpoint(
            id=(
                f"weather:{station.city.casefold()}:"
                f"{station.latitude:.4f}:{station.longitude:.4f}"
            ),
            name=f"{station.city} (weather station)",
            latitude=station.latitude,
            longitude=station.longitude,
            source="Environment Canada city",
        )
        endpoints[endpoint.id] = endpoint
    return tuple(sorted(endpoints.values(), key=lambda item: item.name.casefold()))


def custom_route_request(
    origin: RouteEndpoint,
    destination: RouteEndpoint,
) -> RouteRequest:
    if origin.id == destination.id:
        raise ValueError("Origin and destination must be different")
    return RouteRequest(
        id=f"custom:{origin.id}:{destination.id}",
        label=f"{origin.name} to {destination.name}",
        origin=origin,
        destination=destination,
    )
