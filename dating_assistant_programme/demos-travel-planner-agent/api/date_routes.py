"""约会规划相关的 HTTP 接口。



对外提供 4 个接口（前缀 /api/date）：

- POST /threads                     创建一个新会话，返回 threadId

- GET  /threads/{id}/state          查询某会话当前累积的状态

- POST /runs/stream-plan            流式运行图（SSE），实时推送节点/中断/最终结果

- POST /runs/invoke                 非流式运行图，一次性返回结果



同时内置一个轻量的“耗时日志”封装，方便教学时观察每个节点的执行时间。

"""

from __future__ import annotations  # 启用延迟注解求值

import logging  # 标准库日志，用于节点耗时统计

import time  # 高精度计时（perf_counter）

import uuid  # 生成 threadId、runId 等唯一标识

from collections.abc import Iterator  # 生成器返回类型注解

from typing import Any  # 图 state、chunk 等动态结构

from fastapi import APIRouter, HTTPException  # 路由与 HTTP 错误

from fastapi.responses import StreamingResponse  # SSE 流式 HTTP 响应

from langgraph.checkpoint.memory import MemorySaver  # 内存 checkpointer，支持 HITL 跨请求恢复

from agent.graph import builder  # LangGraph 图构建器（StateGraph 定义）

from api.schemas import StreamRunRequest  # 运行图时的请求体

from api.sse import extract_interrupt_value, sse, stream_input  # SSE 工具与中断提取

# 路由分组，统一加 /api/date 前缀。

router = APIRouter(prefix="/api/date")  # 约会规划 API 路由组

# 用内存 checkpointer 编译图：支持 interrupt / Command(resume=...) 恢复。

# 教学对照：agent/graph.py 里的 `graph = builder.compile()` 没有 checkpointer，

# 只能跑通一遍；这里挂上 MemorySaver 后，HITL 节点才能跨 HTTP 请求暂停/续跑。

# 注意：MemorySaver 在进程重启后会话会丢（生产可换成 Sqlite/Postgres checkpointer）。

graph = builder.compile(checkpointer=MemorySaver())  # 编译 LangGraph 并挂载内存持久化

# 记录已知的会话 id 集合（用于 state 查询时的存在性校验）。

threads: set[str] = set()  # 本进程内已创建的 threadId 集合

# ===== 配置一个独立的耗时日志器（不向根日志器传播，避免重复打印）=====

timing_logger = logging.getLogger("date_agent.timing")  # 专用 logger 名称，与业务日志隔离

if not timing_logger.handlers:  # 避免重复添加 handler（模块热重载时）

    handler = logging.StreamHandler()  # 输出到 stderr/stdout

    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))  # 简洁格式

    timing_logger.addHandler(handler)  # 绑定 handler

timing_logger.setLevel(logging.INFO)  # 只记录 INFO 及以上级别

timing_logger.propagate = False  # 不向 root logger 传播，防止重复打印


def _config(thread_id: str) -> dict[str, Any]:  # 内部工具：拼装 LangGraph 运行配置

    """构造 LangGraph 运行所需的 config，其中 thread_id 决定读写哪段会话。"""

    return {"configurable": {"thread_id": thread_id}}  # checkpointer 用 thread_id 作为会话键


def _public_values(thread_id: str) -> dict[str, Any]:  # 内部工具：读取会话当前 state 字段

    """读取某会话当前的完整状态字段，供前端渲染方案卡片。异常时返回空字典。"""

    try:  # get_state 可能因 checkpointer 异常失败

        state = graph.get_state(_config(thread_id))  # 从 checkpointer 读取当前图 state 快照

    except Exception:  # 任意异常时降级为空状态

        return {}  # 前端收到空 values 仍可展示

    return dict(state.values or {})  # 转为普通 dict，None 时用空字典


def _chunk_node_names(chunk: Any) -> list[str]:  # 内部工具：从 stream 块解析节点名

    """从图 stream 的一个输出块里取出本步执行的节点名（过滤掉 __ 开头的内部键）。"""

    if not isinstance(chunk, dict):  # updates 模式下 chunk 应为 {节点名: 更新内容}

        return []  # 非 dict 无法解析节点名

    return [name for name in chunk if not name.startswith("__")]  # 排除 __interrupt__ 等内部键


def _log_timing(event: str, **fields: Any) -> None:  # 内部工具：写结构化耗时日志

    """打印一条结构化的耗时日志，字段以 key=value 形式拼接。"""

    details = " ".join(f"{key}={value}" for key, value in fields.items())  # 拼接 key=value 对

    timing_logger.info("date_agent_timing event=%s %s", event, details)  # 写入耗时日志



