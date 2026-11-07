"""API 请求体的数据模型（Pydantic）。

FastAPI 会用这些模型自动校验并解析前端发来的 JSON，字段类型不匹配会直接返回 422 错误。
"""

from __future__ import annotations  # 启用延迟注解，便于使用 str | None 等联合类型写法

from typing import Any  # 任意类型占位符，用于 JSON 中结构不固定的字段

from pydantic import BaseModel  # Pydantic 基类，FastAPI 用它做请求体验证与序列化


class ResumeCommand(BaseModel):  # LangGraph HITL 恢复命令的请求体模型
    """恢复中断时携带的命令，resume 里放用户对上一次追问的回复。"""

    resume: Any | None = None  # LangGraph Command(resume=...) 要传回图里的用户回答，None 表示无恢复内容


class StreamRunRequest(BaseModel):  # 约会规划图运行（流式/非流式）的统一请求体
    """约会规划运行请求。

    - threadId: 会话标识，用于在 checkpointer 中定位/续接同一段对话；
    - input: 新对话的初始输入（一般为空）；
    - command: 若是回答中断，则携带 resume 内容。
    """

    threadId: str  # 会话唯一 id，对应 LangGraph config 里的 thread_id
    input: dict[str, Any] | None = None  # 首次运行时的图输入，通常为空字典
    command: ResumeCommand | None = None  # 非空时表示 HITL 恢复，携带用户对 interrupt 的回复


class EmotionBuildRequest(BaseModel):  # 情感知识库向量索引构建请求体
    """构建情感知识库索引的请求，可指定单本书名，None 表示构建 data 目录下全部。"""

    book_name: str | None = None  # 要索引的书籍文件名，None 则处理 data 目录下所有书籍


class EmotionChatRequest(BaseModel):  # 情感咨询流式对话请求体
    """情感咨询对话请求：会话 id + 用户这一句消息。"""

    threadId: str  # 情感咨询会话 id，用于 Redis 记忆与上下文续接
    message: str  # 用户当前发送的一句聊天内容
