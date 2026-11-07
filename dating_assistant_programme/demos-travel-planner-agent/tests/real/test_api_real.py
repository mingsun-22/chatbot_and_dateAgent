from __future__ import annotations

import time
import unittest

import redis
from fastapi.testclient import TestClient
from pypdf import PdfReader

from api.main import app
from core.settings import settings
from tests.real.helpers import elapsed_ms, new_thread_id, parse_sse_lines, require_env


class RealApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_env(["DASHSCOPE_API_KEY", "TAVILY_API_KEY", "AMAP_API_KEY", "CHROMA_HOST", "REDIS_URL"])
        cls.client = TestClient(app)

    def test_date_thread_state_api(self) -> None:
        created = self.client.post("/api/date/threads")
        self.assertEqual(created.status_code, 200)
        thread_id = created.json()["threadId"]
        state = self.client.get(f"/api/date/threads/{thread_id}/state")
        self.assertEqual(state.status_code, 200)
        self.assertIn("values", state.json())


    def test_date_stream_plan_interrupt_api(self) -> None:
        start = time.perf_counter()
        created = self.client.post("/api/date/threads")
        self.assertEqual(created.status_code, 200)
        thread_id = created.json()["threadId"]

        with self.client.stream(
            "POST",
            "/api/date/runs/stream-plan",
            json={"threadId": thread_id, "input": {}},
        ) as response:
            self.assertEqual(response.status_code, 200)
            body = "".join(response.iter_text())

        events = parse_sse_lines(body)
        self.assertTrue(events)
        self.assertEqual(events[-1].get("type"), "interrupt")
        self.assertIn("value", events[-1])
        self.assertIn("values", events[-1])
        self.assertTrue(events[-1].get("interrupted"))
        print(f"[real-test] api_date_stream_plan_interrupt elapsed_ms={elapsed_ms(start)}")

    def test_emotion_chat_stream_api_cites_sources_in_answer(self) -> None:
        start = time.perf_counter()
        thread_id = new_thread_id()
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            with self.client.stream(
                "POST",
                "/api/emotion/chat/stream",
                json={"threadId": thread_id, "message": "忽冷忽热是不是黄灯信号？"},
            ) as response:
                self.assertEqual(response.status_code, 200)
                body = "".join(response.iter_text())

            events = parse_sse_lines(body)
            event_types = [event.get("type") for event in events]
            self.assertIn("delta", event_types)
            self.assertNotIn("sources", event_types)
            self.assertIn("done", event_types)

            answer = "".join(str(event.get("text") or "") for event in events if event.get("type") == "delta")
            self.assertTrue(answer.strip())
            self.assertIn("来源", answer)
            self.assertIn("第八章", answer)
            self.assertIn("识别有毒关系的信号", answer)
        finally:
            redis_client.delete(settings.emotion_redis_key_prefix + thread_id)

        print(f"[real-test] api_emotion_stream elapsed_ms={elapsed_ms(start)}")

    def test_emotion_report_download_api(self) -> None:
        start = time.perf_counter()
        thread_id = new_thread_id()
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            for message in (
                "我最近在一段关系里很没有安全感，对方忽冷忽热。",
                "我说出自己的感受以后，对方总说我太敏感，让我有点自我怀疑。",
                "请帮我生成一份恋爱报告。",
            ):
                with self.client.stream(
                    "POST",
                    "/api/emotion/chat/stream",
                    json={"threadId": thread_id, "message": message},
                ) as response:
                    self.assertEqual(response.status_code, 200)
                    body = "".join(response.iter_text())
                events = parse_sse_lines(body)

            report_events = [event for event in events if event.get("type") == "report"]
            self.assertTrue(report_events)
            download_url = str(report_events[-1]["downloadUrl"])
            pdf_response = self.client.get(download_url)
            self.assertEqual(pdf_response.status_code, 200)
            self.assertEqual(pdf_response.headers.get("content-type"), "application/pdf")
            self.assertGreater(len(pdf_response.content), 1000)

            import io

            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf_response.content)).pages)
            self.assertIn("恋爱关系观察报告", text)
        finally:
            redis_client.delete(settings.emotion_redis_key_prefix + thread_id)

        print(f"[real-test] api_emotion_report elapsed_ms={elapsed_ms(start)}")


if __name__ == "__main__":
    unittest.main()
