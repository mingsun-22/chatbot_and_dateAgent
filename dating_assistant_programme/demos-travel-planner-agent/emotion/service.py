"""情感咨询核心服务（RAG + 会话记忆 + 恋爱报告）。

这是情感咨询模块的“大脑”，把各部分串起来：
1. 路由：先判断用户这句话要不要查知识库（RAG）；
2. 若走 RAG：多查询检索书籍片段 → 拼进提示词 → 流式生成带引用的回答；
3. 若不走 RAG：基于会话历史直接回答（寒暄、情绪承接等）；
4. 特殊指令：识别到“生成恋爱报告”时，汇总最近对话生成 PDF 报告。

所有分支都带 Redis 会话记忆：调用前手动注入 history，调用后写回本轮问答。
（不再使用已弃用的 RunnableWithMessageHistory，避免 LangChainDeprecationWarning。）

和约会助手的对比（帮你建立心智模型）：
- 约会助手用的是 LangGraph（StateGraph + interrupt 人在环）；
- 情感咨询用的是 LangChain Runnable 组合（| 管道、RunnableBranch），
  会话记忆由本模块显式读写 Redis，没有图节点，而是“条件分支 + 链”。
"""

from __future__ import annotations  # 允许在类型注解里引用尚未定义的类型名

import uuid  # 生成新会话 thread_id
from typing import Any, Iterable  # Any 用于 Runnable 链类型；Iterable 用于流式事件产出

from langchain_classic.chains.combine_documents import create_stuff_documents_chain  # 把多个 Document 塞进同一 prompt 的 RAG 链
from langchain_core.messages import AIMessage, BaseMessage, BaseMessageChunk, HumanMessage  # LangChain 消息类型
from langchain_core.output_parsers import StrOutputParser  # 把 LLM 输出解析为纯字符串
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate  # 聊天提示词模板
from langchain_core.runnables import RunnableBranch, RunnableLambda, RunnablePassthrough  # LCEL 组合原语

from core.llm import create_llm  # 项目统一的 LLM 工厂
from core.settings import settings  # 全局配置：检索条数、记忆窗口等
from emotion.indexing.service import build_indexes as build_emotion_indexes  # 建索引入口，委托给 indexing 子模块
from emotion.memory import chat_history, trim_input_history  # Redis 会话记忆与历史裁剪
from emotion.prompts import DIRECT_SYSTEM_PROMPT, DOCUMENT_PROMPT_TEMPLATE, RAG_ROUTE_PROMPT, RAG_SYSTEM_PROMPT  # 提示词常量
from emotion.reports import create_love_report_from_markdown, stream_report_markdown_from_messages  # 恋爱报告生成
from emotion.retrieval import create_multi_query_retriever, emotion_collection_exists  # 向量检索与集合存在性检查


def _chunk_text(chunk: Any) -> str:
    """从流式返回的分片中安全地取出文本内容（兼容消息对象和纯字符串）。"""
    if isinstance(chunk, BaseMessageChunk | BaseMessage):  # LangChain 流式消息分片或完整消息
        return str(chunk.content or "")  # 取 .content 字段并转为字符串
    return str(chunk or "")  # 其他类型（如纯 str）直接转字符串


