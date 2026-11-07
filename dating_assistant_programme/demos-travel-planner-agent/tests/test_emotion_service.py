"""情感咨询服务单元测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.documents import Document
from langchain_core.runnables import RunnableGenerator, RunnableLambda

from emotion.service import EmotionRagService


class EmotionRagServiceTest(unittest.TestCase):
    """验证 RAG 链检索赋值与流式分片行为。"""

    def test_rag_chain_assigns_retrieved_documents_to_context(self) -> None:
        """检索结果应写入 stuff 链的 context，且保留 Document 元数据。"""
        documents = [Document(page_content="retrieved content", metadata={"book_name": "测试书籍"})]
        seen_queries: list[str] = []
        seen_inputs: list[dict[str, object]] = []

        fake_retriever = RunnableLambda(lambda query: seen_queries.append(query) or documents)
        fake_stuff_chain = RunnableLambda(lambda inputs: seen_inputs.append(inputs) or "answer")
        service = EmotionRagService()

        with (
            patch("emotion.service.create_llm", return_value=object()),
            patch("emotion.service.create_stuff_documents_chain", return_value=fake_stuff_chain) as stuff_factory,
            patch("emotion.service.create_multi_query_retriever", return_value=fake_retriever) as retriever_factory,
        ):
            chain = service._rag_chain_with_history()
            # 历史由调用方注入，不再依赖 RunnableWithMessageHistory / session_id。
            result = chain.invoke({"input": "关系问题", "history": []})

        self.assertEqual(result, "answer")
        self.assertEqual(seen_queries, ["关系问题"])
        self.assertEqual(seen_inputs[0]["context"], documents)
        self.assertEqual(seen_inputs[0]["context"][0].metadata, {"book_name": "测试书籍"})
        self.assertEqual(seen_inputs[0]["input"], "关系问题")
        retriever_factory.assert_called_once_with(service.similarity_top_k)
        stuff_factory.assert_called_once()

    def test_rag_chain_preserves_stuff_chain_streaming_chunks(self) -> None:
        """RAG 链应原样透传 stuff 链的流式分片。"""

        def stream_answer(_inputs: object):
            """模拟 stuff 链的流式输出。"""
            yield "a"
            yield "b"

        fake_retriever = RunnableLambda(lambda _query: [])
        fake_stuff_chain = RunnableGenerator(stream_answer)
        service = EmotionRagService()

        with (
            patch("emotion.service.create_llm", return_value=object()),
            patch("emotion.service.create_stuff_documents_chain", return_value=fake_stuff_chain),
            patch("emotion.service.create_multi_query_retriever", return_value=fake_retriever),
        ):
            chain = service._rag_chain_with_history()
            chunks = list(chain.stream({"input": "关系问题", "history": []}))

        self.assertEqual(chunks, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
