from __future__ import annotations

import unittest

from langchain_core.documents import Document

from emotion.indexing.splitter import is_noise_chunk, split_book_documents


class EmotionSplitterTest(unittest.TestCase):
    def test_cleaned_text_is_split_and_metadata_is_preserved(self) -> None:
        documents = [
            Document(
                page_content="这是 第一段。" * 80,
                metadata={"book_name": "测试书籍", "file_name": "测试书籍.txt", "page": 3},
            )
        ]

        chunks = split_book_documents(documents, max_chars=120, overlap_chars=20)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.page_content) <= 120 for chunk in chunks))
        self.assertTrue(all("这是第一段" in chunk.page_content for chunk in chunks))
        self.assertTrue(all(chunk.metadata.get("book_name") == "测试书籍" for chunk in chunks))
        self.assertTrue(all(chunk.metadata.get("file_name") == "测试书籍.txt" for chunk in chunks))
        self.assertTrue(all(chunk.metadata.get("page_start") == 3 for chunk in chunks))
        self.assertTrue(all(chunk.metadata.get("page_end") == 3 for chunk in chunks))

    def test_symbol_only_document_is_skipped(self) -> None:
        chunks = split_book_documents([Document(page_content="••••••••••\n……")])

        self.assertEqual(chunks, [])

    def test_symbol_only_chunks_are_noise(self) -> None:
        self.assertTrue(is_noise_chunk("••••••••••"))
        self.assertTrue(is_noise_chunk("……"))
        self.assertFalse(is_noise_chunk("怎么办……"))


if __name__ == "__main__":
    unittest.main()
