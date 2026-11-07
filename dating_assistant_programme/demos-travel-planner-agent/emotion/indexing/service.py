"""书籍向量索引构建服务。

情感咨询用的是 RAG（检索增强生成）：先把书籍切成小片段、向量化后存入 Chroma 向量库，
对话时再按语义检索相关片段喂给大模型。本模块负责“建库”这一步：

    加载书籍文件 → 清洗与切分 → 向量化写入 Chroma。
"""

from __future__ import annotations  # 允许在类型注解里引用尚未定义的类型名

from typing import Any  # 建索引 API 返回字典的类型标注

from langchain_chroma import Chroma  # LangChain 对 Chroma 的向量存储封装
from langchain_core.documents import Document  # LangChain 标准文档对象

from core.settings import PROJECT_ROOT, settings  # 项目根路径与全局配置
from emotion.retrieval import chroma_client, create_embedding_model  # Chroma 客户端与嵌入模型工厂

from .loader import BookConfig, candidate_book_paths, load_book_documents  # 书籍发现与加载
from .splitter import split_book_documents  # 文本清洗与切分


def build_books_vector_store(configs: list[BookConfig]) -> int:  # 把多本书切分后批量写入 Chroma
    """把若干本书加载、切分后写入 Chroma 向量库，返回写入的片段数量。

    参数:
        configs: 每本书对应一个 BookConfig（书名 + 目录路径）。

    返回:
        实际写入向量库的文档片段总数。
    """
    documents: list[Document] = []  # 累积所有书的切分片段，最后一次性写入 Chroma
    for config in configs:  # 逐本书加载、切分
        # 注意：用独立变量接收单本书的加载结果，再累加到总列表，
        # 避免在循环里覆盖累积结果（这是原始代码的一个 bug）。
        book_documents = load_book_documents(config)  # 加载单本书的全部 PDF 页面
        if not book_documents:  # 该书目录下没有可解析的 PDF
            raise ValueError(f"{config.book_name} 没有找到支持的书籍文件，当前仅支持 pdf 文件")  # 明确报错

        # 清洗去水印，正则清洗，并按语义切成小片段，只把切分后的片段加入索引。
        split_documents = split_book_documents(book_documents)  # 清洗 + RecursiveCharacterTextSplitter 切分
        documents.extend(split_documents)  # 把本书片段追加到总列表

    if not documents:  # 所有书切分后仍为空（极端情况）
        raise ValueError("书籍内容为空，无法构建索引")  # 无法建库

    # 重建前先清空同名集合，保证索引是干净的全量结果。
    reset_index_collections(client=chroma_client())  # 删除旧集合，避免残留脏数据

    # from_documents：对每个 Document 调 embedding 模型得到向量，再批量写入 Chroma。
    # 参数注意：
    # - embedding=  指定向量化模型（误写成 embedding_model= 会被忽略导致报错）；
    # - host/port   连接 .env 里配置的远程 Chroma（不要传不存在的 api_key/base_url）。
    Chroma.from_documents(
        documents=documents,  # 待向量化的全部切分片段
        embedding=create_embedding_model(),  # 与检索侧相同的嵌入模型，保证向量空间一致
        collection_name=settings.emotion_collection_name,  # 写入的情感书籍集合名
        host=settings.chroma_host,  # Chroma 服务主机
        port=settings.chroma_port,  # Chroma 服务端口
    )
    return len(documents)  # 返回实际写入的片段数量


def reset_index_collections(client=None) -> None:  # 重建索引前删除旧 Chroma 集合
    """删除已存在的向量集合（若不存在则忽略），用于重建索引前清场。"""
    client = client or chroma_client()  # 未传入客户端时新建默认 HTTP 客户端
    try:
        client.delete_collection(settings.emotion_collection_name)  # 删除旧集合，为全量重建腾位置
    except Exception:
        # 集合本来就不存在时会报错，这里直接忽略即可。
        pass  # 首次建库或集合已删时无需处理


def build_indexes(book_name: str | None = None) -> dict[str, Any]:  # 对外建索引入口，供 API 与 EmotionRagService 调用
    """对外的建索引入口：定位书籍目录 → 构建索引 → 返回结果摘要。

    参数:
        book_name: 指定单本书目录名；None 表示构建 data/emotion_books 目录下的全部书籍。

    返回:
        描述本次构建结果（成功统计或错误信息）的字典。
    """
    # 书籍统一放在项目根的 data/emotion_books 目录下，每本书是一个子目录。
    # candidate_book_paths 需要的是“父目录 + 可选书名”，所以这里始终传 emotion_books 目录，
    # 由它内部根据 book_name 决定返回单本还是全部（原始代码把 book_name 拼进了父目录，导致路径错误）。
    book_dir = PROJECT_ROOT / "data" / "emotion_books"  # 书籍根目录：项目根下的 data/emotion_books/
    paths = candidate_book_paths(book_dir, book_name)  # 解析待建索引的书目录列表
    if not paths:  # 找不到任何可建索引的书目录
        return {
            "book_name": book_name or "*",  # 请求的书名或通配符
            "status": "error",  # 错误状态
            "error": f"No buildable book directory found in {book_dir}",  # 错误说明
        }

    configs: list[BookConfig] = [BookConfig(book_name=path.name, path=path) for path in paths]  # 目录名即书名
    try:
        document_count = build_books_vector_store(configs)  # 执行加载→切分→写入 Chroma
        return {
            "book_name": "*",  # 成功时返回通配符表示可能构建了多本
            "title": "emotion counseling knowledge base",  # 知识库展示标题
            "collectionName": settings.emotion_collection_name,  # Chroma 集合名
            "bookCount": document_count,  # 写入的文档片段总数（字段名沿用历史命名）
            "books": [config.book_name for config in configs],  # 本次参与建库的书名列表
        }
    except Exception as ex:  # 加载、切分或写入过程中的任意异常
        return {
            "book_name": "*",  # 请求标识
            "title": "emotion counseling knowledge base",  # 知识库标题
            "collectionName": settings.emotion_collection_name,  # 目标集合名
            "status": "error",  # 错误状态
            "error": str(ex),  # 异常信息转字符串返回给 API 层
        }