def _timed_graph_stream(req: StreamRunRequest, endpoint: str, run_id: str) -> Iterator[Any]:  # 带计时的 stream 包装器

    """包装 graph.stream：在逐块产出的同时记录各节点耗时和中断事件。



    这是一个生成器：调用方（流式或非流式接口）迭代它即可拿到每个输出块，

    同时本函数在后台把节点开始、耗时、中断、完成、异常等都写进耗时日志。

    """

    start = time.perf_counter()  # 记录本次 run 的起始时间

    last = start  # 上一块产出时刻，用于计算块间耗时

    nodes: list[str] = []  # 累计已执行节点名列表

    _log_timing("run_start", run_id=run_id, endpoint=endpoint, thread_id=req.threadId)  # 记录 run 开始

    try:  # 捕获 stream 过程中的异常以便打日志后重新抛出

        # stream_mode="updates" 表示每个节点执行后产出一次“增量更新”块。

        for chunk in graph.stream(  # 迭代 LangGraph 流式输出

                stream_input(req),  # 新跑或 Command(resume) 恢复

                config=_config(req.threadId),  # 同 thread_id 才能续接 checkpointer 状态

                stream_mode="updates",  # 每完成一个节点 yield 一次 {节点名: state 增量}

        ):
            print(f"_timed_graph_stream chunk: {chunk}, type: {type(chunk)},thread_id: {req.threadId}")
            now = time.perf_counter()  # 当前块产出时刻

            elapsed_ms = int((now - last) * 1000)  # 距上一块的耗时（毫秒）

            names = _chunk_node_names(chunk)  # 本块涉及的节点名

            if names:  # 有实际节点更新才记日志

                nodes.extend(names)  # 追加到累计节点列表

                chunk_nodes = ",".join(names)  # 本块节点名逗号拼接

                for name in names:  # 每个节点单独一条耗时记录

                    _log_timing(

                        "node",  # 事件类型：节点完成

                        run_id=run_id,  # 本次运行 id

                        endpoint=endpoint,  # 调用的 HTTP 路径

                        thread_id=req.threadId,  # 会话 id

                        node=name,  # 当前节点名

                        chunk_nodes=chunk_nodes,  # 本块全部节点

                        elapsed_ms=elapsed_ms,  # 块间耗时

                    )

            interrupt_value = extract_interrupt_value(chunk)  # 检查是否触发 HITL 中断

            if interrupt_value is not None:  # 图在 interrupt 处暂停

                _log_timing(

                    "interrupt",  # 事件类型：中断

                    run_id=run_id,  # 本次运行 id

                    endpoint=endpoint,  # 调用的 HTTP 路径

                    thread_id=req.threadId,  # 会话 id

                    elapsed_ms=elapsed_ms,  # 触发中断前的块间耗时

                    total_ms=int((now - start) * 1000),  # 从 run 开始到中断的总耗时

                    nodes=",".join(nodes),  # 中断前已跑过的节点

                )

            # 把原始块继续交给调用方处理。

            yield chunk  # 透传 chunk 给上层 SSE 或 invoke 逻辑

            last = now  # 更新“上一块”时间戳

        _log_timing(

            "done",  # 事件类型：正常跑完

            run_id=run_id,  # 本次运行 id

            endpoint=endpoint,  # 调用的 HTTP 路径

            thread_id=req.threadId,  # 会话 id

            total_ms=int((time.perf_counter() - start) * 1000),  # 总耗时

            nodes=",".join(nodes),  # 全部执行过的节点

        )

    except Exception:  # stream 过程中任意异常

        # 记录异常耗时日志后重新抛出，交给上层接口决定如何回应前端。

        timing_logger.exception(  # 带堆栈的 ERROR 日志

            "date_agent_timing event=error run_id=%s endpoint=%s thread_id=%s total_ms=%s nodes=%s",

            run_id,  # 异常时的 run id

            endpoint,  # 异常时的 HTTP 路径

            req.threadId,  # 异常时的会话 id

            int((time.perf_counter() - start) * 1000),  # 异常时的总耗时

            ",".join(nodes),  # 异常前已执行节点

        )

        raise  # 重新抛出，由 stream_plan_run / invoke_run 处理


@router.post("/threads")  # HTTP POST：创建新的约会规划会话
def create_thread() -> dict[str, str]:  # 路由处理函数：分配 threadId

    """创建一个新会话，返回随机生成的 threadId。"""

    thread_id = str(uuid.uuid4())  # 生成 UUID 作为 LangGraph thread_id

    threads.add(thread_id)  # 登记到本地集合，供 get_thread_state 校验

    return {"threadId": thread_id}  # 返回给前端,前端收到的是JSON格式  用于后续 run/state 请求


@router.get("/threads/{thread_id}/state")  # HTTP GET：查询指定会话的图状态
def get_thread_state(thread_id: str) -> dict[str, Any]:  # 路由处理函数：读取 checkpointer 快照

    """查询指定会话当前累积的状态；会话不存在返回 404。"""

    if thread_id not in threads:  # 未在本进程 create 过的 id

        raise HTTPException(status_code=404, detail="thread not found")  # 404

    try:  # 从 checkpointer 读 state

        state = graph.get_state(_config(thread_id))  # 获取当前图状态快照

    except Exception:  # checkpointer 异常时降级

        return {"values": {}}  # 空 state

    return {"values": state.values or {}}  # 返回 state 中的业务字段（如方案、地点等）


