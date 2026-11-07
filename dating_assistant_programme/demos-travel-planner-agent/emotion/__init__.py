"""emotion 包：基于书籍知识库的情感咨询（RAG）服务。

子模块职责一览（读代码时建议按这个顺序）：

- indexing/     建库：加载 PDF → 清洗切分 → 写入 Chroma 向量库
- retrieval.py  检索：连接 Chroma、MultiQueryRetriever、嵌入模型
- memory.py     记忆：Redis 多轮会话历史 + 窗口裁剪
- prompts.py    提示词：路由 yes/no、RAG 作答、直答、文档片段格式
- reports.py    报告：会话 → Markdown → PDF
- service.py    编排：RunnableBranch 在「RAG 链 / 直答链 / 生成报告」间分流

上层 API（api/emotion_routes.py）只调用本包导出的 emotion_service 与报告下载辅助函数。
"""
