"""
Deployed test script — runs against a live LangSmith Deployment.
=================================================================
This shows how to interact with the agent via the LangGraph SDK once it's
deployed to LangSmith Cloud (or any self-hosted deployment).

The graph accepts **empty** initial input: the first interrupt collects
destination and dates. If GeoIP fails, the next asks for departure location;
then preferences are collected after weather.

Environment variables needed:
    DEPLOYMENT_URL      — e.g. https://travel-planner-abc123.langsmith.com
    LANGSMITH_API_KEY   — your LangSmith API key
""" # 部署测试脚本，作用说明和环境变量要求

import asyncio  # 导入异步IO库
import os       # 导入操作系统库
import sys      # 导入系统库

from dotenv import load_dotenv        # 导入加载环境变量的库
from langgraph_sdk import get_client  # 导入LangGraph SDK的客户端

load_dotenv()    # 加载.env环境变量文件


def _is_origin_followup_prompt(payload) -> bool:
    t = str(payload or "").lower()    # 转小写字符串
    return "couldn't automatically" in t or "departing from" in t  # 判断是否需要补充出发地信息


DEPLOYMENT_URL = os.environ.get("DEPLOYMENT_URL")      # 获取部署URL环境变量
LANGSMITH_API_KEY = os.environ.get("LANGSMITH_API_KEY")  # 获取API KEY环境变量

if not DEPLOYMENT_URL:  # 如果没设置部署URL
    sys.exit(
        "Error: DEPLOYMENT_URL is not set.\n"
        "Add it to your .env file: DEPLOYMENT_URL=https://your-deployment-url"
    )   # 输出错误并退出


async def run():
    client = get_client(url=DEPLOYMENT_URL, api_key=LANGSMITH_API_KEY)  # 创建LangGraph客户端

    print("=" * 55)     # 输出分隔线
    print("  Travel Planner Agent — Deployed Test")  # 测试说明
    print("=" * 55)     # 输出分隔线
    print()             # 空行

    thread = await client.threads.create()     # 创建对话线程
    thread_id = thread["thread_id"]            # 获取线程ID
    print(f"  Thread created: {thread_id}\n")  # 打印线程ID

    async def stream_until_interrupt(thread_id_: str, inp: dict | None, command: dict | None):
        interrupted = False         # 是否中断标志
        payload = None              # 收到的中断内容
        kwargs: dict = {
            "thread_id": thread_id_,                # 线程ID
            "assistant_id": "travel_planner",       # 助手ID
            "stream_mode": "updates",               # 流式模式
        }
        if command is not None:                # 如果带command（恢复请求）
            kwargs["command"] = command
        else:                                  
            kwargs["input"] = inp if inp is not None else {}   # 否则传入初始输入

        async for chunk in client.runs.stream(**kwargs):   # 异步遍历每个消息块
            if chunk.event != "updates":   # 只关心updates事件
                continue
            if "__interrupt__" in chunk.data:                       # 判断是否有中断
                intr = chunk.data["__interrupt__"][0]               # 拿到中断内容
                payload = intr["value"] if isinstance(intr, dict) else intr.value # 获取具体数值
                interrupted = True                                  # 标记中断
                break                                               # 跳出循环
            node_name = list(chunk.data.keys())[0]                  # 当前节点名称
            print(f"  + {node_name}")                               # 打印节点
        return payload, interrupted      # 返回中断内容和标志

    # ── Phase 1: empty input — first interrupt (trip details) ───────────────────

    print("Starting agent (first HITL = trip details)...\n")    # 开始第一个人工输入阶段

    payload, interrupted = await stream_until_interrupt(thread_id, {}, None)   # 初始空输入，等待第一次打断收集行程
    if not interrupted:            # 如果没有被中断（直接给出结果），直接输出最终行程
        await _print_final_agenda(client, thread_id)
        return

    print()
    print("─" * 55)        # 分隔线
    print("  Trip details (first interrupt)")   # 第一次打断说明
    print("─" * 55)
    print()
    print(f"  {payload}")  # 打印要补充的信息（目的地与时间）
    print()

    trip_reply = input("  Your answer: ").strip()     # 用户输入
    if not trip_reply:                                # 默认输入内容
        trip_reply = "Tokyo, Japan — June 10 through June 17, 2025"

    # ── Phase 2: resume → weather → second interrupt ────────────────────────────

    print()
    print("Resuming...\n")    # 恢复，进入第二阶段

    payload, interrupted = await stream_until_interrupt(
        thread_id, None, {"resume": trip_reply}
    )   # 用刚才的补充恢复对话
    if not interrupted:           # 如果没中断了，直接输出最终行程
        await _print_final_agenda(client, thread_id)
        return

    if _is_origin_followup_prompt(payload):    # 如果需要补出发地
        print()
        print("─" * 55)
        print("  Starting location (GeoIP could not infer)")
        print("─" * 55)
        print()
        print(f"  {payload}")              # 打印需要补充的出发地内容
        print()

        origin_reply = input("  City/region you're departing from: ").strip()  # 用户输入出发地
        if not origin_reply:
            origin_reply = "San Francisco, CA"    # 默认出发地

        print()
        print("Resuming...\n")

        payload, interrupted = await stream_until_interrupt(
            thread_id, None, {"resume": origin_reply}
        )      # 用出发地恢复对话
        if not interrupted:                 # 没中断直接结束
            await _print_final_agenda(client, thread_id)
            return

    print()
    print("─" * 55)
    print("  Preferences (interrupt)")
    print("─" * 55)
    print()
    print(f"  {payload}")              # 打印偏好问题
    print()

    pref_reply = input("  Your preferences: ").strip()    # 用户输入偏好
    if not pref_reply:
        pref_reply = "Mix of culture, local food, and some outdoor walks"  # 默认偏好

    # ── Phase 3: resume to completion ───────────────────────────────────────────

    print()
    print("Resuming...\n")      # 恢复执行到结束

    _, interrupted = await stream_until_interrupt(
        thread_id, None, {"resume": pref_reply}
    )
    if interrupted:
        print("  (Unexpected extra interrupt.)")    # 理论上不应再中断，若有说明流程异常

    await _print_final_agenda(client, thread_id)     # 打印最终行程单


async def _print_final_agenda(client, thread_id: str):
    state = await client.threads.get_state(thread_id)    # 获取当前线程状态
    values = state["values"]                             # 获取所有变量

    print()
    print("=" * 55)
    print("  Your Personalized Travel Agenda")           # 行程单标题
    print("=" * 55)
    print()
    print(values.get("agenda", "(no agenda generated)"))    # 打印生成的行程单
    print()
    print("─" * 55)
    print(f"  Preferences captured: {values.get('activity_preferences', 'N/A')}")   # 用户偏好
    print(f"  Thread ID (for resuming later): {thread_id}")                          # 线程ID供恢复
    print("─" * 55)


if __name__ == "__main__":
    asyncio.run(run())      # 程序入口，异步运行主函数
