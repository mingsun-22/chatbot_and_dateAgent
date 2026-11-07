"""约会助手的 LangGraph 图装配。

本文件把 nodes.py 里的各个节点函数，按业务顺序连成一张有向图（状态机）：
- 先串行收集基本信息、确认出发地；
- 再并行执行“查天气 / 规划交通 / 问偏好”，进一步并行“搜活动 / 搜餐饮”；
- 最后汇聚到一个节点，整合生成完整约会方案。

并行分支能缩短总时长；LangGraph 会在每个“超级步”把并行节点返回的字段合并进同一个状态。
"""

from __future__ import annotations  # 允许类型别名等前向引用

from collections.abc import Callable  # Callable 用于描述“接收状态、返回字典”的节点函数签名
from typing import Any, TypeAlias, cast  # Any 绕过严格类型检查；TypeAlias 定义别名；cast 做类型断言

from langgraph.graph import END, START, StateGraph  # LangGraph 图构建器及起点/终点常量

from agent.nodes import (  # 导入各业务节点函数
    ask_preferences,  # HITL：询问用户偏好
    assemble_date_plan,  # 整合所有信息生成最终方案
    collect_date_details_hitl,  # HITL：收集地点/日期/时间段
    confirm_departure_hitl,  # HITL：确认出发地
    research_activities,  # 搜索并整理活动候选
    research_restaurants,  # 搜索并整理餐饮候选
    research_weather,  # 查天气并生成穿搭建议
    summarize_transport_options,  # 规划公共交通路线
)  # 从 nodes 模块导入的全部节点函数
from agent.state import DateInputState, DateOutputState, DateState  # 三种状态 schema

# 节点函数的类型别名：接收 DateState、返回要合并进状态的字段字典
DateNode: TypeAlias = Callable[[DateState], dict[str, Any]]  # 节点函数统一签名：读状态、返回更新片段
# cast 到 Any 是为了绕开 StateGraph 对 TypedDict schema 的静态类型检查兼容性问题
date_state_schema: Any = DateState  # 图内部流转使用的完整状态类型
date_input_schema: Any = DateInputState  # 图入口允许传入的字段类型
date_output_schema: Any = DateOutputState  # 图结束后对外暴露的字段类型

# 创建图构建器，分别声明“内部完整状态 / 输入状态 / 输出状态”三种 schema
builder = StateGraph(  # 创建 LangGraph 图构建器
    date_state_schema,  # 节点之间共享的完整状态结构
    input_schema=date_input_schema,  # 调用 graph.invoke 时可传入的字段
    output_schema=date_output_schema,  # 调用结束后返回给调用方的字段
)  # StateGraph 构造完成，后续 add_node / add_edge


def add_date_node(name: str, node: DateNode) -> None:  # 封装 add_node，统一做类型 cast
    """把一个节点函数以指定名字注册到图里（封装 cast 以消除类型告警）。"""
    builder.add_node(name, cast(Any, node))  # cast 消除 LangGraph 对节点签名的类型告警


# ===== 注册所有节点（名字即图中的节点 ID）=====
add_date_node("collect_date_details_hitl", collect_date_details_hitl)  # 收集基本信息（HITL）
add_date_node("confirm_departure_hitl", confirm_departure_hitl)  # 确认出发地（HITL）
add_date_node("research_weather", research_weather)  # 查天气
add_date_node("ask_preferences", ask_preferences)  # 问偏好（HITL）
add_date_node("summarize_transport_options", summarize_transport_options)  # 规划交通
add_date_node("research_activities", research_activities)  # 搜活动
add_date_node("research_restaurants", research_restaurants)  # 搜餐饮
add_date_node("assemble_date_plan", assemble_date_plan)  # 整合方案

# ===== 连接节点，定义执行顺序（边）=====
# 重要原则：三个需要向用户提问的 HITL 节点（收集信息 / 确认出发地 / 问偏好）
# 必须“串行”排在最前面，绝不能放进并行分支里。
#
# 为什么？带 interrupt 的节点若和其它节点并行，LangGraph 在恢复时会“重跑整个并行超级步”：
# 这会导致 ① 偏好还没问，天气/交通就先跑了、提前生成半张方案卡片；
#          ② 回答偏好后天气/交通被重复执行，浪费调用且时序混乱（即本次 bug 的表现）。
# 把三个提问节点串成一条直线后，并行部分就不含任何 interrupt，恢复行为变得确定、干净。

# 起点 → 收集基本信息 → 确认出发地 → 询问偏好（三个提问节点严格串行）
builder.add_edge(START, "collect_date_details_hitl")  # 图从 START 进入第一个 HITL 节点
builder.add_edge("collect_date_details_hitl", "confirm_departure_hitl")  # 基本信息收集完再确认出发地
builder.add_edge("confirm_departure_hitl", "ask_preferences")  # 出发地确认完再询问偏好

# 偏好收集完毕后，才扇出为并行分支：查天气 / 规划交通 / 搜餐饮（均为纯计算，无提问）
builder.add_edge("ask_preferences", "research_weather")  # 偏好就绪后并行查天气
builder.add_edge("ask_preferences", "summarize_transport_options")  # 偏好就绪后并行规划交通
builder.add_edge("ask_preferences", "research_restaurants")  # 偏好就绪后并行搜餐饮

# 搜活动需要结合天气（室内/室外）选择，因此等天气就绪后再跑；偏好此时已在状态中
builder.add_edge("research_weather", "research_activities")  # 天气结果写入状态后再搜活动

# 交通、活动、餐饮三路结果汇聚，进入最终整合节点（LangGraph 会等待所有入边完成）
builder.add_edge(  # 多入边汇聚：LangGraph 会等待所有前置节点完成
    [  # 三个并行分支的节点 ID 列表
        "summarize_transport_options",  # 交通分支
        "research_activities",  # 活动分支
        "research_restaurants",  # 餐饮分支
    ],  # 入边列表结束
    "assemble_date_plan",  # 三路汇聚到整合节点
)  # 汇聚边注册完成
# 整合完成即到达终点
builder.add_edge("assemble_date_plan", END)  # 最终方案生成后图结束

# 编译出可直接运行的图（API 层会用带 checkpointer 的方式再编译一次以支持中断/恢复）
graph = builder.compile()  # compile() 返回可调用的 CompiledGraph 对象
