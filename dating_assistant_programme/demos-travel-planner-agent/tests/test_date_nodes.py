from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.nodes import (
    _activity_search_terms,
    _date_area_fields,
    _infer_budget_search_terms,
    _parse_departure_from_text,
    _restaurant_search_terms,
    _resolve_departure_with_map,
    assemble_date_plan,
    collect_date_details_hitl,
    confirm_departure_hitl,
    research_activities,
    research_weather,
    summarize_transport_options,
)


class FakeStructuredLlm:
    def __init__(self, outputs: object | list[object]) -> None:
        self._outputs = iter(outputs if isinstance(outputs, list) else [outputs])

    def with_structured_output(self, _schema: object) -> "FakeStructuredLlm":
        return self

    def invoke(self, _prompt: str) -> object:
        return next(self._outputs)


class ConfirmDepartureTest(unittest.TestCase):
    def test_parse_departure_uses_structured_output(self) -> None:
        fake_llm = FakeStructuredLlm(type("Departure", (), {"departure_address": "杭州西湖区文三路"})())
        with patch("agent.nodes.llm", fake_llm):
            result = _parse_departure_from_text("我从杭州西湖区文三路出发")

        self.assertEqual(result, "杭州西湖区文三路")

    def test_new_departure_extracts_before_map_lookup(self) -> None:
        raw_reply = "我从杭州西湖区文三路出发"
        extracted = "杭州西湖区文三路"
        with (
            patch("agent.nodes.interrupt", return_value=raw_reply),
            patch("agent.nodes._parse_departure_from_text", return_value=extracted) as extract_mock,
            patch(
                "agent.nodes.map_geocode_detail",
                return_value={
                    "lat": 30.2731,
                    "lon": 120.1234,
                    "formatted_address": "浙江省杭州市西湖区文三路",
                },
            ) as geocode_mock,
        ):
            result = confirm_departure_hitl({})

        extract_mock.assert_called_once_with(raw_reply)
        geocode_mock.assert_called_once_with(extracted)
        self.assertEqual(result["departure_address"], "浙江省杭州市西湖区文三路")
        self.assertEqual(result["user_lat"], 30.2731)
        self.assertEqual(result["user_lon"], 120.1234)

    def test_unknown_departure_keeps_asking_until_map_resolves(self) -> None:
        replies = iter(["家里", "杭州西湖区文三路"])

        def fake_geocode(value: str) -> dict[str, object] | None:
            if value == "杭州西湖区文三路":
                return {
                    "lat": 30.2731,
                    "lon": 120.1234,
                    "formatted_address": "浙江省杭州市西湖区文三路",
                }
            return None

        with (
            patch("agent.nodes.interrupt", side_effect=lambda _prompt: next(replies)) as interrupt_mock,
            patch("agent.nodes.map_geocode_detail", side_effect=fake_geocode),
            patch("agent.nodes._parse_departure_from_text", side_effect=lambda value: value),
        ):
            result = confirm_departure_hitl({})

        self.assertEqual(interrupt_mock.call_count, 2)
        self.assertEqual(result["departure_address"], "浙江省杭州市西湖区文三路")

    def test_empty_departure_extraction_asks_before_map_lookup(self) -> None:
        replies = iter(["随便哪里", "杭州西湖区文三路"])
        extracted = iter(["", "杭州西湖区文三路"])

        with (
            patch("agent.nodes.interrupt", side_effect=lambda _prompt: next(replies)) as interrupt_mock,
            patch("agent.nodes._parse_departure_from_text", side_effect=lambda _value: next(extracted)),
            patch(
                "agent.nodes.map_geocode_detail",
                return_value={
                    "lat": 30.2731,
                    "lon": 120.1234,
                    "formatted_address": "浙江省杭州市西湖区文三路",
                },
            ) as geocode_mock,
        ):
            result = confirm_departure_hitl({})

        self.assertEqual(interrupt_mock.call_count, 2)
        geocode_mock.assert_called_once_with("杭州西湖区文三路")
        self.assertEqual(result["departure_address"], "浙江省杭州市西湖区文三路")

