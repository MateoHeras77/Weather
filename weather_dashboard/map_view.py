from __future__ import annotations

import html

import folium
from folium.plugins import MarkerCluster

from .geo import corridor_points
from .models import Corridor, Hub, OperationalRisk, RouteResult, Severity


SEVERITY_COLORS = {
    Severity.CRITICAL: "#b42318",
    Severity.HIGH: "#ee3124",
    Severity.MODERATE: "#f79009",
    Severity.LOW: "#667085",
}


def build_map(
    risks: tuple[OperationalRisk, ...],
    hubs: tuple[Hub, ...],
    corridors: tuple[Corridor, ...],
    selected_risk_id: str | None,
    route: RouteResult | None,
    tomtom_api_key: str | None,
) -> folium.Map:
    selected = next((risk for risk in risks if risk.id == selected_risk_id), None)
    location = (
        [selected.latitude, selected.longitude]
        if selected
        else [56.1304, -106.3468]
    )
    zoom = 7 if selected else 4
    dashboard_map = folium.Map(
        location=location,
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
        prefer_canvas=True,
    )

    folium.WmsTileLayer(
        url="https://geo.weather.gc.ca/geomet",
        layers="ALERTS",
        format="image/png",
        transparent=True,
        name="Weather alert areas",
        overlay=True,
        control=True,
        show=False,
    ).add_to(dashboard_map)
    for name, layer in (
        ("Weather radar", "RADAR_1KM_RRSKS"),
        ("Satellite", "GOES-16"),
        ("24h precipitation", "RDPA.24F_PR"),
    ):
        folium.WmsTileLayer(
            url="https://geo.weather.gc.ca/geomet",
            layers=layer,
            format="image/png",
            transparent=True,
            name=name,
            overlay=True,
            control=True,
            show=False,
        ).add_to(dashboard_map)

    if tomtom_api_key:
        folium.TileLayer(
            tiles=(
                "https://api.tomtom.com/traffic/map/4/tile/flow/relative0/"
                f"{{z}}/{{x}}/{{y}}.png?key={tomtom_api_key}"
            ),
            attr="TomTom Traffic",
            name="Traffic flow",
            overlay=True,
            control=True,
            show=False,
        ).add_to(dashboard_map)

    hubs_by_id = {hub.id: hub for hub in hubs}
    corridor_group = folium.FeatureGroup(name="Priority corridors", show=True)
    for corridor in corridors:
        points = corridor_points(corridor, hubs_by_id)
        folium.PolyLine(
            points,
            color="#1c3f94",
            weight=2 + corridor.priority / 2,
            opacity=0.5,
            tooltip=corridor.name,
        ).add_to(corridor_group)
    corridor_group.add_to(dashboard_map)

    hub_group = folium.FeatureGroup(name="Network hubs", show=True)
    for hub in hubs:
        folium.CircleMarker(
            location=[hub.latitude, hub.longitude],
            radius=5 + hub.priority / 2,
            color="#1c3f94",
            weight=2,
            fill=True,
            fill_color="#ffffff",
            fill_opacity=1,
            tooltip=f"{hub.name} ({hub.province})",
        ).add_to(hub_group)
    hub_group.add_to(dashboard_map)

    risk_group = MarkerCluster(
        name="Operational risks",
        options={
            "showCoverageOnHover": False,
            "maxClusterRadius": 45,
            "disableClusteringAtZoom": 7,
        },
    )
    for risk in risks:
        color = SEVERITY_COLORS[risk.severity]
        selected_weight = 5 if risk.id == selected_risk_id else 2
        safe_title = html.escape(risk.title)
        safe_summary = html.escape(risk.summary[:280])
        folium.CircleMarker(
            location=[risk.latitude, risk.longitude],
            radius=10 if risk.severity >= Severity.HIGH else 7,
            color="#ffffff",
            weight=selected_weight,
            fill=True,
            fill_color=color,
            fill_opacity=0.95,
            tooltip=(
                f"{risk.severity.label}: {safe_title}<br>"
                f"{len(risk.affected_hub_ids)} hubs · "
                f"{len(risk.affected_corridor_ids)} corridors"
            ),
            popup=folium.Popup(
                f"<strong>{safe_title}</strong><br>{safe_summary}",
                max_width=360,
            ),
        ).add_to(risk_group)
    risk_group.add_to(dashboard_map)

    if route and route.points:
        folium.PolyLine(
            route.points,
            color="#ee3124",
            weight=6,
            opacity=0.9,
            tooltip="Truck route",
        ).add_to(dashboard_map)

    folium.LayerControl(collapsed=True).add_to(dashboard_map)
    return dashboard_map
