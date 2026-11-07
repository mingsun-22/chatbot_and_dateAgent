"""SSE（Server-Sent Events）相关的小工具。



前端通过“流式响应”实时接收后端一步步产生的事件。SSE 是一种基于 HTTP 的单向流协议，

约定每条消息以 `data: <内容>\\n\\n` 的格式发送。本模块提供：

- sse(): 把字典打包成一条 SSE 文本；

- stream_input(): 把前端请求转换成 LangGraph 的输入（新对话或恢复中断）；

- extract_interrupt_value(): 从图的输出块里识别“中断（等待用户输入）”事件。

"""

from __future__ import annotations  # 启用延迟注解求值

import json  # 将 Python 字典序列化为 JSON 字符串

from typing import Any  # 通用类型，用于图输入/输出等动态结构

from langgraph.types import Command  # LangGraph HITL 恢复命令，resume 字段对应 interrupt 返回值

from api.schemas import StreamRunRequest  # 约会规划流式/非流式运行的请求体模型


def sse(payload: dict[str, Any]) -> str:
    """把一个字典序列化为一条 SSE 消息文本。



    `ensure_ascii=False` 保证中文不被转义成 \\uXXXX；结尾的两个换行是 SSE 的分隔符。

    """

    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"  # 按 SSE 协议格式：data: + JSON + 双换行


def stream_input(req: StreamRunRequest) -> Any:
    """把前端请求转换成传给 graph.stream 的输入。
    LangGraph HITL 的两次调用形态：

    - 新开跑：`graph.stream({}, config={thread_id})` —— 对应这里返回 `req.input or {}`；

    - 恢复中断：`graph.stream(Command(resume=用户回答), config=同一 thread_id)` ——

      resume的值会成为节点里 `interrupt(prompt)` 的返回值。

    前端用同一个 threadId 发第二次请求时，务必带上 command.resume。

    - 带 command（且含 resume）：说明是在回答某次中断，用 Command(resume=...) 恢复图；

    - 否则：是一次全新运行，返回初始输入（通常是空字典）。

    """

    if req.command is not None:  # 请求里带了恢复命令，说明图此前在 interrupt 处暂停
        print(f"stream_input 恢复命令: {req.command.resume}")
        # resume 会把前端用户的回答穿透注入到上次中断（interrupt）的节点，让节点代码继续用这个值。
        # resume 适用于“人类补全缺失数据/决策”场景：流程暂停等待输入，用户答完后恢复到原处继续。
        # 和 goto 不同：goto 属于跳转控制，用于让图直接跳到新的节点执行（如无条件退出/重定向流程），而 resume 只是解开当前暂停，把数据补全后从断点往下顺序执行原图流程。
        return Command(resume=req.command.resume)  # 包装成 LangGraph Command，resume 会注入到中断节点

    return req.input or {}  # 首次运行：返回初始 state 输入，缺省为空字典


def extract_interrupt_value(chunk: Any) -> Any | None:
    """从图 stream 的一个输出块里提取“中断值”（即要向用户展示的问题）。

    LangGraph 在触发 interrupt 时，会在输出块里放一个特殊键 `__interrupt__`，

    其值通常是一个列表，元素带 `.value` 属性或 "value" 键。

    没有中断时返回 None。

    """

    if not isinstance(chunk, dict):  # 非字典块不可能是标准 updates 格式，直接跳过

        return None  # 表示本块不含中断信息

    raw = chunk.get("__interrupt__")  # 读取 LangGraph 注入的中断元数据

    if isinstance(raw, (list, tuple)) and raw:  # 中断值通常是含至少一个元素的列表/元组

        item = raw[0]  # 取第一个中断项（一般只有一个）

        # 兼容对象形式（有 .value 属性）和字典形式（有 "value" 键）两种结构。

        if hasattr(item, "value"):  # LangGraph Interrupt 对象常见写法

            return item.value  # 返回 interrupt() 调用时传入、要展示给用户的问题文本

        if isinstance(item, dict) and "value" in item:  # 字典形式的中断项

            return item["value"]  # 从字典中取出中断展示值

        return item  # 兜底：直接返回原始项

    return None  # 没有 __interrupt__ 或列表为空，表示本步未触发中断
