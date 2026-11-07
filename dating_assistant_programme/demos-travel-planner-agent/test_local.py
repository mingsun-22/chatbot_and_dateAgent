"""
本地测试脚本。

使用内存 checkpointer 直接运行约会助手图，便于在不启动 FastAPI 的情况下
检查 streaming、interrupt 和 Command(resume=...) 流程。

用法：
    pip install -r requirements.txt
    cp .env.example .env   # 填入真实 key
    python test_local.py
"""

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

load_dotenv()

from agent.graph import builder


DEFAULT_REPLIES = [
    "明天下午14点到深圳龙岗麟恒约会，想吃饭和散步",
    "我从大芬地铁站出发",
    "喜欢安静，预算200",
    "满意",
]


def run() -> None:
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "date-assistant-local-test-1"}}

    print("=" * 60)
    print("  约会助手 Agent 本地测试")
    print("=" * 60)
    print()

    # 首次运行传空字典 {}，表示"全新对话，尚无用户输入"。
    # 每次 interrupt 之后，resume_input 会换成 Command(resume=...) 再进入下一轮循环。
    resume_input = {}
    interrupt_count = 0

    while True:
        # ── 断点①：进入 stream_until_interrupt，观察每轮传入的 resume_input 是 {} 还是 Command ──
        payload, interrupted = stream_until_interrupt(graph, config, resume_input)
        if not interrupted:
            # 图正常跑完（未触发任何新的 interrupt），退出循环。
            break

        print()
        print("-" * 60)
        print("助手提问：")
        # payload 就是 interrupt(prompt) 里传的字符串，即节点向用户提的问题。
        print(payload)
        print()

        default = DEFAULT_REPLIES[min(interrupt_count, len(DEFAULT_REPLIES) - 1)]
        # answer = input(f"你的回答（回车使用默认：{default}）：").strip() or default
        print(f'用户回答{default}')
        answer = default #纯自动化测试
        # ── 断点②：观察 Command 对象的结构 ──
        # Command(resume=answer) 是 LangGraph 的"恢复指令"；
        # 下一轮 graph.stream(Command(resume=...), ...) 会从上次 interrupt 处继续执行，
        # 并把 answer 作为 interrupt() 调用的返回值交给节点函数。
        resume_input = Command(resume=answer)
        interrupt_count += 1

    final_state = graph.get_state(config).values
    print_final_state(final_state)


def stream_until_interrupt(graph, config: dict, inp):
    # ── 断点③：stream_mode="updates" 表示每个节点执行完后产出一个 chunk（增量更新块）。
    # inp 是 {} 或 Command(resume=...)，LangGraph 据此判断是新运行还是从中断处恢复。
    for chunk in graph.stream(inp, config=config, stream_mode="updates"):
        # ── 断点④：检查 chunk 是否包含 __interrupt__ 键 ──
        # 当节点调用 interrupt(prompt) 时，LangGraph 会暂停图并在 chunk 里写入：
        #   {"__interrupt__": [Interrupt(value=prompt, ...)]} interrupt_id 是 这一次中断（Interrupt）的唯一标识符（Unique ID），作用是恢复（resume）时告诉 LangGraph："我要恢复的是哪一个 interrupt。"
        # 此时图已保存到 checkpointer，等待下次 Command(resume=...) 才会继续。
        if "__interrupt__" in chunk:
            # ── 断点⑤：展开 chunk["__interrupt__"] 看 Interrupt 对象的完整内容 ──
            # [0].value 就是节点传给 interrupt() 的那个字符串（即要问用户的问题）。
            return chunk["__interrupt__"][0].value, True
        node_name = next(iter(chunk.keys()))
        print(f"  + {node_name}")
    return None, False


def print_final_state(state: dict) -> None:
    print()
    print("=" * 60)
    print("  最终约会方案")
    print("=" * 60)
    print()
    print(state.get("agenda", "(没有生成约会方案)"))
    print()
    print("-" * 60)
    print(f"天气摘要：{state.get('weather_summary', '')[:160]}")
    print(f"出行建议：{state.get('travel_leg_summary', '')[:160]}")
    print(f"结束语：{state.get('final_message', '')}")
    print("-" * 60)


if __name__ == "__main__":
    run()
