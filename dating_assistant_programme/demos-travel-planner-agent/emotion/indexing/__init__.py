"""emotion.indexing 子包：书籍向量索引构建流水线。

典型调用链：
    build_indexes(book_name)
      → candidate_book_paths / load_book_documents（loader）
      → split_book_documents（splitter）
      → Chroma.from_documents（service）

对外主要导出：`build_indexes`，供 EmotionRagService.build_indexes 与 API 建索引接口使用。
"""

from .service import build_indexes  # 从 service 子模块导出建索引入口函数，供上层直接调用
