from __future__ import annotations

import unittest

from weather_dashboard.config import load_network
from weather_dashboard.models import (
    RouteResult,
    Severity,
    TrafficIncident,
    WeatherStation,
)
from weather_dashboard.route_analysis import (
    build_route_analysis,
    incidents_near_route,
    route_sample_points,
    route_scan_boxes,
    route_weather_stations,
)
from weather_dashboard.routes import (
    custom_route_endpoints,
    custom_route_request,
    request_for_corridor,
)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.hubs, self.corridors, _ = load_network()
        self.hubs_by_id = {hub.id: hub for hub in self.hubs}
        self.route = RouteResult(
            request_id="test-route",
            points=tuple((43.6 + index * 0.02, -79.7 + index * 0.03) for index in range(30)),
            distance_m=120000,
            travel_time_seconds=5000,
            traffic_delay_seconds=300,
        )

    def test_planning_network_contains_expanded_routes(self):
        corridor_ids = {corridor.id for corridor in self.corridors}
        self.assertGreaterEqual(len(self.hubs), 15)
        self.assertGreaterEqual(len(self.corridors), 18)
        self.assertIn("toronto-london", corridor_ids)
        self.assertIn("vancouver-victoria", corridor_ids)

    def test_saved_and_custom_requests_share_contract(self):
        saved = request_for_corridor(self.corridors[0], self.hubs_by_id)
        endpoints = custom_route_endpoints(self.hubs, ())
        custom = custom_route_request(endpoints[0], endpoints[1])

        self.assertTrue(saved.id.startswith("saved:"))
        self.assertTrue(custom.id.startswith("custom:"))
        self.assertIsNotNone(saved.corridor_id)
        self.assertIsNone(custom.corridor_id)

    def test_custom_request_rejects_identical_endpoint(self):
        endpoint = custom_route_endpoints(self.hubs, ())[0]
        with self.assertRaises(ValueError):
            custom_route_request(endpoint, endpoint)

    def test_route_sampling_and_boxes_are_bounded(self):
        samples = route_sample_points(self.route.points, target_count=9)
        boxes = route_scan_boxes(self.route.points)

        self.assertEqual(len(samples), 9)
        self.assertLessEqual(len(boxes), 18)
        self.assertEqual(samples[0], self.route.points[0])
        self.assertEqual(samples[-1], self.route.points[-1])

    def test_weather_and_incidents_are_selected_near_route(self):
        station = WeatherStation(
            city="Near",
            latitude=43.8,
            longitude=-79.4,
            condition="Rain",
            temperature_c=8,
            wind_speed_kmh=20,
            wind_direction="W",
            wind_gust_kmh=55,
            visibility_km=8,
            humidity_percent=80,
            pressure_kpa=100,
            wind_chill_c=None,
        )
        far_station = WeatherStation(
            **{
                **station.__dict__,
                "city": "Far",
                "latitude": 50,
                "longitude": -100,
            }
        )
        incident = TrafficIncident(
            id="near-closure",
            latitude=43.8,
            longitude=-79.4,
            category=8,
            description="Closed",
            magnitude=4,
            start_time=None,
            end_time=None,
            from_name="A",
            to_name="B",
            length_m=1000,
            delay_seconds=None,
            road_numbers=("401",),
            time_validity="present",
            probability="certain",
            number_of_reports=None,
            last_report_time=None,
        )
        far_incident = TrafficIncident(
            **{
                **incident.__dict__,
                "id": "far",
                "latitude": 50,
                "longitude": -100,
            }
        )

        weather = route_weather_stations(self.route, (station, far_station))
        incidents = incidents_near_route((incident, far_incident), self.route)

        self.assertEqual([item.city for item in weather], ["Near"])
        self.assertEqual([item.id for item in incidents], ["near-closure"])

    def test_route_analysis_preserves_partial_failure_message(self):
        request = request_for_corridor(self.corridors[0], self.hubs_by_id)

        analysis = build_route_analysis(
            request,
            self.route,
            (),
            (),
            errors=("Traffic coverage is partial",),
        )

        self.assertEqual(analysis.severity, Severity.LOW)
        self.assertEqual(analysis.errors, ("Traffic coverage is partial",))


if __name__ == "__main__":
    unittest.main()
