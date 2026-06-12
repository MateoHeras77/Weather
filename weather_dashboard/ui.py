from __future__ import annotations

import html
from datetime import UTC, datetime

import pandas as pd
import streamlit as st

from .models import (
    Corridor,
    DataFreshness,
    Hub,
    OperationalRisk,
    Severity,
    TrafficIncident,
    WeatherStation,
)


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #102a43;
            --blue: #173f8f;
            --red: #ee3124;
            --paper: #ffffff;
            --mist: #f3f6fa;
            --line: #d9e2ec;
        }
        header[data-testid="stHeader"] {background: #173f8f;}
        header[data-testid="stHeader"] * {color: white !important;}
        [data-testid="stSidebar"] {display: none;}
        .stApp {background:
            linear-gradient(180deg, #edf3fa 0, #ffffff 230px);
            color: var(--ink);
        }
        .main .block-container {max-width: 1540px; padding-top: 1rem;}
        h1, h2, h3 {color: var(--blue) !important; letter-spacing: -0.025em;}
        .command-header {
            padding: 18px 22px; border-radius: 12px;
            background: linear-gradient(112deg, #112f6b, #1c4ba1);
            color: white; box-shadow: 0 12px 32px rgba(17,47,107,.18);
        }
        .command-kicker {font-size: .72rem; letter-spacing: .15em; opacity: .72;}
        .command-title {font-size: 1.85rem; font-weight: 760; margin-top: 4px;}
        .command-subtitle {opacity: .82; margin-top: 3px;}
        .source-strip {
            font-size: .78rem; color: #52616f; padding: 6px 2px 12px;
        }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,.94); border: 1px solid var(--line);
            border-radius: 10px; padding: 13px 15px;
            box-shadow: 0 5px 18px rgba(16,42,67,.06);
        }
        div[data-testid="stMetricLabel"] {font-size: .78rem;}
        div[data-testid="stMetricValue"] {color: var(--ink);}
        .risk-card {
            border: 1px solid var(--line); border-left: 5px solid var(--risk-color);
            border-radius: 8px; padding: 10px 12px; background: white;
            margin-bottom: 8px;
        }
        .risk-level {font-size: .68rem; font-weight: 800; letter-spacing: .1em;}
        .risk-title {font-weight: 730; color: var(--ink); margin: 3px 0;}
        .risk-meta {font-size: .76rem; color: #66788a;}
        .detail-hero {
            border-left: 6px solid var(--risk-color); background: #fff;
            border-radius: 10px; padding: 14px 16px; border-top: 1px solid var(--line);
            border-right: 1px solid var(--line); border-bottom: 1px solid var(--line);
        }
        .asset-chip {
            display: inline-block; background: #eaf0fa; color: #173f8f;
            border-radius: 999px; padding: 4px 8px; margin: 2px;
            font-size: .75rem; font-weight: 650;
        }
        .stButton > button {
            border-radius: 7px; border: 1px solid #cbd6e2;
            font-weight: 650;
        }
        .stButton > button[kind="primary"] {
            background: var(--red); border-color: var(--red);
        }
        div[data-testid="stForm"] {border: 0; padding: 0;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def freshness_label(freshness: DataFreshness, stale_after_minutes: int) -> str:
    if not freshness.successful_at:
        return f"{freshness.source}: unavailable"
    age_minutes = int(
        (datetime.now(UTC) - freshness.successful_at).total_seconds() / 60
    )
    state = "stale" if age_minutes > stale_after_minutes else "current"
    return (
        f"{freshness.source}: {state}, updated "
        f"{freshness.successful_at.astimezone().strftime('%H:%M')}"
    )


def severity_color(severity: Severity) -> str:
    return {
        Severity.CRITICAL: "#b42318",
        Severity.HIGH: "#ee3124",
        Severity.MODERATE: "#f79009",
        Severity.LOW: "#667085",
    }[severity]


def render_risk_card(risk: OperationalRisk) -> None:
    safe_title = html.escape(risk.title)
    st.markdown(
        f"""
        <div class="risk-card" style="--risk-color:{severity_color(risk.severity)}">
          <div class="risk-level">{risk.severity.label.upper()} · {risk.kind.upper()}</div>
          <div class="risk-title">{safe_title}</div>
          <div class="risk-meta">{len(risk.affected_hub_ids)} hubs ·
          {len(risk.affected_corridor_ids)} corridors · score {risk.score}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_detail(
    risk: OperationalRisk,
    hubs_by_id: dict[str, Hub],
    corridors_by_id: dict[str, Corridor],
) -> None:
    safe_title = html.escape(risk.title)
    safe_summary = html.escape(risk.summary)
    st.markdown(
        f"""
        <div class="detail-hero" style="--risk-color:{severity_color(risk.severity)}">
          <div class="risk-level">{risk.severity.label.upper()} · {risk.source}</div>
          <div class="risk-title" style="font-size:1.08rem">{safe_title}</div>
          <div style="font-size:.84rem;color:#52616f">{safe_summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Affected network")
    chips = [
        hubs_by_id[item].name
        for item in risk.affected_hub_ids
        if item in hubs_by_id
    ] + [
        corridors_by_id[item].name
        for item in risk.affected_corridor_ids
        if item in corridors_by_id
    ]
    st.markdown(
        "".join(
            f'<span class="asset-chip">{html.escape(chip)}</span>' for chip in chips
        )
        or "No configured network assets nearby.",
        unsafe_allow_html=True,
    )

    if risk.kind == "weather":
        station: WeatherStation = risk.details["station"]
        cols = st.columns(3)
        cols[0].metric(
            "Temperature",
            f"{station.temperature_c:.0f} °C"
            if station.temperature_c is not None
            else "N/A",
        )
        cols[1].metric(
            "Wind gust",
            f"{station.wind_gust_kmh:.0f} km/h"
            if station.wind_gust_kmh is not None
            else "N/A",
        )
        cols[2].metric(
            "Visibility",
            f"{station.visibility_km:.1f} km"
            if station.visibility_km is not None
            else "N/A",
        )
        with st.expander("Forecast detail"):
            if station.hourly:
                chart = pd.DataFrame(
                    {
                        "Period": [item.period for item in station.hourly[:18]],
                        "Temperature (°C)": [
                            item.temperature_c for item in station.hourly[:18]
                        ],
                    }
                )
                st.line_chart(chart.set_index("Period"))
            if station.daily:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Period": item.period,
                                "Forecast": item.summary,
                                "Temperature (°C)": item.temperature_c,
                                "Precipitation": item.precipitation,
                            }
                            for item in station.daily
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )
    else:
        incident: TrafficIncident = risk.details["incident"]
        cols = st.columns(3)
        cols[0].metric("Status", "CLOSED" if incident.is_closed else "ACTIVE")
        cols[1].metric(
            "Delay",
            f"{round(incident.delay_seconds / 60)} min"
            if incident.delay_seconds
            else "Indefinite",
        )
        cols[2].metric("Confidence", incident.probability.replace("_", " ").title())
        st.caption(
            f"{incident.from_name} → {incident.to_name} · "
            f"{incident.length_m / 1000:.1f} km · "
            f"{incident.time_validity.title()}"
        )
        st.link_button(
            "Open incident in Google Maps",
            (
                "https://www.google.com/maps/search/?api=1&query="
                f"{incident.latitude},{incident.longitude}"
            ),
            width="stretch",
        )
