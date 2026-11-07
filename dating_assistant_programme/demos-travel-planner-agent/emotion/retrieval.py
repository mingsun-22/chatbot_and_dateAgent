"""情感咨询的向量检索层。

封装“连接 Chroma 向量库、构建检索器”的逻辑：
- chroma_client(): 建立到远程 Chroma 服务的连接；
- emotion_collection_exists(): 判断书籍向量集合是否已建好（供路由判断，避免查询不存在的集合而报错）；
- create_multi_query_retriever(): 构建“多查询检索器”，先用 LLM 把问题改写成多个角度再检索，提高召回；
- create_embedding_model(): 创建把文本转成向量的嵌入模型。
"""

from __future__ import annotations  # 允许在类型注解里引用尚未定义的类型名

from typing import Any  # 用于 Chroma 客户端等第三方库返回值类型标注

import chromadb  # Chroma 向量数据库官方 Python 客户端
from langchain_chroma import Chroma  # LangChain 对 Chroma 的向量存储封装
from langchain_classic.retrievers import MultiQueryRetriever  # 多查询检索器：LLM 改写问题后合并检索结果
from langchain_core.prompts import PromptTemplate  # 提示词模板，用于多查询改写
from langchain_openai import OpenAIEmbeddings  # OpenAI 兼容接口的嵌入模型（此处接 DashScope）

from core.llm import create_llm  # 项目统一的 LLM 工厂函数
from core.settings import settings  # 全局配置：Chroma 地址、集合名、嵌入模型参数等


def chroma_client() -> Any:  # 创建 Chroma HTTP 客户端的工厂函数
    """创建一个连接到远程 Chroma 服务的 HTTP 客户端。"""
    return chromadb.HttpClient(
        host=settings.chroma_host,  # Chroma 服务主机地址
        port=settings.chroma_port,  # Chroma 服务端口
    )


def emotion_collection_exists() -> bool:  # 检查情感书籍向量集合是否已建好的守卫函数
    """判断情感书籍向量集合是否已经建好。

    这是修复“Collection [emotion_books] does not exist”报错的关键：
    对话前先用它判断集合是否存在，不存在就走“不检索、直接回答”的分支，
    而不是贸然去查询一个不存在的集合导致整个对话崩溃。

    返回:
        集合存在返回 True；不存在或连接失败返回 False。
    """
    try:
        client = chroma_client()  # 建立到 Chroma 的 HTTP 连接
        client.get_collection(settings.emotion_collection_name)  # 尝试获取已存在的集合，不存在会抛异常
        return True  # 能成功获取说明集合已建好
    except Exception:
        return False  # 集合不存在或网络/权限异常时，统一视为“未就绪”


def create_multi_query_retriever(top_k: int) -> MultiQueryRetriever:  # 构建多查询向量检索器
    """构建多查询检索器（Multi-Query Retriever）。

    工作方式：先让 LLM 把用户问题改写成多个不同角度的检索问题，分别检索后合并去重，
    比单次检索更不容易漏掉相关内容。

    参数:
        top_k: 每次检索返回的相似片段数量。
    """
    # create_collection_if_not_exists=False：集合不存在时不要偷偷新建空集合，
    # 由上层 emotion_collection_exists() 决定降级到直答，避免“空库还去检索”。
    vector_store = Chroma(
        collection_name=settings.emotion_collection_name,  # 情感书籍向量集合名称
        embedding_function=create_embedding_model(),  # 查询时也要用同一嵌入模型做向量化
        host=settings.chroma_host,  # Chroma 服务主机
        port=settings.chroma_port,  # Chroma 服务端口
        create_collection_if_not_exists=False,  # 禁止自动创建空集合，避免掩盖“索引未建”问题
    )
    # as_retriever 得到标准 LangChain Retriever：输入 str → 输出 list[Document]。
    base_retriever = vector_store.as_retriever(search_kwargs={"k": top_k})  # 每次检索返回 top_k 条最相似片段
    llm = create_llm()  # 用于把用户问题改写成多个检索 query
    # MultiQueryRetriever：LLM 改写多个 query → 各自检索 → 合并去重。
    return MultiQueryRetriever.from_llm(
        retriever=base_retriever,  # 底层向量检索器
        llm=llm,  # 负责问题改写的 LLM
        prompt=MULTI_QUERY_PROMPT,  # 改写提示词模板
        include_original=True,  # 检索时同时保留用户原始问题，不只用改写后的 query
    )


def create_embedding_model() -> OpenAIEmbeddings:  # 创建文本嵌入模型的工厂函数
    """创建文本嵌入（向量化）模型，用于把文本转成向量存取。

    使用 DashScope 的嵌入模型（OpenAI 兼容接口），维度由配置指定。
    """
    return OpenAIEmbeddings(
        model=settings.emotion_embed_model,  # 嵌入模型名称（如 text-embedding-v3）
        dimensions=settings.emotion_embed_dim,  # 向量维度，需与 Chroma 集合一致
        api_key=settings.dashscope_api_key,  # DashScope API 密钥
        base_url=settings.qwen_base_url,  # OpenAI 兼容接口基地址
        chunk_size=10,  # 每批向量化的文本条数，控制单次 API 请求量
        check_embedding_ctx_length=False,  # 关闭长度校验，兼容中文分片场景
    )


# 多查询检索用的“问题改写”提示词：把 1 个问题扩写成 3 个不同角度的检索问题。
MULTI_QUERY_PROMPT = PromptTemplate.from_template(
    """你是情感咨询知识库的检索查询改写助手。
请把用户的问题改写成 3 个不同角度的中文检索问题，用来从恋爱、关系、沟通类书籍中召回相关片段。

要求：
- 每行只输出 1 个检索问题。
- 总共只输出 3 行。
- 不要编号，不要解释。
- 保留用户原始问题中的关键关系处境、行为表现和困惑点。
- 可以补充更适合书籍知识库检索的同义表达。

用户问题：{question}"""
)  # PromptTemplate：{question} 占位符由 MultiQueryRetriever 自动填入用户原始问题
