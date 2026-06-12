from __future__ import annotations

import logging
from datetime import UTC, datetime

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium

from weather_dashboard.config import load_network, load_settings
from weather_dashboard.geo import haversine_km, network_scan_boxes
from weather_dashboard.map_view import build_map
from weather_dashboard.models import DataFreshness, OperationalRisk, Severity
from weather_dashboard.providers.routing import fetch_route
from weather_dashboard.providers.traffic import fetch_incidents
from weather_dashboard.providers.weather import fetch_weather
from weather_dashboard.risk import build_operational_risks
from weather_dashboard.ui import (
    apply_styles,
    freshness_label,
    render_detail,
    render_risk_card,
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
def cached_route(corridor_id: str, api_key: str):
    return fetch_route(
        SETTINGS.tomtom_route_url,
        CORRIDORS_BY_ID[corridor_id],
        HUBS_BY_ID,
        TRUCK_PROFILE,
        api_key,
        SETTINGS.request_timeout_seconds,
        SETTINGS.user_agent,
    )


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
        elif st.session_state.get("last_traffic"):
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
            if asset_id not in risk.affected_hub_ids and asset_id not in risk.affected_corridor_ids:
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
            latitude, longitude, risk.latitude, risk.longitude
        ),
    )
    distance = haversine_km(
        latitude, longitude, candidate.latitude, candidate.longitude
    )
    return candidate if distance <= 40 else None


if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True
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
            Prioritized operational risk across monitored hubs and linehaul corridors
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with header_actions:
    if st.button("Refresh data", type="primary", width="stretch"):
        cached_weather.clear()
        cached_traffic.clear()
        st.rerun()
    st.session_state.auto_refresh = st.toggle(
        "Auto-refresh every 5 min",
        value=st.session_state.auto_refresh,
    )

with st.spinner("Updating national operating picture..."):
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

risks = build_operational_risks(
    stations, incidents, HUBS, CORRIDORS, SETTINGS
)

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

critical_count = sum(risk.severity == Severity.CRITICAL for risk in risks)
closure_count = sum(
    risk.kind == "traffic" and risk.details["incident"].is_closed for risk in risks
)
affected_hubs = {hub_id for risk in risks for hub_id in risk.affected_hub_ids}
affected_corridors = {
    corridor_id for risk in risks for corridor_id in risk.affected_corridor_ids
}
national_level = max((risk.severity for risk in risks), default=Severity.LOW)

kpi_columns = st.columns(5)
kpi_columns[0].metric("Critical risks", critical_count)
kpi_columns[1].metric("Road closures", closure_count)
kpi_columns[2].metric("Affected hubs", len(affected_hubs))
kpi_columns[3].metric("At-risk corridors", len(affected_corridors))
kpi_columns[4].metric("National risk", national_level.label)

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
map_risks = filtered_risks[:250]

selected_risk_id = st.session_state.get("selected_risk_id")
if selected_risk_id not in {risk.id for risk in filtered_risks}:
    selected_risk_id = filtered_risks[0].id if filtered_risks else None
    st.session_state.selected_risk_id = selected_risk_id
selected_risk = next(
    (risk for risk in filtered_risks if risk.id == selected_risk_id),
    None,
)

map_column, rail_column = st.columns([3.25, 1.25], gap="medium")
with map_column:
    st.markdown("### National Operating Picture")
    st.caption(
        "Select a risk marker or use the priority rail. The map displays up to "
        "250 highest-ranked results; layer controls are in the map."
    )
    dashboard_map = build_map(
        map_risks,
        HUBS,
        CORRIDORS,
        selected_risk_id,
        st.session_state.get("active_route"),
        api_key,
    )
    map_state = st_folium(
        dashboard_map,
        width=None,
        height=650,
        returned_objects=["last_object_clicked"],
        key="national-risk-map",
    )
    clicked = (map_state or {}).get("last_object_clicked")
    if clicked:
        clicked_risk = nearest_risk(
            clicked["lat"], clicked["lng"], map_risks
        )
        if clicked_risk and clicked_risk.id != st.session_state.selected_risk_id:
            st.session_state.selected_risk_id = clicked_risk.id
            st.rerun()

with rail_column:
    st.markdown("### Priority Alerts")
    st.caption(f"{len(filtered_risks)} risks match the current filters")
    for risk in filtered_risks[:7]:
        render_risk_card(risk)
        if st.button(
            "Inspect",
            key=f"inspect-{risk.id}",
            type="primary" if risk.id == selected_risk_id else "secondary",
            width="stretch",
        ):
            st.session_state.selected_risk_id = risk.id
            st.rerun()
    if len(filtered_risks) > 7:
        st.caption(f"+ {len(filtered_risks) - 7} additional monitored risks")

    st.markdown("### Context")
    if selected_risk:
        render_detail(selected_risk, HUBS_BY_ID, CORRIDORS_BY_ID)
    else:
        st.success("No operational risks match the current filters.")

if selected_risk:
    st.markdown("## Corridor Analysis")
    st.caption(
        "Analyst detail stays in context. Truck routing uses the configured "
        f"{TRUCK_PROFILE.name.lower()} profile."
    )
    relevant_corridors = [
        CORRIDORS_BY_ID[item]
        for item in selected_risk.affected_corridor_ids
        if item in CORRIDORS_BY_ID
    ]
    if relevant_corridors:
        route_control, route_summary = st.columns([1.3, 2.7])
        with route_control:
            corridor_id = st.selectbox(
                "Affected corridor",
                [corridor.id for corridor in relevant_corridors],
                format_func=lambda item: CORRIDORS_BY_ID[item].name,
            )
            analyze_route = st.button(
                "Analyze truck route",
                type="primary",
                disabled=not bool(api_key),
                width="stretch",
            )
            if not api_key:
                st.caption("TomTom API key required for live truck routing.")
            if analyze_route and api_key:
                with st.spinner("Calculating truck-aware route..."):
                    route = cached_route(corridor_id, api_key)
                if route:
                    st.session_state.active_route = route
                else:
                    st.error("TomTom could not calculate this truck route.")
        with route_summary:
            route = st.session_state.get("active_route")
            if route and route.corridor_id == corridor_id:
                columns = st.columns(3)
                columns[0].metric("Distance", f"{route.distance_m / 1000:.0f} km")
                columns[1].metric(
                    "Travel time", f"{route.travel_time_seconds / 3600:.1f} h"
                )
                columns[2].metric(
                    "Traffic delay", f"{route.traffic_delay_seconds / 60:.0f} min"
                )
                matching = [
                    risk
                    for risk in risks
                    if corridor_id in risk.affected_corridor_ids
                ]
                st.dataframe(
                    [
                        {
                            "Severity": risk.severity.label,
                            "Risk": risk.title,
                            "Type": risk.kind.title(),
                            "Summary": risk.summary,
                        }
                        for risk in matching
                    ],
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.info(
                    "Analyze the selected corridor to overlay its truck route "
                    "and summarize live traffic delay."
                )
    else:
        st.info("This risk does not intersect a configured priority corridor.")

st.divider()
st.caption(
    "Weather: Environment and Climate Change Canada / MSC GeoMet. "
    "Traffic and routing: TomTom. Network locations are planning defaults "
    "and must be replaced with approved operational data."
)
