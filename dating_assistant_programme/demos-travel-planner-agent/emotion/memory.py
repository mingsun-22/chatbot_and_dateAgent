"""情感咨询的会话记忆（基于 Redis）。

多轮对话需要“记住”前面聊过什么。这里用 Redis 按 thread_id 存储每个会话的历史消息，
并提供一个把历史裁剪到最近 N 条的工具，避免上下文过长、成本过高。

和约会助手 MemorySaver 的区别：
- LangGraph 的 MemorySaver：存的是整张图的 checkpoint（节点状态 + 中断点），用于 interrupt/resume；
- 这里的 RedisChatMessageHistory：只存聊天消息列表，由 EmotionRagService 在调用链前后显式读写。
"""

from __future__ import annotations  # 允许在类型注解里引用尚未定义的类型名

from langchain_community.chat_message_histories import RedisChatMessageHistory  # LangChain 社区版 Redis 聊天历史实现

from core.settings import settings  # 项目全局配置（Redis URL、记忆 TTL、窗口大小等）


def chat_history(thread_id: str) -> RedisChatMessageHistory:
    """按会话 id 获取一个 Redis 消息历史对象（读写该会话的多轮记忆）。

    异常:
        RuntimeError: 未配置 REDIS_URL 时抛出。
    """
    if not settings.redis_url:  # 未配置 Redis 连接串时无法持久化会话
        raise RuntimeError("缺少 REDIS_URL。")  # 提前失败，避免静默丢记忆
    return RedisChatMessageHistory(
        session_id=thread_id,  # 会话唯一标识，与 API 层的 thread_id 一一对应
        url=settings.redis_url,  # Redis 连接地址
        key_prefix=settings.emotion_redis_key_prefix,  # key 前缀，避免与其他业务键冲突
        ttl=settings.emotion_memory_ttl_seconds,  # 记忆自动过期时间（秒），过期后历史清空
    )


def trim_input_history(inputs: dict) -> dict:
    """把输入里的 history 列表裁剪到最近 N 条（N 来自配置），返回新的输入字典。

    只截取尾部最近若干条消息，既保留上下文，又控制提示词长度。
    """
    values = dict(inputs)  # 浅拷贝输入字典，避免原地修改上游数据
    history = values.get("history")  # 取出调用方注入的历史消息列表
    if isinstance(history, list):  # 仅当 history 确实是列表时才裁剪
        values["history"] = history[-settings.emotion_memory_window_messages :]  # 保留尾部最近 N 条消息
    return values  # 返回裁剪后的输入，供后续 prompt | llm 链使用