class EmotionRagService:
    """情感咨询服务：封装路由、RAG、直答、报告生成等能力。

    内部对三条链（路由链/RAG 链/直答链）做了懒加载缓存，首次用到才构建。
    会话记忆通过 Redis 显式读写，不再依赖已弃用的 RunnableWithMessageHistory。
    """

    def __init__(self) -> None:
        """初始化配置与三条链的懒加载缓存位。"""
        # 读取配置：检索条数、参与推理的历史消息窗口。
        self.similarity_top_k = settings.emotion_similarity_top_k  # 每次向量检索返回的片段数
        self.memory_window_messages = settings.emotion_memory_window_messages  # 送入 LLM 的历史消息条数上限
        # 三条链的缓存位（懒加载）。
        self._rag_chain: Any | None = None  # RAG 链缓存（不含历史包装）
        self._direct_chain: Any | None = None  # 直答链缓存（不含历史包装）
        self._rag_condition_chain: Any | None = None  # 路由判断链缓存（返回 bool）

    def create_thread(self) -> str:
        """创建一个新会话 id（作为 Redis 记忆的 key）。"""
        return str(uuid.uuid4())  # UUID4 保证全局唯一

    def build_indexes(self, book_name: str | None = None) -> dict[str, Any]:
        """构建/重建书籍向量索引，委托给 indexing 子模块。"""
        return build_emotion_indexes(book_name)  # 转发到 emotion.indexing.service.build_indexes

    def stream_chat(self, thread_id: str, message: str) -> Iterable[dict[str, Any]]:
        """处理一次对话，以“事件字典”的形式流式产出结果。

        产出的事件类型：ready（开始）、delta（增量文本）、report（报告信息）、
        done（结束）、error（出错）。上层路由会把它们包成 SSE 发给前端。
        """
        clean_message = message.strip()  # 去掉首尾空白
        print(f"EmotionRagService:stream_chat-clean_message: {clean_message}")
        if not clean_message:  # 空消息直接报错
            yield {"type": "error", "message": "消息不能为空!"}  # 产出错误事件
            return  # 提前结束生成器

        yield {"type": "ready"}  # 通知前端：流式响应已开始

        try:
            # 分支一：用户想生成恋爱报告 —— 汇总最近对话，流式生成 Markdown 并转成 PDF。
            if self._is_report_requested(clean_message):  # 关键词命中“生成/下载报告”等
                history = chat_history(thread_id)  # 获取该会话的 Redis 消息历史对象
                messages = trim_input_history({"history": history.messages})["history"]  # 裁剪到最近 N 条
                markdown_parts: list[str] = []  # 累积流式生成的 Markdown 片段
                for text in stream_report_markdown_from_messages(messages):  # LLM 根据最近上下文流式写报告
                    markdown_parts.append(text)  # 拼入完整 Markdown
                    yield {"type": "delta", "text": text}  # 每个 token 分片推给前端

                report = create_love_report_from_markdown("".join(markdown_parts))  # Markdown → PDF 落盘
                assistant_text = f"恋爱报告已生成：[{report.filename}]({report.download_url})"  # 助手回复中的 Markdown 链接
                # 把这轮问答写回记忆。
                history.add_messages(
                    [HumanMessage(content=clean_message), AIMessage(content=assistant_text)]
                )  # 持久化到 Redis

                yield {
                    "type": "delta",
                    "text": f"\n\n恋爱报告 PDF 已生成，可以点击下方链接下载：{report.filename}",
                }  # 补充下载提示
                yield {
                    "type": "report",  # 报告元数据事件，供前端展示下载按钮
                    "reportId": report.report_id,  # 报告唯一 id
                    "downloadUrl": report.download_url,  # 下载 API 路径
                    "filename": report.filename,  # PDF 文件名
                }
                yield {"type": "done"}  # 报告分支结束
                return  # 不再走普通问答链

            # 分支二：普通问答或 RAG 回答。
            # 必须先判断向量集合是否已建好，再决定要不要构建 RAG 链。
            # Chroma(create_collection_if_not_exists=False) 在构造检索器时就会查集合，
            # 集合不存在会直接抛错，因此集合未建好时一律走直答链。
            inputs = self._prepare_chain_inputs(thread_id, clean_message)  # 注入并裁剪会话历史

            if emotion_collection_exists():  # 向量库已就绪，可以走 RAG 路由
                # RunnableBranch：条件为 True 走 RAG；否则走默认直答链。
                chain: Any = RunnableBranch(
                    (self._rag_condition(), self._rag_chain_with_history()),  # 条件为 True 时走 RAG 链
                    self._direct_chain_with_history(),  # 默认分支：直答链
                )
            else:
                # 集合未建好：一律走直答链，保证对话仍能正常进行（只是没有书籍引用）。
                chain = self._direct_chain_with_history()  # 跳过 RAG，避免查询不存在的集合

            assistant_parts: list[str] = []  # 累积本轮助手完整回复，用于写回 Redis
            for chunk in chain.stream(inputs):  # 遍历 LLM 流式输出的每个分片
                text = _chunk_text(chunk)  # 从分片中提取纯文本
                if text:  # 跳过空分片
                    assistant_parts.append(text)  # 拼完整回复
                    yield {"type": "delta", "text": text}  # 增量文本事件推给前端

            # 与原先 RunnableWithMessageHistory 一致：流结束后把本轮问答写回 Redis。
            self._persist_turn(thread_id, clean_message, "".join(assistant_parts))
            yield {"type": "done"}  # 普通问答流结束

        except Exception as exc:  # 链执行、检索、记忆等任意环节异常
            yield {"type": "error", "message": str(exc)}  # 把异常信息转成错误事件

    def _prepare_chain_inputs(self, thread_id: str, message: str) -> dict[str, Any]:
        """从 Redis 读取会话历史，裁剪后组装成链的标准输入字典。"""
        history = chat_history(thread_id)  # 按 thread_id 定位 Redis 会话
        return trim_input_history(
            {
                "input": message,  # 用户本轮消息
                "history": list(history.messages),  # 历史消息列表（不含本轮）
            }
        )

    def _persist_turn(self, thread_id: str, user_message: str, assistant_text: str) -> None:
        """把本轮用户消息与助手回复追加写入 Redis 会话历史。"""
        history = chat_history(thread_id)  # 同一 thread_id 对应同一段 Redis 记忆
        history.add_messages(
            [HumanMessage(content=user_message), AIMessage(content=assistant_text)]
        )  # 追加一轮完整对话

    def _is_report_requested(self, message: str) -> bool:
        """通过关键词判断用户是否在要求生成/下载恋爱报告。"""
        keywords = (
            "生成报告",
            "下载报告",
            "导出报告",
            "恋爱报告",
            "关系报告",
            "情感报告",
            "恋爱分析文档",
        )  # 触发报告分支的关键词
        return any(keyword in message for keyword in keywords)  # 任一关键词命中即返回 True

    def _rag_condition(self) -> Any:
        """构建“是否走 RAG”的判断链（懒加载缓存）。

        这里只负责让路由 LLM 判断“这句话是否需要查知识库”（返回是否以 yes 开头）；
        “向量集合是否存在”的前置判断已在 stream_chat 顶层完成，此处不再重复检查。
        """
        if self._rag_condition_chain is not None:  # 已构建过则直接复用，使用缓存
            return self._rag_condition_chain

        llm = create_llm()  # 路由用小模型即可，默认非流式
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", RAG_ROUTE_PROMPT),  # 路由 system 提示：只输出 yes/no
                ("human", "{input}"),  # 用户本轮输入
            ]
        )
        # LCEL 管道：Prompt → LLM → 纯文本 → 布尔值。
        # `|` 是 LangChain 的 Runnable 组合运算符，左边输出作为右边输入。
        self._rag_condition_chain = prompt | llm | StrOutputParser() | RunnableLambda(
            lambda text: str(text).strip().lower().startswith("yes")  # yes 开头 → True，走 RAG 分支
        )
        return self._rag_condition_chain  # 返回可复用的条件 Runnable

    def _rag_chain_with_history(self) -> Any:
        """构建 RAG 链（懒加载缓存）。

        流程：检索片段填充 context → 套用 RAG 系统提示 + 历史 + 问题 → 流式生成带引用的回答。
        会话历史由 stream_chat 在调用前注入 inputs["history"]，不再使用 RunnableWithMessageHistory。
        """
        if self._rag_chain is not None:  # 已构建过则直接复用
            return self._rag_chain

        llm = create_llm(streaming=True)  # RAG 回答需要流式输出
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", RAG_SYSTEM_PROMPT),  # RAG system 提示，含 {context} 占位符
                MessagesPlaceholder("history"),  # 会话历史占位符，由调用方注入
                ("human", "{input}"),  # 用户本轮问题
            ]
        )
        # stuff：把多个 Document“塞进”同一个 prompt 的 {context}（适合片段不太多时）。
        document_prompt = PromptTemplate.from_template(DOCUMENT_PROMPT_TEMPLATE)  # 单片段格式化模板
        stuff_chain = create_stuff_documents_chain(
            llm,  # 生成最终回答的 LLM
            prompt,  # 含 history、input、context 的主提示词
            document_prompt=document_prompt,  # 每个 Document 如何渲染进 context
            document_separator="\n\n",  # 片段之间的分隔符
            document_variable_name="context",  # prompt 中接收检索结果的变量名
        )
        retriever = create_multi_query_retriever(self.similarity_top_k)  # 多查询向量检索器
        # RunnablePassthrough.assign：在原输入上新增 context 字段。
        # 右侧 `(lambda → input) | retriever`：用用户问题检索，得到 Document 列表。
        self._rag_chain = (
            RunnablePassthrough.assign(context=(lambda values: values["input"]) | retriever)
            | stuff_chain
        )  # 检索 + 生成
        return self._rag_chain  # 返回 RAG 链（历史由上层注入）

    def _direct_chain_with_history(self) -> Any:
        """构建“直答链”（不检索知识库，懒加载缓存）。

        会话历史由 stream_chat 在调用前注入 inputs["history"]，不再使用 RunnableWithMessageHistory。
        """
        if self._direct_chain is not None:  # 已构建过则直接复用
            return self._direct_chain

        llm = create_llm(streaming=True)  # 直答也需要流式输出
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", DIRECT_SYSTEM_PROMPT),  # 直答 system 提示：不查库
                MessagesPlaceholder("history"),  # 会话历史占位符，由调用方注入
                ("human", "{input}"),  # 用户本轮输入
            ]
        )
        self._direct_chain = prompt | llm  # 拼提示词 → LLM 生成
        return self._direct_chain  # 返回直答链（历史由上层注入）


# 全局单例：路由层通过它调用情感咨询能力。
emotion_service = EmotionRagService()  # 模块级单例，api/emotion_routes 直接 import 使用
