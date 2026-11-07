from __future__ import annotations

import time
import unittest

import redis
from langchain_core.messages import AIMessage, HumanMessage
from pypdf import PdfReader

from core.settings import settings
from emotion.memory import chat_history, trim_input_history
from emotion.retrieval import create_multi_query_retriever
from emotion.service import EmotionRagService
from tests.real.helpers import elapsed_ms, new_thread_id, require_env




class RealEmotionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        require_env(["DASHSCOPE_API_KEY", "CHROMA_HOST", "REDIS_URL"])
        cls.service = EmotionRagService()
        cls.retriever = create_multi_query_retriever(settings.emotion_similarity_top_k)

    def test_science_book_chapter_8_retrieval_quality(self) -> None:
        start = time.perf_counter()

        hot_cold_hits = self.retriever.invoke("忽冷忽热是不是黄灯信号？")
        self.assertTrue(hot_cold_hits)
        self.assertTrue(all((document.metadata or {}).get("book_title") for document in hot_cold_hits))
        self.assertTrue(all("page_start" in (document.metadata or {}) for document in hot_cold_hits))
        self.assertIn("对你的态度非常不稳定", "\n".join(document.page_content for document in hot_cold_hits))

        past_hits = self.retriever.invoke("对方不愿意说过去的感情经历，这正常吗？")
        self.assertIn("回避谈论过去的感情经历", "\n".join(document.page_content for document in past_hits))

        care_hits = self.retriever.invoke("对方总是打着关心的名义控制我怎么办？")
        self.assertIn("绑架式关心", "\n".join(document.page_content for document in care_hits))

        print(f"[real-test] emotion_retrieval_ch8 elapsed_ms={elapsed_ms(start)}")

    def test_science_book_chapter_9_retrieval_quality(self) -> None:
        start = time.perf_counter()

        hits = self.retriever.invoke("确立关系后总是吵架，怎么有效沟通？")
        self.assertTrue(hits)
        self.assertIn("沟通", "\n".join(document.page_content for document in hits))

        print(f"[real-test] emotion_retrieval_ch9 elapsed_ms={elapsed_ms(start)}")

    def test_stream_chat_uses_real_rag_and_cites_sources_in_answer(self) -> None:
        start = time.perf_counter()
        thread_id = new_thread_id()
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            events = list(
                self.service.stream_chat(
                    thread_id,
                    "对方总是打着关心的名义控制我，这算不算有毒关系的红灯信号？",
                )
            )
            event_types = [event.get("type") for event in events]
            self.assertIn("ready", event_types)
            self.assertIn("delta", event_types)
            self.assertNotIn("sources", event_types)
            self.assertIn("done", event_types)

            answer = "".join(str(event.get("text") or "") for event in events if event.get("type") == "delta")
            self.assertIn("绑架式关心", answer)
            self.assertIn("来源", answer)
        finally:
            redis_client.delete(settings.emotion_redis_key_prefix + thread_id)

        print(f"[real-test] emotion_stream_chat elapsed_ms={elapsed_ms(start)}")


    def test_stream_chat_direct_reply_skips_rag_sources(self) -> None:
        thread_id = new_thread_id()
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            events = list(self.service.stream_chat(thread_id, "谢谢你，我明白了"))
            event_types = [event.get("type") for event in events]
            self.assertIn("ready", event_types)
            self.assertIn("delta", event_types)
            self.assertIn("done", event_types)
            self.assertNotIn("sources", event_types)
        finally:
            redis_client.delete(settings.emotion_redis_key_prefix + thread_id)

    def test_tool_call_generates_love_report_pdf(self) -> None:
        start = time.perf_counter()
        thread_id = new_thread_id()
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            first_events = list(
                self.service.stream_chat(
                    thread_id,
                    "我最近很困扰，对方总是忽冷忽热，一会儿很热情，一会儿又几天不回消息。",
                )
            )
            self.assertIn("done", [event.get("type") for event in first_events])
            second_events = list(
                self.service.stream_chat(
                    thread_id,
                    "我表达不舒服的时候，对方会说我太敏感，还说自己只是太忙了。",
                )
            )
            self.assertIn("done", [event.get("type") for event in second_events])

            report_events = list(self.service.stream_chat(thread_id, "请根据刚才的聊天帮我生成一份恋爱报告"))
            event_types = [event.get("type") for event in report_events]
            self.assertIn("report", event_types)
            self.assertIn("done", event_types)
            report_event = next(event for event in report_events if event.get("type") == "report")
            self.assertTrue(report_event.get("downloadUrl"))

            from emotion.reports import find_report_file

            path = find_report_file(str(report_event.get("reportId")))
            self.assertIsNotNone(path)
            assert path is not None
            self.assertGreater(path.stat().st_size, 1000)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
            self.assertIn("恋爱关系观察报告", text)
            self.assertIn("当前关系画像", text)
            self.assertIn("给你的行动建议", text)
        finally:
            redis_client.delete(settings.emotion_redis_key_prefix + thread_id)

        print(f"[real-test] emotion_love_report elapsed_ms={elapsed_ms(start)}")

    def test_input_history_window_does_not_trim_real_redis(self) -> None:
        thread_id = new_thread_id()
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        key = settings.emotion_redis_key_prefix + thread_id
        try:
            history = chat_history(thread_id)
            history.clear()
            pair_count = (settings.emotion_memory_window_messages // 2) + 2
            for index in range(pair_count):
                history.add_messages(
                    [
                        HumanMessage(content=f"用户消息 {index}"),
                        AIMessage(content=f"助手消息 {index}"),
                    ]
                )
            self.assertGreater(len(history.messages), settings.emotion_memory_window_messages)

            trimmed = trim_input_history({"history": history.messages})
            self.assertEqual(len(trimmed["history"]), settings.emotion_memory_window_messages)
            self.assertGreater(redis_client.llen(key), settings.emotion_memory_window_messages)
        finally:
            redis_client.delete(key)


if __name__ == "__main__":
    unittest.main()
