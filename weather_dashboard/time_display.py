from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .models import TrafficIncident


TORONTO_TIME = ZoneInfo("America/Toronto")


def _normalized(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _duration_label(total_seconds: float) -> str:
    seconds = max(0, int(abs(total_seconds)))
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    if days:
        return f"{days}d"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return "<1m"


def relative_time(value: datetime | None, now: datetime | None = None) -> str:
    if value is None:
        return "Not provided"
    current = _normalized(now or datetime.now(UTC))
    timestamp = _normalized(value)
    difference = current - timestamp
    duration = _duration_label(difference.total_seconds())
    return f"{duration} ago" if difference.total_seconds() >= 0 else f"in {duration}"


def local_timestamp(value: datetime | None) -> str:
    if value is None:
        return "Not provided"
    return _normalized(value).astimezone(TORONTO_TIME).strftime(
        "%b %-d, %Y · %-I:%M %p %Z"
    )


def incident_timing_summary(
    incident: TrafficIncident,
    now: datetime | None = None,
) -> str:
    current = _normalized(now or datetime.now(UTC))
    parts: list[str] = []
    if incident.start_time:
        start = _normalized(incident.start_time)
        elapsed = current - start
        if elapsed.total_seconds() >= 7 * 24 * 60 * 60:
            parts.append(f"Ongoing {_duration_label(elapsed.total_seconds())}")
        elif elapsed.total_seconds() >= 0:
            parts.append(f"Started {_duration_label(elapsed.total_seconds())} ago")
        else:
            parts.append(f"Starts in {_duration_label(elapsed.total_seconds())}")

    if incident.last_report_time:
        last_report = _normalized(incident.last_report_time)
        if (
            last_report.astimezone(TORONTO_TIME).date()
            == current.astimezone(TORONTO_TIME).date()
        ):
            parts.append("confirmed today")
        else:
            parts.append(f"Updated {relative_time(last_report, current)}")

    return " · ".join(parts) or "Timing not provided"
