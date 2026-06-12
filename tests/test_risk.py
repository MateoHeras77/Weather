from __future__ import annotations

import unittest
from datetime import UTC, datetime

from weather_dashboard.config import load_network, load_settings
from weather_dashboard.geo import haversine_km, network_scan_boxes
from weather_dashboard.models import (
    TrafficIncident,
    WeatherAlert,
    WeatherStation,
)
from weather_dashboard.risk import build_operational_risks


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings()
        self.hubs, self.corridors, _ = load_network()

    def test_haversine_is_zero_for_same_point(self):
        self.assertEqual(haversine_km(43.7, -79.4, 43.7, -79.4), 0)

    def test_network_scan_boxes_are_bounded_and_deduplicated(self):
        boxes = network_scan_boxes(self.hubs, self.corridors)
        self.assertEqual(len(boxes), len(set(boxes)))
        self.assertGreater(len(boxes), len(self.hubs))

    def test_critical_weather_near_priority_assets_ranks_first(self):
        alert = WeatherAlert(
            id="weather:1",
            city="Toronto",
            latitude=43.68,
            longitude=-79.62,
            alert_type="Snow squall warning",
            description="Near-zero visibility is expected.",
        )
        station = WeatherStation(
            city="Toronto",
            latitude=43.68,
            longitude=-79.62,
            condition="Snow",
            temperature_c=-8,
            wind_speed_kmh=40,
            wind_direction="W",
            wind_gust_kmh=75,
            visibility_km=0.5,
            humidity_percent=90,
            pressure_kpa=100,
            wind_chill_c=-15,
            alerts=(alert,),
        )
        traffic = TrafficIncident(
            id="jam",
            latitude=43.7,
            longitude=-79.6,
            category=6,
            description="Traffic jam",
            magnitude=1,
            start_time=datetime.now(UTC),
            end_time=None,
            from_name="A",
            to_name="B",
            length_m=500,
            delay_seconds=120,
            road_numbers=("401",),
            time_validity="present",
            probability="certain",
            number_of_reports=1,
            last_report_time=datetime.now(UTC),
        )

        risks = build_operational_risks(
            (station,),
            (traffic,),
            self.hubs,
            self.corridors,
            self.settings,
        )

        self.assertEqual(risks[0].id, "weather:1")
        self.assertEqual(risks[0].severity.label, "Critical")
        self.assertIn("toronto", risks[0].affected_hub_ids)
        self.assertIn("toronto-montreal", risks[0].affected_corridor_ids)

    def test_road_closure_scores_above_minor_jam(self):
        def incident(incident_id, category, magnitude, delay):
            return TrafficIncident(
                id=incident_id,
                latitude=43.68,
                longitude=-79.62,
                category=category,
                description=incident_id,
                magnitude=magnitude,
                start_time=None,
                end_time=None,
                from_name="A",
                to_name="B",
                length_m=6000 if category == 8 else 100,
                delay_seconds=delay,
                road_numbers=(),
                time_validity="present",
                probability="certain",
                number_of_reports=None,
                last_report_time=None,
            )

        risks = build_operational_risks(
            (),
            (incident("jam", 6, 1, 1200), incident("closure", 8, 4, None)),
            self.hubs,
            self.corridors,
            self.settings,
        )

        self.assertEqual(risks[0].source_id, "closure")
        self.assertGreater(risks[0].score, risks[1].score)

    def test_adjacent_segments_of_same_incident_are_consolidated(self):
        base = TrafficIncident(
            id="segment-one",
            latitude=43.680,
            longitude=-79.620,
            category=8,
            description="Closed",
            magnitude=4,
            start_time=None,
            end_time=None,
            from_name="A",
            to_name="B",
            length_m=6000,
            delay_seconds=None,
            road_numbers=("ON-401",),
            time_validity="present",
            probability="certain",
            number_of_reports=None,
            last_report_time=None,
        )
        adjacent = TrafficIncident(
            **{
                **base.__dict__,
                "id": "segment-two",
                "latitude": 43.681,
                "longitude": -79.621,
            }
        )

        risks = build_operational_risks(
            (), (base, adjacent), self.hubs, self.corridors, self.settings
        )

        self.assertEqual(len(risks), 1)


if __name__ == "__main__":
    unittest.main()
