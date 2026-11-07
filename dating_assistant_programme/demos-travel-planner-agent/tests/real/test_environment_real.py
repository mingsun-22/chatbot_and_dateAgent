from __future__ import annotations

import time
import unittest

import redis

from agent.clients import llm, map_geocode_detail
from core.settings import settings
from emotion.retrieval import chroma_client
from tests.real.helpers import elapsed_ms, require_env


class RealEnvironmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_env(
            [
                "DASHSCOPE_API_KEY",
                "QWEN_BASE_URL",
                "QWEN_MODEL",
                "TAVILY_API_KEY",
                "AMAP_API_KEY",
                "CHROMA_HOST",
                "CHROMA_PORT",
                "REDIS_URL",
            ]
        )

    def test_required_settings_are_loaded(self) -> None:
        self.assertTrue(settings.dashscope_api_key)
        self.assertTrue(settings.tavily_api_key)
        self.assertTrue(settings.redis_url)
        self.assertEqual(settings.chroma_host, "192.168.150.109")

    def test_redis_chroma_amap_and_qwen_are_reachable(self) -> None:
        start = time.perf_counter()

        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.assertTrue(redis_client.ping())

        client = chroma_client()
        heartbeat = client.heartbeat()
        self.assertIsNotNone(heartbeat)

        geocode = map_geocode_detail("杭州湖滨")
        self.assertIsNotNone(geocode)
        assert geocode is not None
        self.assertGreaterEqual(float(geocode["lat"]), -90)
        self.assertLessEqual(float(geocode["lat"]), 90)
        self.assertGreaterEqual(float(geocode["lon"]), -180)
        self.assertLessEqual(float(geocode["lon"]), 180)

        response = llm.invoke("请只回复：真实环境连通。")
        self.assertIn("真实环境", str(response.content))

        print(f"[real-test] environment elapsed_ms={elapsed_ms(start)}")


if __name__ == "__main__":
    unittest.main()
