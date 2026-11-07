from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.date_parser import resolve_date_text


class DateParserTest(unittest.TestCase):
    def test_resolve_date_text_uses_jionlp_time_field(self) -> None:
        with patch(
            "agent.date_parser.jio.parse_time",
            return_value={"time": ["2026-06-18 00:00:00", "2026-06-18 23:59:59"]},
        ):
            self.assertEqual(resolve_date_text("6?18?"), "2026-06-18")

    def test_resolve_date_text_raises_when_jionlp_cannot_parse(self) -> None:
        with patch("agent.date_parser.jio.parse_time", return_value=None):
            with self.assertRaises(ValueError):
                resolve_date_text("unknown date")

    def test_resolve_date_text_raises_for_unsupported_jionlp_shape(self) -> None:
        for value in ("2026-06-18 00:00:00", {"date": "2026-06-18 00:00:00"}, {"time": []}):
            with self.subTest(value=value):
                with patch("agent.date_parser.jio.parse_time", return_value=value):
                    with self.assertRaises(ValueError):
                        resolve_date_text("unknown date")


if __name__ == "__main__":
    unittest.main()
