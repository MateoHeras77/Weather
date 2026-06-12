from __future__ import annotations

import logging
from datetime import UTC, datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium

from weather_dashboard.config import load_network, load_settings
from weather_dashboard.geo import haversine_km, network_scan_boxes
from weather_dashboard.map_view import build_map
from weather_dashboard.models import (
    DataFreshness,
    MapBounds,
    OperationalRisk,
    RouteAnalysis,
    RouteRequest,
    Severity,
)
from weather_dashboard.providers.routing import fetch_route
from weather_dashboard.providers.traffic import fetch_incidents
from weather_dashboard.providers.weather import fetch_weather
from weather_dashboard.risk import build_operational_risks
from weather_dashboard.route_analysis import build_route_analysis, route_scan_boxes
from weather_dashboard.routes import (
    custom_route_endpoints,
    custom_route_request,
    request_for_corridor,
)
from weather_dashboard.time_display import incident_timing_summary, relative_time
from weather_dashboard.ui import (
    apply_styles,
    freshness_label,
    render_detail,
    render_risk_card,
)
from weather_dashboard.viewport import (
    TORONTO_BOUNDS,
    TORONTO_CENTER,
    TORONTO_ZOOM,
    bounds_around,
    bounds_changed,
    bounds_for_points,
    parse_leaflet_bounds,
    risks_in_bounds,
    zoom_for_bounds,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("weather_dashboard")

SETTINGS = load_settings()
HUBS, CORRIDORS, TRUCK_PROFILE = load_network()
HUBS_BY_ID = {hub.id: hub for hub in HUBS}
CORRIDORS_BY_ID = {corridor.id: corridor for corridor in CORRIDORS}
NETWORK_BOXES = network_scan_boxes(HUBS, CORRIDORS)
ALERT_PAGE_SIZE = 5

st.set_page_config(
    page_title="Purolator Network Weather Command Center",
    layout="wide",
    page_icon="P",
    initial_sidebar_state="collapsed",
)
apply_styles()


def secret(name: str) -> str | None:
    try:
        return st.secrets.get(name)
    except Exception:
        return None


@st.cache_data(ttl=SETTINGS.weather_cache_seconds, show_spinner=False)
def cached_weather():
    return fetch_weather(
        SETTINGS.weather_api_url,
        SETTINGS.request_timeout_seconds,
        SETTINGS.user_agent,
    )


@st.cache_data(ttl=SETTINGS.traffic_cache_seconds, show_spinner=False)
def cached_traffic(api_key: str, boxes: tuple[str, ...]):
    return fetch_incidents(
        SETTINGS.tomtom_incident_url,
        boxes,
        api_key,
        SETTINGS.request_timeout_seconds,
        SETTINGS.user_agent,
    )


@st.cache_data(ttl=SETTINGS.route_cache_seconds, show_spinner=False)
def cached_route(route_request: RouteRequest, api_key: str):
    return fetch_route(
        SETTINGS.tomtom_route_url,
        route_request,
        TRUCK_PROFILE,
        api_key,
        SETTINGS.request_timeout_seconds,
        SETTINGS.user_agent,
    )


@st.cache_data(ttl=SETTINGS.traffic_cache_seconds, show_spinner=False)
def cached_route_traffic(
    request_id: str,
    route_points: tuple[tuple[float, float], ...],
    api_key: str,
):
    del request_id
    return fetch_incidents(
        SETTINGS.tomtom_incident_url,
        route_scan_boxes(route_points),
        api_key,
        SETTINGS.request_timeout_seconds,
        SETTINGS.user_agent,
    )


def initialize_state() -> None:
    defaults = {
        "auto_refresh": True,
        "map_center": TORONTO_CENTER,
        "map_zoom": TORONTO_ZOOM,
        "map_bounds": TORONTO_BOUNDS,
        "map_ignore_next_bounds": True,
        "map_programmatic_focus": False,
        "selected_risk_id": None,
        "alert_page": 0,
        "active_route_analysis": None,
        "route_control_signature": None,
        "route_on_map": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def load_resilient_data():
    stations, weather_freshness = cached_weather()
    if stations:
        st.session_state.last_weather = stations
        st.session_state.last_weather_success = weather_freshness.successful_at
    elif st.session_state.get("last_weather"):
        stations = st.session_state.last_weather
        weather_freshness = DataFreshness(
            source=weather_freshness.source,
            attempted_at=weather_freshness.attempted_at,
            successful_at=st.session_state.get("last_weather_success"),
            error=weather_freshness.error,
        )

    api_key = secret("TOMTOM_API_KEY")
    if api_key:
        incidents, traffic_freshness = cached_traffic(api_key, NETWORK_BOXES)
        if traffic_freshness.available:
            st.session_state.last_traffic = incidents
            st.session_state.last_traffic_success = traffic_freshness.successful_at
        elif st.session_state.get("last_traffic") is not None:
            incidents = st.session_state.last_traffic
            traffic_freshness = DataFreshness(
                source=traffic_freshness.source,
                attempted_at=traffic_freshness.attempted_at,
                successful_at=st.session_state.get("last_traffic_success"),
                error=traffic_freshness.error,
            )
    else:
        incidents = ()
        traffic_freshness = DataFreshness(
            source="TomTom Traffic",
            attempted_at=datetime.now(UTC),
            successful_at=None,
            error="TOMTOM_API_KEY is not configured",
        )
    return stations, incidents, weather_freshness, traffic_freshness, api_key


def filter_risks(
    risks: tuple[OperationalRisk, ...],
    severities: list[str],
    risk_types: list[str],
    province: str,
    asset_id: str,
) -> tuple[OperationalRisk, ...]:
    allowed_severity = {item.upper() for item in severities}
    filtered: list[OperationalRisk] = []
    for risk in risks:
        if risk.severity.name not in allowed_severity or risk.kind not in risk_types:
            continue
        if province != "All regions":
            provinces = {
                HUBS_BY_ID[item].province
                for item in risk.affected_hub_ids
                if item in HUBS_BY_ID
            }
            if province not in provinces:
                continue
        if asset_id != "All network assets":
            if (
                asset_id not in risk.affected_hub_ids
                and asset_id not in risk.affected_corridor_ids
            ):
                continue
        filtered.append(risk)
    return tuple(filtered)


def nearest_risk(
    latitude: float,
    longitude: float,
    risks: tuple[OperationalRisk, ...],
) -> OperationalRisk | None:
    if not risks:
        return None
    candidate = min(
        risks,
        key=lambda risk: haversine_km(
            latitude,
            longitude,
            risk.latitude,
            risk.longitude,
        ),
    )
    distance = haversine_km(
        latitude,
        longitude,
        candidate.latitude,
        candidate.longitude,
    )
    return candidate if distance <= 40 else None


def focus_map(
    center: tuple[float, float],
    zoom: int,
    bounds: MapBounds,
) -> None:
    st.session_state.map_center = center
    st.session_state.map_zoom = zoom
    st.session_state.map_bounds = bounds
    st.session_state.map_ignore_next_bounds = True
    st.session_state.map_programmatic_focus = True
    st.session_state.alert_page = 0


def focus_risk(risk: OperationalRisk) -> None:
    st.session_state.selected_risk_id = risk.id
    focus_map(
        (risk.latitude, risk.longitude),
        9,
        bounds_around((risk.latitude, risk.longitude)),
    )


def reset_to_toronto() -> None:
    st.session_state.selected_risk_id = None
    st.session_state.route_on_map = False
    focus_map(TORONTO_CENTER, TORONTO_ZOOM, TORONTO_BOUNDS)


def viewport_metrics(risks: tuple[OperationalRisk, ...]) -> tuple[int, int, int, int, Severity]:
    critical_count = sum(risk.severity == Severity.CRITICAL for risk in risks)
    closure_count = sum(
        risk.kind == "traffic" and risk.details["incident"].is_closed
        for risk in risks
    )
    affected_hubs = {hub_id for risk in risks for hub_id in risk.affected_hub_ids}
    affected_corridors = {
        corridor_id for risk in risks for corridor_id in risk.affected_corridor_ids
    }
    risk_level = max((risk.severity for risk in risks), default=Severity.LOW)
    return (
        critical_count,
        closure_count,
        len(affected_hubs),
        len(affected_corridors),
        risk_level,
    )


def render_alert_list(
    risks: tuple[OperationalRisk, ...],
    selected_risk_id: str | None,
) -> None:
    page_count = max(1, (len(risks) + ALERT_PAGE_SIZE - 1) // ALERT_PAGE_SIZE)
    st.session_state.alert_page = min(st.session_state.alert_page, page_count - 1)
    start = st.session_state.alert_page * ALERT_PAGE_SIZE
    page_risks = risks[start : start + ALERT_PAGE_SIZE]

    if not page_risks:
        st.success("No operational risks are visible in the current map area.")
        return

    for risk in page_risks:
        render_risk_card(risk)
        if st.button(
            "Inspect and locate",
            key=f"inspect-{risk.id}",
            type="primary" if risk.id == selected_risk_id else "secondary",
            width="stretch",
        ):
            focus_risk(risk)
            st.rerun()

    previous_column, page_column, next_column = st.columns([1, 1.2, 1])
    with previous_column:
        if st.button(
            "Previous",
            disabled=st.session_state.alert_page == 0,
            width="stretch",
        ):
            st.session_state.alert_page -= 1
            st.rerun()
    with page_column:
        st.caption(f"Page {st.session_state.alert_page + 1} of {page_count}")
    with next_column:
        if st.button(
            "Next",
            disabled=st.session_state.alert_page >= page_count - 1,
            width="stretch",
        ):
            st.session_state.alert_page += 1
            st.rerun()


def route_request_controls(stations) -> RouteRequest | None:
    mode = st.segmented_control(
        "Route source",
        ["Saved Network Routes", "Custom Route"],
        default="Saved Network Routes",
        width="stretch",
    )
    if mode == "Custom Route":
        endpoints = custom_route_endpoints(HUBS, stations)
        endpoints_by_id = {endpoint.id: endpoint for endpoint in endpoints}
        origin_column, destination_column = st.columns(2)
        with origin_column:
            origin_id = st.selectbox(
                "Origin",
                [endpoint.id for endpoint in endpoints],
                format_func=lambda item: endpoints_by_id[item].name,
                key="custom-route-origin",
            )
        with destination_column:
            destination_options = [
                endpoint.id for endpoint in endpoints if endpoint.id != origin_id
            ]
            destination_id = st.selectbox(
                "Destination",
                destination_options,
                format_func=lambda item: endpoints_by_id[item].name,
                key="custom-route-destination",
            )
        try:
            return custom_route_request(
                endpoints_by_id[origin_id],
                endpoints_by_id[destination_id],
            )
        except (KeyError, ValueError):
            return None

    corridor_id = st.selectbox(
        "Saved route",
        [corridor.id for corridor in CORRIDORS],
        format_func=lambda item: CORRIDORS_BY_ID[item].name,
        key="saved-route",
    )
    return request_for_corridor(CORRIDORS_BY_ID[corridor_id], HUBS_BY_ID)


def analyze_route(
    request: RouteRequest,
    stations,
    api_key: str,
) -> RouteAnalysis | None:
    route = cached_route(request, api_key)
    if route is None:
        return None
    route_incidents, traffic_freshness = cached_route_traffic(
        request.id,
        route.points,
        api_key,
    )
    errors = ()
    if traffic_freshness.error:
        errors = (f"Traffic coverage is partial: {traffic_freshness.error}",)
    return build_route_analysis(
        request,
        route,
        stations,
        route_incidents,
        errors=errors,
    )


def render_route_analysis(analysis: RouteAnalysis) -> None:
    st.markdown(
        f"### {analysis.request.label} · {analysis.severity.label} route risk"
    )
    metrics = st.columns(4)
    metrics[0].metric("Distance", f"{analysis.route.distance_m / 1000:.0f} km")
    metrics[1].metric(
        "Travel time",
        f"{analysis.route.travel_time_seconds / 3600:.1f} h",
    )
    metrics[2].metric(
        "Traffic delay",
        f"{analysis.route.traffic_delay_seconds / 60:.0f} min",
    )
    metrics[3].metric("Route risk", analysis.severity.label)

    if analysis.errors:
        for error in analysis.errors:
            st.warning(error)

    weather_column, incident_column = st.columns(2, gap="large")
    with weather_column:
        st.markdown("#### Weather Waypoints")
        if analysis.weather_stations:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "City": station.city,
                            "Condition": station.condition,
                            "Temperature (°C)": station.temperature_c,
                            "Wind gust (km/h)": station.wind_gust_kmh,
                            "Alert": ", ".join(
                                alert.alert_type for alert in station.alerts
                            )
                            or "None",
                        }
                        for station in analysis.weather_stations
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No weather station was found close enough to this route.")
    with incident_column:
        st.markdown("#### Route Incidents")
        if analysis.incidents:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Status": "CLOSED" if incident.is_closed else "ACTIVE",
                            "Incident": incident.description,
                            "From": incident.from_name,
                            "To": incident.to_name,
                            "Age": incident_timing_summary(incident).split(" · ")[0],
                            "Last update": relative_time(
                                incident.last_report_time
                            ),
                            "Delay (min)": (
                                round(incident.delay_seconds / 60)
                                if incident.delay_seconds
                                else None
                            ),
                        }
                        for incident in analysis.incidents
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.success("No material traffic incidents were found near the route.")


initialize_state()
if st.session_state.auto_refresh:
    st_autorefresh(
        interval=SETTINGS.weather_cache_seconds * 1000,
        limit=None,
        key="command_center_refresh",
    )

header_left, header_actions = st.columns([5, 1.4], vertical_alignment="center")
with header_left:
    st.markdown(
        """
        <div class="command-header">
          <div class="command-kicker">NATIONAL NETWORK OPERATIONS</div>
          <div class="command-title">Weather & Traffic Command Center</div>
          <div class="command-subtitle">
            Toronto-first visibility with live risk scoped to the map
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with header_actions:
    if st.button("Refresh data", type="primary", width="stretch"):
        cached_weather.clear()
        cached_traffic.clear()
        cached_route_traffic.clear()
        st.rerun()
    st.session_state.auto_refresh = st.toggle(
        "Auto-refresh every 5 min",
        value=st.session_state.auto_refresh,
    )

with st.spinner("Updating operating picture..."):
    stations, incidents, weather_freshness, traffic_freshness, api_key = (
        load_resilient_data()
    )

if not stations:
    st.error(
        "Environment Canada weather data is unavailable and no successful "
        "snapshot exists in this session."
    )
    st.caption(weather_freshness.error or "Unknown provider error")
    st.stop()

risks = build_operational_risks(stations, incidents, HUBS, CORRIDORS, SETTINGS)
source_text = " · ".join(
    (
        freshness_label(weather_freshness, SETTINGS.stale_after_minutes),
        freshness_label(traffic_freshness, SETTINGS.stale_after_minutes),
    )
)
st.markdown(f'<div class="source-strip">{source_text}</div>', unsafe_allow_html=True)
if weather_freshness.error:
    st.warning(
        "Weather refresh failed; showing the last successful snapshot. "
        f"{weather_freshness.error}"
    )
if traffic_freshness.error:
    st.info(
        "Traffic coverage is degraded. Weather risk remains available. "
        f"{traffic_freshness.error}"
    )

with st.container(border=True):
    filter_columns = st.columns([1.35, 1.1, 1, 1.7])
    with filter_columns[0]:
        selected_severities = st.multiselect(
            "Severity",
            [item.label for item in reversed(list(Severity))],
            default=[
                Severity.CRITICAL.label,
                Severity.HIGH.label,
                Severity.MODERATE.label,
            ],
        )
    with filter_columns[1]:
        selected_types = st.multiselect(
            "Risk type",
            ["weather", "traffic"],
            default=["weather", "traffic"],
            format_func=str.title,
        )
    with filter_columns[2]:
        selected_province = st.selectbox(
            "Region",
            ["All regions", *sorted({hub.province for hub in HUBS})],
        )
    with filter_columns[3]:
        asset_options = {
            "All network assets": "All network assets",
            **{hub.id: f"Hub · {hub.name}" for hub in HUBS},
            **{
                corridor.id: f"Corridor · {corridor.name}"
                for corridor in CORRIDORS
            },
        }
        selected_asset = st.selectbox(
            "Network asset",
            list(asset_options),
            format_func=lambda item: asset_options[item],
        )

filtered_risks = filter_risks(
    risks,
    selected_severities,
    selected_types,
    selected_province,
    selected_asset,
)
viewport_risks = risks_in_bounds(filtered_risks, st.session_state.map_bounds)
selected_risk = next(
    (
        risk
        for risk in filtered_risks
        if risk.id == st.session_state.selected_risk_id
    ),
    None,
)

critical_count, closure_count, affected_hubs, affected_corridors, view_level = (
    viewport_metrics(viewport_risks)
)
st.caption(
    f"Current map view · {len(viewport_risks)} matching risks · "
    f"center {st.session_state.map_center[0]:.2f}, "
    f"{st.session_state.map_center[1]:.2f}"
)
kpi_columns = st.columns(5)
kpi_columns[0].metric("Critical risks", critical_count)
kpi_columns[1].metric("Road closures", closure_count)
kpi_columns[2].metric("Affected hubs", affected_hubs)
kpi_columns[3].metric("At-risk corridors", affected_corridors)
kpi_columns[4].metric("View risk", view_level.label)

map_title, map_reset = st.columns([5, 1], vertical_alignment="bottom")
with map_title:
    st.markdown("### Current Operating Area")
    st.caption(
        "Pan or zoom to automatically update KPIs and alerts. "
        "Optional weather and traffic layers are available in the map."
    )
with map_reset:
    if st.button("Reset to Toronto", width="stretch"):
        reset_to_toronto()
        st.rerun()

route_overlay = None
active_analysis = st.session_state.active_route_analysis
if st.session_state.route_on_map and active_analysis:
    route_overlay = active_analysis.route

dashboard_map = build_map(
    viewport_risks[:250],
    HUBS,
    CORRIDORS,
    st.session_state.map_center,
    st.session_state.map_zoom,
    st.session_state.map_bounds,
    st.session_state.selected_risk_id,
    route_overlay,
    api_key,
)
map_state = st_folium(
    dashboard_map,
    height=650,
    use_container_width=True,
    returned_objects=["last_object_clicked", "bounds", "zoom"],
    center=st.session_state.map_center,
    zoom=st.session_state.map_zoom,
    key="toronto-viewport-map",
)

clicked = (map_state or {}).get("last_object_clicked")
clicked_risk = None
if clicked:
    clicked_risk = nearest_risk(clicked["lat"], clicked["lng"], viewport_risks)

candidate_bounds = parse_leaflet_bounds((map_state or {}).get("bounds"))
candidate_zoom = (map_state or {}).get("zoom")
viewport_changed = False
if st.session_state.map_ignore_next_bounds:
    st.session_state.map_ignore_next_bounds = False
    st.session_state.map_programmatic_focus = False
elif candidate_bounds:
    if bounds_changed(st.session_state.map_bounds, candidate_bounds):
        st.session_state.map_bounds = candidate_bounds
        st.session_state.map_center = candidate_bounds.center
        st.session_state.alert_page = 0
        viewport_changed = True
    if isinstance(candidate_zoom, int) and candidate_zoom != st.session_state.map_zoom:
        st.session_state.map_zoom = candidate_zoom
        viewport_changed = True

if clicked_risk and clicked_risk.id != st.session_state.selected_risk_id:
    st.session_state.selected_risk_id = clicked_risk.id
    st.rerun()
if viewport_changed:
    st.rerun()

alerts_column, context_column = st.columns([1.15, 1.85], gap="large")
with alerts_column:
    st.markdown("### Priority Alerts")
    st.caption(f"{len(viewport_risks)} risks inside the visible map area")
    render_alert_list(viewport_risks, st.session_state.selected_risk_id)
with context_column:
    st.markdown("### Context")
    if selected_risk:
        if not st.session_state.map_bounds.contains(
            selected_risk.latitude,
            selected_risk.longitude,
        ):
            st.info(
                "This selected risk is outside the current map view. "
                "Its context remains available."
            )
        render_detail(selected_risk, HUBS_BY_ID, CORRIDORS_BY_ID)
    else:
        st.info(
            "Select a marker or a priority alert to inspect weather, traffic, "
            "and affected network assets."
        )

st.divider()
st.markdown("## Corridor Analysis")
st.caption(
    "Analyze a saved planning lane or any available Canadian city pair with "
    f"the configured {TRUCK_PROFILE.name.lower()} profile."
)
route_request = route_request_controls(stations)
if route_request and route_request.id != st.session_state.route_control_signature:
    st.session_state.route_control_signature = route_request.id
    st.session_state.active_route_analysis = None
    st.session_state.route_on_map = False

analyze_column, show_column, status_column = st.columns([1.1, 1.1, 2.8])
with analyze_column:
    analyze_button = st.button(
        "Analyze route",
        type="primary",
        disabled=not bool(api_key) or route_request is None,
        width="stretch",
    )
with show_column:
    analysis_matches = (
        st.session_state.active_route_analysis is not None
        and route_request is not None
        and st.session_state.active_route_analysis.request.id == route_request.id
    )
    show_route = st.button(
        "Show route on map",
        disabled=not analysis_matches,
        width="stretch",
    )
with status_column:
    if not api_key:
        st.info("TomTom API key is required for truck route analysis.")
    elif route_request:
        st.caption(f"Ready to analyze: {route_request.label}")

if analyze_button and route_request and api_key:
    with st.spinner("Calculating truck route, weather corridor, and incidents..."):
        analysis = analyze_route(route_request, stations, api_key)
    if analysis:
        st.session_state.active_route_analysis = analysis
        st.session_state.route_on_map = False
        st.rerun()
    else:
        st.error("TomTom could not calculate this truck route.")

if show_route and st.session_state.active_route_analysis:
    analysis = st.session_state.active_route_analysis
    route_bounds = bounds_for_points(analysis.route.points)
    focus_map(route_bounds.center, zoom_for_bounds(route_bounds), route_bounds)
    st.session_state.route_on_map = True
    st.rerun()

active_analysis = st.session_state.active_route_analysis
if (
    active_analysis
    and route_request
    and active_analysis.request.id == route_request.id
):
    render_route_analysis(active_analysis)

st.divider()
st.caption(
    "Weather: Environment and Climate Change Canada / MSC GeoMet. "
    "Traffic and routing: TomTom. Network locations and added corridors are "
    "planning defaults and must be replaced with approved operational data."
)
