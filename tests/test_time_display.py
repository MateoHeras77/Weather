from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from weather_dashboard.models import TrafficIncident
from weather_dashboard.time_display import (
    incident_timing_summary,
    local_timestamp,
    relative_time,
)


class TimeDisplayTests(unittest.TestCase):
    def incident(self, **overrides) -> TrafficIncident:
        values = {
            "id": "incident",
            "latitude": 43.7,
            "longitude": -79.6,
            "category": 8,
            "description": "Road closed",
            "magnitude": 4,
            "start_time": None,
            "end_time": None,
            "from_name": "A",
            "to_name": "B",
            "length_m": 1000,
            "delay_seconds": None,
            "road_numbers": ("401",),
            "time_validity": "present",
            "probability": "certain",
            "number_of_reports": 2,
            "last_report_time": None,
        }
        values.update(overrides)
        return TrafficIncident(**values)

    def test_recent_incident_shows_start_and_confirmation(self):
        now = datetime(2026, 6, 12, 16, 0, tzinfo=UTC)
        incident = self.incident(
            start_time=now - timedelta(hours=2),
            last_report_time=now - timedelta(minutes=12),
        )

        self.assertEqual(
            incident_timing_summary(incident, now),
            "Started 2h ago · confirmed today",
        )
        self.assertEqual(relative_time(incident.last_report_time, now), "12m ago")

    def test_long_running_incident_is_labeled_ongoing(self):
        now = datetime(2026, 6, 12, 16, 0, tzinfo=UTC)
        incident = self.incident(
            start_time=now - timedelta(days=30),
            last_report_time=now - timedelta(hours=1),
        )

        self.assertEqual(
            incident_timing_summary(incident, now),
            "Ongoing 30d · confirmed today",
        )

    def test_future_and_missing_times_are_clear(self):
        now = datetime(2026, 6, 12, 16, 0, tzinfo=UTC)
        future = self.incident(start_time=now + timedelta(hours=3))

        self.assertEqual(incident_timing_summary(future, now), "Starts in 3h")
        self.assertEqual(incident_timing_summary(self.incident(), now), "Timing not provided")
        self.assertEqual(local_timestamp(None), "Not provided")

    def test_exact_timestamp_is_converted_to_toronto_time(self):
        value = datetime(2026, 6, 12, 16, 30, tzinfo=UTC)

        self.assertEqual(local_timestamp(value), "Jun 12, 2026 · 12:30 PM EDT")


if __name__ == "__main__":
    unittest.main()
