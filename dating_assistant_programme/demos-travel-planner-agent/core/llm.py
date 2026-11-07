"""大模型（LLM）工厂模块。

统一在这里创建 `ChatOpenAI` 客户端，好处是：
- 全项目共用同一套模型、密钥、接口地址配置（都来自 settings）；
- 需要不同参数（如开启流式、调整温度）时，通过 **kwargs 传入即可，无需到处改。
"""

from __future__ import annotations  # 启用延迟注解求值

from typing import Any  # 用于 **kwargs 的任意额外参数类型

from langchain_openai import ChatOpenAI  # LangChain 的 OpenAI 兼容聊天模型客户端

from core.settings import settings  # 全局配置单例，含模型名、API Key、Base URL


def create_llm(**kwargs: Any) -> ChatOpenAI:  # 工厂函数：按全局配置创建可复用的 LLM 客户端
    """创建一个连接 Qwen（DashScope OpenAI 兼容接口）的对话模型客户端。

    为什么用 `langchain_openai.ChatOpenAI` 调通义千问？
    DashScope 提供了 OpenAI 兼容 HTTP 接口，只要改 base_url + api_key + model，
    现有 LangChain/LangGraph 代码（invoke / stream / with_structured_output）都能直接用。

    参数:
        **kwargs: 透传给 ChatOpenAI 的额外参数，例如 `streaming=True`、`temperature=0.2`。

    返回:
        配置好模型名、api_key、base_url 的 ChatOpenAI 实例。
    """
    return ChatOpenAI(  # 实例化 LangChain 聊天模型，底层走 OpenAI 兼容 HTTP API
        model=settings.qwen_model,  # 从环境变量读取的 Qwen 模型名，如 qwen-plus
        api_key=settings.dashscope_api_key,  # DashScope API 密钥
        base_url=settings.qwen_base_url,  # 通义千问 OpenAI 兼容端点地址
        **kwargs,  # 调用方可覆盖 streaming、temperature 等 LangChain 参数
    )
