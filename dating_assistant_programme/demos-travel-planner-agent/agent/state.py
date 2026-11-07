"""约会助手 LangGraph 的状态定义。

LangGraph 用一个“状态字典”在各节点之间传递数据：每个节点读取需要的字段、返回要更新的字段，
框架自动把返回值合并进整体状态。这里用 TypedDict 描述状态结构，方便类型检查和阅读。

三种 schema 的分工（对应 graph.py 里 StateGraph 的三个参数）：
- DateInputState：图入口允许接收的字段（本项目几乎为空，信息靠对话收集）；
- DateState：节点之间流转的完整内部状态；
- DateOutputState：图结束后对外暴露的字段（这里只暴露 agenda）。

- `total=False` 表示所有字段都是可选的（不要求一开始就全部存在）。
- `NotRequired[...]` 进一步强调该键可能不存在，读取时要用 `state.get(...)`。
"""

from __future__ import annotations  # 启用延迟注解，允许类型提示引用尚未定义的类名

from typing import NotRequired, TypedDict  # NotRequired 标记可选键；TypedDict 定义字典结构的类型


class DateInputState(TypedDict, total=False):  # 图入口状态：新会话无需预填字段
    """图的输入状态。

    新会话不需要携带任何初始字段，核心信息（地点/日期/时间等）都通过对话逐步收集，
    所以这里保持为空。
    """

    pass  # 占位：表示输入状态当前没有任何预定义字段


class DateState(TypedDict, total=False):  # 图内部完整状态：节点间共享的全部字段
    """约会助手的完整内部状态，贯穿所有节点。

    字段大致分为四类：用户填写的基本信息、地理编码坐标、用户偏好、以及各节点产出的结果文本。
    """

    # ===== 用户提供的约会基本信息 =====
    date_area: str  # 约会地点（规范化后的地址）
    date_date: str  # 约会日期（ISO 格式，如 2026-06-18）
    date_time_range: str  # 约会时间段（24 小时制，如 14:00-18:00）

    # ===== 地理编码得到的坐标信息 =====
    departure_address: str  # 出发地地址
    user_lat: NotRequired[float]  # 出发地纬度（地理编码后才有）
    user_lon: NotRequired[float]  # 出发地经度（地理编码后才有）
    destination_lat: NotRequired[float]  # 约会地点纬度
    destination_lon: NotRequired[float]  # 约会地点经度
    destination_city: NotRequired[str]  # 约会地点所在城市（查天气/公交用）
    destination_adcode: NotRequired[str]  # 约会地点行政区编码（查天气用，比城市名更精确）

    # ===== 用户偏好与搜索关键词 =====
    date_preferences: NotRequired[str]  # 用户描述的约会偏好（氛围、预算、忌口等）
    budget_search_terms: NotRequired[str]  # 根据偏好推断出的低预算搜索关键词

    # ===== 各节点产出的结果 =====
    weather_summary: NotRequired[str]  # 天气与穿搭建议（research_weather 节点写入）
    travel_leg_summary: NotRequired[str]  # 公共交通建议（summarize_transport_options 节点写入）
    activity_recommendations: NotRequired[str]  # 活动候选列表（research_activities 节点写入）
    restaurant_recommendations: NotRequired[str]  # 餐饮候选列表（research_restaurants 节点写入）
    activity_search_found: NotRequired[bool]  # 活动搜索是否找到有效候选（供最终整合节点判断）
    restaurant_search_found: NotRequired[bool]  # 餐饮搜索是否找到有效候选
    agenda: NotRequired[str]  # 最终整合的约会方案（assemble_date_plan 节点写入）


class DateOutputState(TypedDict, total=False):  # 图输出状态：对外只暴露 agenda
    """图的输出状态：对外只暴露最终方案文本。"""

    agenda: str  # 最终约会方案正文，API 层读取此字段返回给前端
