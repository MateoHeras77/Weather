from __future__ import annotations

import unittest

from weather_dashboard.models import MapBounds, OperationalRisk, Severity
from weather_dashboard.viewport import (
    TORONTO_CENTER,
    TORONTO_ZOOM,
    bounds_changed,
    parse_leaflet_bounds,
    risks_in_bounds,
)


def risk(risk_id: str, latitude: float, longitude: float) -> OperationalRisk:
    return OperationalRisk(
        id=risk_id,
        kind="weather",
        title=risk_id,
        summary="summary",
        latitude=latitude,
        longitude=longitude,
        severity=Severity.HIGH,
        score=70,
        affected_hub_ids=(),
        affected_corridor_ids=(),
        source_id=risk_id,
        source="test",
    )


class ViewportTests(unittest.TestCase):
    def test_toronto_is_the_default_center_and_zoom(self):
        self.assertEqual(TORONTO_CENTER, (43.6777, -79.6248))
        self.assertEqual(TORONTO_ZOOM, 8)

    def test_bounds_include_points_on_every_edge(self):
        bounds = MapBounds(south=43, west=-80, north=44, east=-79)
        risks = (
            risk("southwest", 43, -80),
            risk("northeast", 44, -79),
            risk("outside", 44.01, -79),
        )

        visible = risks_in_bounds(risks, bounds)

        self.assertEqual([item.id for item in visible], ["southwest", "northeast"])

    def test_leaflet_bounds_are_normalized(self):
        bounds = parse_leaflet_bounds(
            {
                "_southWest": {"lat": 43.1, "lng": -80.2},
                "_northEast": {"lat": 44.2, "lng": -78.8},
            }
        )

        self.assertEqual(
            bounds,
            MapBounds(south=43.1, west=-80.2, north=44.2, east=-78.8),
        )
        self.assertAlmostEqual(bounds.center[0], 43.6525, places=3)
        self.assertEqual(bounds.center[1], -79.5)

    def test_small_bound_rounding_does_not_trigger_rerun(self):
        current = MapBounds(43, -80, 44, -79)
        candidate = MapBounds(43.0001, -80.0001, 44.0001, -79.0001)

        self.assertFalse(bounds_changed(current, candidate))


if __name__ == "__main__":
    unittest.main()
