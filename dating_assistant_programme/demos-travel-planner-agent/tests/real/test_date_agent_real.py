from __future__ import annotations

import time
import unittest
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agent.graph import builder
from tests.real.helpers import elapsed_ms, new_thread_id, require_env


class RealDateAgentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_env(["DASHSCOPE_API_KEY", "TAVILY_API_KEY", "AMAP_API_KEY"])

    def test_full_date_plan_flow(self) -> None:
        start = time.perf_counter()
        graph = builder.compile(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": new_thread_id()}}
        seen_nodes: list[str] = []

        payload, interrupted = self._stream_until_interrupt(graph, config, {}, seen_nodes)
        self.assertTrue(interrupted)
        self.assertIn("约会", str(payload))

        payload, interrupted = self._stream_until_interrupt(
            graph,
            config,
            Command(resume="明天在杭州西湖区湖滨约会，14:00-18:00"),
            seen_nodes,
        )
        self.assertTrue(interrupted)
        self.assertIn("出发地", str(payload))

        payload, interrupted = self._stream_until_interrupt(
            graph,
            config,
            Command(resume="杭州西湖区文三路"),
            seen_nodes,
        )
        self.assertTrue(interrupted)
        self.assertIn("偏好", str(payload))

        _, interrupted = self._stream_until_interrupt(
            graph,
            config,
            Command(resume="喜欢安静咖啡、湖边散步、晚餐环境好，预算中等"),
            seen_nodes,
        )
        self.assertFalse(interrupted)

        final_state = graph.get_state(config).values
        agenda = str(final_state.get("agenda") or "")
        self.assertIn("时间线", agenda)
        self.assertIn("简短总结", agenda)
        self.assertTrue(final_state.get("weather_summary"))
        self.assertTrue(final_state.get("travel_leg_summary"))
        self.assertTrue(final_state.get("activity_recommendations"))
        self.assertTrue(final_state.get("restaurant_recommendations"))

        required_nodes = {
            "research_weather",
            "summarize_transport_options",
            "research_activities",
            "research_restaurants",
            "assemble_date_plan",
        }
        self.assertTrue(required_nodes.issubset(set(seen_nodes)), sorted(set(required_nodes) - set(seen_nodes)))
        self.assertNotIn("infer_departure_candidate_parallel", seen_nodes)
        self.assertNotIn("join_parallel_date_prep", seen_nodes)
        self.assertNotIn("ask_satisfaction_hitl", seen_nodes)
        self.assertNotIn("ask_dissatisfaction_reason_hitl", seen_nodes)
        self.assertNotIn("finalize_date_plan", seen_nodes)
        print(f"[real-test] date_agent_full elapsed_ms={elapsed_ms(start)} nodes={','.join(seen_nodes)}")

    @staticmethod
    def _stream_until_interrupt(graph: Any, config: dict[str, Any], inp: Any, seen_nodes: list[str]) -> tuple[Any, bool]:
        for chunk in graph.stream(inp, config=config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                return chunk["__interrupt__"][0].value, True
            if isinstance(chunk, dict):
                for node_name in chunk:
                    if not node_name.startswith("__"):
                        seen_nodes.append(node_name)
        return None, False


if __name__ == "__main__":
    unittest.main()
