from __future__ import annotations

import unittest

from weather_dashboard.config import load_network, load_settings
from weather_dashboard.providers.routing import fetch_route
from weather_dashboard.providers.traffic import fetch_incidents, parse_traffic_payload
from weather_dashboard.providers.weather import parse_weather_payload


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payloads.pop(0))


class ProviderTests(unittest.TestCase):
    def test_weather_parser_tolerates_missing_optional_fields(self):
        payload = {
            "features": [
                {
                    "geometry": {"coordinates": [-79.4, 43.7]},
                    "properties": {
                        "name": {"en": "Toronto"},
                        "currentConditions": {
                            "temperature": {"value": {"en": 4}},
                            "condition": {"en": "Cloudy"},
                        },
                        "warnings": [
                            {
                                "type": {"en": "Snow squall warning"},
                                "description": {"en": "Visibility may be reduced."},
                            }
                        ],
                    },
                },
                {"geometry": None, "properties": {}},
            ]
        }

        stations = parse_weather_payload(payload)

        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0].city, "Toronto")
        self.assertEqual(stations[0].temperature_c, 4.0)
        self.assertEqual(stations[0].wind_gust_kmh, None)
        self.assertEqual(stations[0].alerts[0].alert_type, "Snow squall warning")

    def test_tomtom_category_eight_is_closed_and_zero_is_unknown(self):
        payload = {
            "incidents": [
                {
                    "geometry": {"type": "Point", "coordinates": [-79.4, 43.7]},
                    "properties": {
                        "id": "closed",
                        "iconCategory": 8,
                        "magnitudeOfDelay": 4,
                        "events": [{"description": "Road closed"}],
                        "length": 1000,
                    },
                },
                {
                    "geometry": {"type": "Point", "coordinates": [-79.5, 43.8]},
                    "properties": {
                        "id": "unknown",
                        "iconCategory": 0,
                        "magnitudeOfDelay": 0,
                        "events": [{"description": "Unknown"}],
                        "length": 0,
                    },
                },
            ]
        }

        incidents = parse_traffic_payload(payload)

        self.assertTrue(incidents[0].is_closed)
        self.assertFalse(incidents[1].is_closed)

    def test_incidents_are_deduplicated_across_bounding_boxes(self):
        incident = {
            "geometry": {"type": "Point", "coordinates": [-79.4, 43.7]},
            "properties": {
                "id": "same-id",
                "iconCategory": 6,
                "magnitudeOfDelay": 2,
                "events": [{"description": "Jam"}],
                "length": 200,
            },
        }
        session = FakeSession(
            [{"incidents": [incident]}, {"incidents": [incident]}]
        )

        incidents, freshness = fetch_incidents(
            "https://example.test/incidents",
            ("box-one", "box-two"),
            "key",
            5,
            "test-agent",
            session=session,
        )

        self.assertEqual(len(incidents), 1)
        self.assertTrue(freshness.available)
        self.assertEqual(len(session.calls), 2)

    def test_route_uses_truck_and_commercial_vehicle_parameters(self):
        hubs, corridors, truck = load_network()
        settings = load_settings()
        session = FakeSession(
            [
                {
                    "routes": [
                        {
                            "summary": {
                                "lengthInMeters": 100000,
                                "travelTimeInSeconds": 4000,
                                "trafficDelayInSeconds": 500,
                            },
                            "legs": [
                                {
                                    "points": [
                                        {"latitude": 43.7, "longitude": -79.4},
                                        {"latitude": 45.5, "longitude": -73.6},
                                    ]
                                }
                            ],
                        }
                    ]
                }
            ]
        )

        route = fetch_route(
            settings.tomtom_route_url,
            corridors[0],
            {hub.id: hub for hub in hubs},
            truck,
            "key",
            5,
            "test-agent",
            session=session,
        )

        params = session.calls[0][1]["params"]
        self.assertIsNotNone(route)
        self.assertEqual(params["travelMode"], "truck")
        self.assertEqual(params["vehicleCommercial"], "true")
        self.assertEqual(params["vehicleWeight"], truck.weight_kg)
        self.assertEqual(params["vehicleHeight"], truck.height_m)


if __name__ == "__main__":
    unittest.main()