class CollectDateDetailsTest(unittest.TestCase):
    def test_collect_date_details_geocodes_date_area(self) -> None:
        fake_llm = FakeStructuredLlm(type("DateDetails", (), {
            "date_area": "杭州西湖区湖滨",
            "date_date": "6月18日",
            "date_time_range": "14:00-18:00",
        })())
        with (
            patch("agent.nodes.interrupt", return_value="6月18日在杭州西湖区湖滨约会，14:00-18:00"),
            patch("agent.nodes.llm", fake_llm),
            patch("agent.nodes.resolve_date_text", return_value="2026-06-18"),
            patch(
                "agent.nodes.map_geocode_detail",
                return_value={
                    "lat": 30.2559,
                    "lon": 120.1647,
                    "city": "杭州市",
                    "adcode": "330100",
                    "formatted_address": "浙江省杭州市西湖区湖滨",
                },
            ),
        ):
            result = collect_date_details_hitl({})

        self.assertEqual(result["date_area"], "浙江省杭州市西湖区湖滨")
        self.assertEqual(result["destination_lat"], 30.2559)
        self.assertEqual(result["destination_lon"], 120.1647)
        self.assertEqual(result["destination_adcode"], "330100")

    def test_collect_date_details_keeps_asking_until_area_resolves(self) -> None:
        replies = iter(["湖滨", "6月18日在杭州西湖区湖滨约会，14:00-18:00"])
        fake_llm = FakeStructuredLlm([
            type("DateDetails", (), {
                "date_area": "湖滨",
                "date_date": "6月18日",
                "date_time_range": "14:00-18:00",
            })(),
            type("DateDetails", (), {
                "date_area": "杭州西湖区湖滨",
                "date_date": "6月18日",
                "date_time_range": "14:00-18:00",
            })(),
        ])

        def fake_geocode(value: str) -> dict[str, object] | None:
            if value == "杭州西湖区湖滨":
                return {
                    "lat": 30.2559,
                    "lon": 120.1647,
                    "city": "杭州市",
                    "adcode": "330100",
                    "formatted_address": "浙江省杭州市西湖区湖滨",
                }
            return None

        with (
            patch("agent.nodes.interrupt", side_effect=lambda _prompt: next(replies)) as interrupt_mock,
            patch("agent.nodes.llm", fake_llm),
            patch("agent.nodes.resolve_date_text", return_value="2026-06-18"),
            patch("agent.nodes.map_geocode_detail", side_effect=fake_geocode),
        ):
            result = collect_date_details_hitl({})

        self.assertEqual(interrupt_mock.call_count, 2)
        self.assertEqual(result["date_area"], "浙江省杭州市西湖区湖滨")


class MapAddressValidationTest(unittest.TestCase):
    def test_date_area_rejects_empty_formatted_address(self) -> None:
        with patch(
            "agent.nodes.map_geocode_detail",
            return_value={"lat": 30.2559, "lon": 120.1647, "formatted_address": ""},
        ):
            self.assertIsNone(_date_area_fields("Hangzhou Hubin"))

    def test_departure_rejects_missing_formatted_address(self) -> None:
        with patch(
            "agent.nodes.map_geocode_detail",
            return_value={"lat": 30.2731, "lon": 120.1234, "formatted_address": None},
        ):
            self.assertIsNone(_resolve_departure_with_map("Hangzhou Wensan Road"))


class WeatherAndTransportTest(unittest.TestCase):
    def test_weather_match_uses_llm(self) -> None:
        fake_llm = type("FakeLlm", (), {"invoke": lambda self, _prompt: type("Msg", (), {"content": "weather summary"})()})()
        with (
            patch("agent.nodes.map_weather_forecast", return_value={"casts": [{"date": "2026-06-18", "dayweather": "sunny"}]}),
            patch("agent.nodes.llm", fake_llm),
        ):
            result = research_weather({"date_area": "Hangzhou", "date_date": "2026-06-18", "destination_adcode": "330100"})

        self.assertEqual(result["weather_summary"], "weather summary")

    def test_weather_out_of_range_skips_llm(self) -> None:
        with (
            patch("agent.nodes.map_weather_forecast", return_value={"casts": [{"date": "2026-06-19"}]}),
            patch("agent.nodes.llm") as llm_mock,
        ):
            result = research_weather({"date_area": "Hangzhou", "date_date": "2026-06-18", "destination_adcode": "330100"})

        llm_mock.invoke.assert_not_called()
        self.assertTrue(result["weather_summary"])

    def test_weather_unavailable_skips_llm(self) -> None:
        with (
            patch("agent.nodes.map_weather_forecast", return_value=None),
            patch("agent.nodes.llm") as llm_mock,
        ):
            result = research_weather({"date_area": "Hangzhou", "date_date": "2026-06-18", "destination_adcode": "330100"})

        llm_mock.invoke.assert_not_called()
        self.assertTrue(result["weather_summary"])

    def test_transport_summary_uses_required_coordinates(self) -> None:
        with patch("agent.nodes.map_transit_route_summary", return_value="Metro Line 1") as route_mock:
            result = summarize_transport_options({
                "date_area": "Hangzhou Hubin",
                "destination_city": "Hangzhou",
                "departure_address": "Hangzhou Wensan Road",
                "user_lat": 30.1,
                "user_lon": 120.1,
                "destination_lat": 30.2,
                "destination_lon": 120.2,
                "date_date": "2026-06-18",
            })

        route_mock.assert_called_once()
        self.assertEqual(route_mock.call_args.kwargs["city"], "Hangzhou")
        self.assertIn("Metro Line 1", result["travel_leg_summary"])