@router.post("/runs/stream-plan")  # HTTP POST：SSE 流式运行约会规划图
def stream_plan_run(req: StreamRunRequest) -> StreamingResponse:  # 路由处理函数：推送 node/interrupt/final 事件

    """流式运行图：以 SSE 持续推送 node / interrupt / final / error 事件。"""

    if not req.threadId:  # 缺少 threadId 无法绑定 checkpointer

        raise HTTPException(status_code=400, detail="threadId required")  # 400

    threads.add(req.threadId)  # 确保 thread 在已知集合中（前端可能直接用已有 id）

    def event_stream():  # 内嵌生成器：供 StreamingResponse 逐条消费 SSE 事件

        """生成器：把图的每个输出块翻译成前端可消费的 SSE 事件。"""

        run_id = uuid.uuid4().hex[:12]  # 本次 run 的短 id，用于耗时日志关联

        try:  # 捕获异常并通过 SSE error 事件通知前端

            for chunk in _timed_graph_stream(req, "/api/date/runs/stream-plan", run_id):  # 带计时的 stream

                # 命中中断：推送中断事件（含当前已收集状态），然后结束本次流。

                interrupt_value = extract_interrupt_value(chunk)  # 解析 interrupt 展示内容

                if interrupt_value is not None:  # 图等待用户输入

                    yield sse(  # 发送 interrupt 类型 SSE 事件

                        {

                            "type": "interrupt",  # 事件类型：需要用户回答

                            "value": interrupt_value,  # interrupt() 传入的追问文本

                            "values": _public_values(req.threadId),  # 当前已收集的 state

                            "interrupted": True,  # 标记本次 run 因中断结束

                        }

                    )

                    return  # 中断后结束 SSE 流，等用户带 resume 再请求

                if not isinstance(chunk, dict):  # 非标准 updates 块跳过

                    continue  # 继续下一块

                # 普通节点更新：逐个推送 node 事件，让前端显示“运行中: xxx”。

                for name in chunk:  # 遍历 chunk 中的键（节点名或内部键）

                    if not name.startswith("__"):  # 过滤 LangGraph 内部键

                        yield sse({"type": "node", "name": name})  # 推送节点进度事件

            # 正常跑完（未中断）：推送最终状态。

            yield sse(  # 发送 final 类型 SSE 事件

                {

                    "type": "final",  # 事件类型：图执行完毕

                    "values": _public_values(req.threadId),  # 最终 state 供前端渲染

                    "interrupted": False,  # 未在中断处停止

                }

            )

        except Exception as exc:  # stream 或图节点内部异常

            # 运行出错：以 error 事件告知前端。

            yield sse({"type": "error", "message": str(exc)})  # 错误信息字符串

    return StreamingResponse(event_stream(), media_type="text/event-stream")  # 返回 SSE 响应


@router.post("/runs/invoke")  # HTTP POST：非流式一次性运行约会规划图
def invoke_run(req: StreamRunRequest) -> dict[str, Any]:  # 路由处理函数：聚合 stream 结果后 JSON 返回

    """非流式运行图：内部同样迭代 stream，但把结果聚合后一次性返回。"""

    if not req.threadId:  # 校验 threadId

        raise HTTPException(status_code=400, detail="threadId required")  # 400

    threads.add(req.threadId)  # 登记 thread

    nodes: list[str] = []  # 收集执行过的节点名

    run_id = uuid.uuid4().hex[:12]  # 耗时日志 run id

    try:  # 聚合 stream 结果

        for chunk in _timed_graph_stream(req, "/api/date/runs/invoke", run_id):  # 同样走带计时的 stream

            # 命中中断：立即返回，附带追问内容和已收集状态。

            interrupt_value = extract_interrupt_value(chunk)  # 检测 HITL 中断

            if interrupt_value is not None:  # 需要用户回答

                return {  # 一次性 JSON 响应（非 SSE）

                    "interrupted": True,  # 标记中断

                    "interruptValue": interrupt_value,  # 追问内容

                    "nodes": nodes,  # 中断前已执行节点

                    "values": _public_values(req.threadId),  # 当前 state

                }

            if isinstance(chunk, dict):  # 标准 updates 块

                for name in chunk:  # 遍历节点名

                    if not name.startswith("__"):  # 跳过内部键

                        nodes.append(name)  # 记录节点执行顺序

        # 正常跑完：返回执行过的节点列表和最终状态。

        return {  # 成功完成的 JSON 响应

            "interrupted": False,  # 未中断

            "nodes": nodes,  # 全部节点名

            "values": _public_values(req.threadId),  # 最终 state

        }

    except Exception as exc:  # 异常时不抛 HTTP 500，而是结构化返回

        # 出错时也返回 200，但带上 error 字段，让前端统一处理。

        return {  # 结构化错误响应，仍走 200 状态码

            "interrupted": False,  # 未在中断处结束

            "nodes": nodes,  # 异常前已执行节点

            "error": str(exc),  # 异常信息文本

            "values": _public_values(req.threadId),  # 尽量返回当前 state

        }
