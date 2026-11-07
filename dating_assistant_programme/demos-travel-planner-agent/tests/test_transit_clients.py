from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.clients import map_transit_route_summary


class TransitClientTest(unittest.TestCase):
    def test_transit_summary_contains_lines_and_duration_only(self) -> None:
        response = type("Response", (), {
            "raise_for_status": lambda self: None,
            "json": lambda self: {
                "status": "1",
                "route": {
                    "transits": [{
                        "duration": "1800",
                        "walking_distance": "800",
                        "cost": "4",
                        "segments": [
                            {"bus": {"buslines": [{"name": "Metro Line 1"}]}},
                            {"bus": {"buslines": [{"name": "Bus 7"}]}},
                        ],
                    }]
                },
            },
        })()
        fake_client = type("Client", (), {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *_args: None,
            "get": lambda self, _url, params: response,
        })
        with (
            patch("agent.clients.settings", type("Settings", (), {"amap_api_key": "test-key", "map_timeout_seconds": 5.0})()),
            patch("agent.clients.httpx.Client", return_value=fake_client()),
        ):
            result = map_transit_route_summary((30.1, 120.1), (30.2, 120.2), city="Hangzhou", date_value="2026-06-18")

        self.assertIn("Metro Line 1", result)
        self.assertIn("Bus 7", result)
        self.assertIn("30", result)
        self.assertNotIn("800", result)
        self.assertNotIn("4", result)


if __name__ == "__main__":
    unittest.main()