class RecommendationSearchTermsTest(unittest.TestCase):
    def test_budget_search_terms_uses_structured_output(self) -> None:
        fake_llm = FakeStructuredLlm(type("BudgetTerms", (), {"use_low_budget_terms": True})())
        with patch("agent.nodes.llm", fake_llm):
            terms = _infer_budget_search_terms("预算低一点，不要太贵")

        self.assertIn("性价比", terms)

    def test_activity_search_terms_adds_night_terms_for_evening(self) -> None:
        terms = _activity_search_terms({"date_time_range": "18:30-21:00"})

        self.assertIn("影院", terms)
        self.assertIn("密室逃脱", terms)
        self.assertIn("夜景", terms)

    def test_activity_search_terms_skips_night_terms_for_daytime(self) -> None:
        terms = _activity_search_terms({"date_time_range": "14:00-17:00"})

        self.assertIn("影院", terms)
        self.assertNotIn("夜景", terms)

    def test_restaurant_search_terms_follow_time_range(self) -> None:
        self.assertIn("午餐", _restaurant_search_terms({"date_time_range": "11:30-13:30"}))
        self.assertIn("下午茶", _restaurant_search_terms({"date_time_range": "14:00-16:30"}))
        self.assertIn("晚餐", _restaurant_search_terms({"date_time_range": "18:00-21:00"}))


class RecommendationWeatherContextTest(unittest.TestCase):
    def test_activity_recommendations_include_weather_context(self) -> None:
        captured_prompt_kwargs = {}

        def fake_prompt(**kwargs: object) -> str:
            captured_prompt_kwargs.update(kwargs)
            return "prompt"

        fake_llm = type("FakeLlm", (), {"invoke": lambda self, _prompt: type("Msg", (), {"content": "activities"})()})()
        fake_search = type("FakeSearch", (), {"invoke": lambda self, _query: {"results": [{"title": "Candidate", "url": "https://example.com", "content": "Summary"}]}})()
        with (
            patch("agent.nodes.search", fake_search),
            patch("agent.nodes.llm", fake_llm),
            patch("agent.nodes.activity_recommendations_prompt", side_effect=fake_prompt),
        ):
            result = research_activities({
                "date_area": "Hangzhou Hubin",
                "date_date": "2026-06-18",
                "date_time_range": "14:00-18:00",
                "date_preferences": "室内",
                "weather_summary": "有雨，建议室内活动。",
            })

        self.assertEqual(result["activity_recommendations"], "activities")
        self.assertEqual(captured_prompt_kwargs["weather_summary"], "有雨，建议室内活动。")

    def test_activity_recommendations_skip_llm_when_search_empty(self) -> None:
        fake_search = type("FakeSearch", (), {"invoke": lambda self, _query: {"results": []}})()
        with (
            patch("agent.nodes.search", fake_search),
            patch("agent.nodes.llm") as llm_mock,
        ):
            result = research_activities({
                "date_area": "Hangzhou Hubin",
                "date_date": "2026-06-18",
                "date_time_range": "14:00-18:00",
            })

        llm_mock.invoke.assert_not_called()
        self.assertFalse(result["activity_search_found"])
        self.assertEqual(result["activity_recommendations"], "未搜索到明确候选。")


class AssembleDatePlanFallbackTest(unittest.TestCase):
    def test_fallback_when_activity_and_restaurant_search_empty(self) -> None:
        with patch("agent.nodes.llm") as llm_mock:
            result = assemble_date_plan({
                "activity_search_found": False,
                "restaurant_search_found": False,
            })

        llm_mock.invoke.assert_not_called()
        self.assertIn("没有搜索到", result["agenda"])


if __name__ == "__main__":
    unittest.main()
