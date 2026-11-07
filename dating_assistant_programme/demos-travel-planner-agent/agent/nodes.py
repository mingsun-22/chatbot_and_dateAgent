"""约会助手 LangGraph 的各个“节点函数”。

每个节点都是一个函数：`def 节点(state) -> dict`，
它读取当前状态（state），执行一小步工作（问用户、查天气、搜活动……），
然后返回一个字典，框架会把这个字典合并回整体状态，供后续节点使用。

其中带 `_hitl` 后缀的是 Human-In-The-Loop（人在环）节点：
它们通过 `interrupt(...)` 暂停整个图，把问题抛给前端用户，等用户回复后再继续。

本文件还包含一批下划线开头的私有辅助函数，负责关键词构造、文本解析、结果压缩等细节。
"""

from __future__ import annotations  # 允许使用 date | None 等现代类型注解

import json  # 将天气 casts 序列化为 JSON 字符串供 LLM 阅读
import re  # 正则解析时间段文本（如 14:00-18:00）
from datetime import date  # 解析 ISO 日期并计算星期
from typing import Any  # 通用类型，用于辅助函数返回值

from langgraph.types import interrupt  # LangGraph HITL 中断：暂停图并等待用户回复
from pydantic import BaseModel  # 定义 LLM 结构化输出的数据模型

from agent.clients import (  # 外部服务客户端
    llm,  # 大语言模型实例
    map_geocode_detail,  # 高德地理编码
    map_transit_route_summary,  # 高德公交路径规划
    map_weather_forecast,  # 高德天气预报
    search,  # Tavily 联网搜索
)  # 外部服务客户端导入结束
from agent.date_parser import current_date_context, resolve_date_text  # 日期解析工具
from agent.prompts import (  # 各场景的提示词模板
    activity_recommendations_prompt,  # 活动推荐 prompt 工厂
    budget_terms_prompt,  # 低预算判断 prompt
    date_details_prompt,  # 基本信息抽取 prompt
    date_plan_prompt,  # 最终方案整合 prompt
    departure_prompt,  # 出发地抽取 prompt
    restaurant_recommendations_prompt,  # 餐饮推荐 prompt
    weather_summary_prompt,  # 天气总结 prompt
)  # prompts 模块导入结束
from agent.state import DateState  # 图状态类型定义


# ===== 下面三个 Pydantic 模型用于 LLM 的“结构化输出” =====
# `llm.with_structured_output(模型)` 是 LangChain 能力：让模型按 Pydantic 字段返回对象，
# 而不是自由文本，省去手工 json.loads，字段缺失时也有默认值兜底。


class BudgetTermsOutput(BaseModel):  # LLM 结构化输出：是否低预算倾向
    """判断用户是否为低预算倾向的结构化输出。"""

    use_low_budget_terms: bool = False  # True 表示需要在搜索词中加入低预算关键词


class DateDetailsOutput(BaseModel):  # LLM 结构化输出：约会基本信息
    """从用户消息抽取的约会基本信息。"""

    date_area: str = ""  # 约会地点
    date_date: str = ""  # 日期（保留用户原始表达，如“下周六”）
    date_time_range: str = ""  # 时间段（24 小时制，如 14:00-18:00）


class DepartureOutput(BaseModel):  # LLM 结构化输出：出发地地址
    """从用户消息抽取的出发地地址。"""

    departure_address: str = ""  # 出发地完整地址


def _infer_budget_search_terms(text: str) -> str:  # 根据偏好推断低预算搜索关键词
    """根据用户偏好文本，判断是否需要在搜索时加入“低预算”关键词。

    返回一串低预算关键词（用于提升平价结果权重），若无低预算倾向则返回空串。
    """
    cleaned = (text or "").strip()  # 去除偏好文本首尾空白
    if not cleaned:  # 空文本无需判断
        return ""  # 无偏好则不加低预算词
    try:  # 调用 LLM 做结构化判断
        # 让模型只回答“是否低预算”，再据此决定加不加关键词
        data = llm.with_structured_output(BudgetTermsOutput).invoke(budget_terms_prompt(cleaned))  # 结构化调用
    except Exception:  # 模型或网络异常
        # 模型调用失败时不影响主流程，按“无低预算倾向”处理
        return ""  # 失败时返回空串
    return "性价比 不贵 平价 便宜 免费 低成本 人均不高" if data.use_low_budget_terms is True else ""  # 按判断结果返回关键词或空串


def _budget_search_terms(state: DateState) -> str:  # 从状态读取低预算搜索词
    """从状态里取出之前推断好的低预算关键词。"""
    return str(state.get("budget_search_terms") or "").strip()  # 读取并清理空白


def _parse_time_range_hours(value: str | None) -> tuple[int, int] | None:  # 解析 "HH:MM-HH:MM" 为小时元组
    """从 "14:00-18:00" 这类时间段文本里解析出 (开始小时, 结束小时)。

    解析失败或小时超出 0-23 时返回 None。
    """
    # 匹配形如 14:00-18:00 的时间段，中间的连接符兼容 - ~ — – 等多种写法
    match = re.search(r"(\d{1,2}):\d{2}\s*[-~—–]\s*(\d{1,2}):\d{2}", str(value or ""))  # 正则匹配时间段
    if not match:  # 未匹配到合法时间段格式
        return None  # 无法解析
    start_hour = int(match.group(1))  # 提取开始小时
    end_hour = int(match.group(2))  # 提取结束小时
    if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):  # 小时必须在 0-23 范围内
        return None  # 小时越界
    return start_hour, end_hour  # 返回 (开始小时, 结束小时) 元组


def _activity_search_terms(state: DateState) -> str:  # 生成活动类 Tavily 搜索词
    """根据约会时间段动态生成活动搜索关键词。

    如果约会会持续到晚上（结束时间 >= 18 点），额外补充夜景、酒吧等夜间关键词。
    """
    terms = ["影院", "密室逃脱", "展览", "脱口秀", "Livehouse", "咖啡", "散步", "拍照", "体验"]  # 基础活动关键词
    hours = _parse_time_range_hours(state.get("date_time_range"))  # 解析时间段
    if hours and hours[1] >= 18:  # 结束时间在 18 点及以后，补充夜间活动词
        terms.extend(["夜景", "夜游", "酒吧", "清吧", "江边", "湖边", "晚间"])  # 夜间关键词
    return " ".join(terms)  # 拼接为空格分隔的搜索词串


def _restaurant_search_terms(state: DateState) -> str:  # 生成餐饮类 Tavily 搜索词
    """根据约会时间段推断需要的餐饮类型（午餐/晚餐/下午茶）关键词。"""
    terms = ["餐厅", "咖啡", "甜品"]  # 基础餐饮关键词
    hours = _parse_time_range_hours(state.get("date_time_range"))  # 解析时间段
    if not hours:  # 时间段无法解析
        # 时间段无法解析时，退化为通用“约会”关键词
        terms.append("约会")  # 通用餐饮搜索词
        return " ".join(terms)  # 提前返回
    start_hour, end_hour = hours  # 解包开始/结束小时
    # 时间段与常见用餐时段有重叠时，补充对应关键词
    if start_hour < 14 and end_hour > 11:  # 覆盖午餐时段（约 11:00-14:00）
        terms.append("午餐")  # 午餐关键词
    if start_hour < 21 and end_hour > 17:  # 覆盖晚餐时段（约 17:00-21:00）
        terms.append("晚餐")  # 晚餐关键词
    if start_hour < 17 and end_hour > 13:  # 覆盖下午茶时段（约 13:00-17:00）
        terms.extend(["下午茶", "咖啡", "甜品"])  # 下午茶相关词
    return " ".join(dict.fromkeys(terms))  # dict.fromkeys 去重且保持顺序


def _date_weekday_label(value: str | None) -> str:  # ISO 日期 → 中文星期
    """把 ISO 日期字符串转成中文星期，解析失败返回空串。"""
    if not value:  # 空值直接返回
        return ""  # 无日期则无星期
    try:  # 尝试解析 ISO 日期
        parsed = date.fromisoformat(str(value).strip())  # 解析 ISO 日期
    except ValueError:  # 格式不合法
        return ""  # 解析失败
    return ("周一", "周二", "周三", "周四", "周五", "周六", "周日")[parsed.weekday()]  # weekday() 0=周一


def _compact_search_results(results: dict[str, Any], max_results: int = 4, max_content_chars: int = 800) -> str:  # 压缩 Tavily 结果供 LLM 阅读
    """把 Tavily 搜索结果压缩成简短文本，交给 LLM 进一步整理。

    TavilySearch.invoke 的典型返回：

        {
            "query": "杭州西湖区 约会 餐厅",
            "results": [
                {"title": "...", "url": "...", "content": "网页摘要", "score": 0.92}
            ]
        }

    这里只保留 title、url、content 三个字段，并对正文做长度截断，避免提示词过长。
    """
    lines: list[str] = []  # 存放每条搜索结果的格式化文本
    for index, row in enumerate((results.get("results") or [])[:max_results], 1):  # 遍历前 N 条结果
        title = str(row.get("title") or "").strip()  # 网页标题
        url = str(row.get("url") or "").strip()  # 网页链接
        content = re.sub(r"\s+", " ", str(row.get("content") or "")).strip()  # 压缩连续空白
        if len(content) > max_content_chars:  # 正文过长则截断
            content = content[:max_content_chars].rstrip() + "..."  # 截断并加省略号
        lines.append(f"{index}. 标题：{title}\nURL：{url}\n摘要：{content}")  # 格式化单条结果
    return "\n\n".join(lines)  # 用空行连接所有结果


def _date_area_fields(area: str) -> dict[str, Any] | None:  # 约会地点地理编码，失败返回 None
    """对约会地点做地理编码，返回规范化地址和目的地坐标等字段。

    地理编码失败（查不到经纬度）时返回 None，由上层追问用户重填。
    """
    detail = map_geocode_detail(area)  # 调用高德地理编码
    if not detail:  # 编码失败
        return None  # 高德查不到该地址
    formatted_address = str(detail.get("formatted_address") or "").strip()  # 规范化地址
    if not formatted_address:  # 地址为空则失败
        return None  # 无有效 formatted_address
    return {  # 返回写入状态的地理信息字段
        "date_area": formatted_address,  # 规范化后的约会地点
        "destination_lat": float(detail["lat"]),  # 目的地纬度
        "destination_lon": float(detail["lon"]),  # 目的地经度
        "destination_city": str(detail.get("city") or detail.get("province") or "").strip(),  # 城市名
        "destination_adcode": str(detail.get("adcode") or "").strip(),  # 行政区编码
    }  # 地理编码字段字典


def  _parse_date_details_from_text(text: str) -> dict[str, Any]:  # 用户一句话 → 结构化约会信息
    """把用户的一句话解析成结构化约会信息，并补全地理编码与标准日期。

    流程：LLM 抽取地点/日期/时间段 → 地点做地理编码 → 日期做标准化。
    任一步失败都抛出带提示语的 ValueError，让 HITL 节点据此追问用户。
    """
    cleaned = (text or "").strip()  # 清理用户输入
    if not cleaned:  # 空输入则提示必填信息
        raise ValueError('请提供约会地点、日期、以及 24 小时制的约会时间段。')  # 必填项缺失
    today_date, weekday = current_date_context()  # 获取当前中国日期和星期，供 LLM 理解相对日期
    prompt = date_details_prompt(text=cleaned, today=today_date.isoformat(), weekday=weekday)  # 构造抽取 prompt
    data = llm.with_structured_output(DateDetailsOutput).invoke(prompt)  # LLM 结构化抽取
    date_area = data.date_area.strip()  # 抽取的约会地点
    raw_date = data.date_date.strip()  # 抽取的原始日期表达
    range_time = data.date_time_range.strip()  # 抽取的时间段
    if not raw_date or not range_time or not date_area:  # 任一必填字段缺失
        raise ValueError('没有识别到约会地点、日期或时间段，请重新说明。')  # 抽取不完整
    area_geo = _date_area_fields(date_area)  # 对地点做地理编码
    if not area_geo:  # 编码失败
        raise ValueError('这个约会地点暂时无法通过高德地图查到经纬度，请写清楚城市 + 区/商圈/地标。')  # 地理编码失败
    date_date = resolve_date_text(raw_date)  # 把“下周六”等相对日期解析为 ISO 日期
    return {  # 合并地理编码结果与日期/时间段
        **area_geo,  # 展开地理编码字段
        "date_date": date_date,  # 标准 ISO 日期
        "date_time_range": range_time,  # 24 小时制时间段
    }  # 解析成功，供 HITL 节点写回状态


def _parse_departure_from_text(text: str) -> str:  # LLM 抽取出发地地址字符串
    """用 LLM 从用户消息中抽取出发地地址字符串，失败返回空串。"""
    cleaned = (text or "").strip()  # 清理用户输入
    if not cleaned:  # 空输入
        return ""  # 无出发地可抽
    try:  # 调用 LLM 结构化抽取
        data = llm.with_structured_output(DepartureOutput).invoke(departure_prompt(cleaned))  # LLM 抽取出发地
        return data.departure_address.strip()  # 返回抽取到的地址
    except Exception:  # 模型调用失败
        return ""  # 失败时返回空串


def _resolve_departure_with_map(text: str) -> dict[str, Any] | None:  # 出发地地理编码
    """对出发地地址做地理编码，返回规范化地址和出发地坐标，失败返回 None。"""
    detail = map_geocode_detail(text)  # 调用高德地理编码
    if not detail:  # 编码失败
        return None  # 查不到经纬度
    formatted_address = str(detail.get("formatted_address") or "").strip()  # 规范化地址
    if not formatted_address:  # 地址为空
        return None  # 无有效地址
    return {  # 返回写入状态的出发地信息
        "departure_address": formatted_address,  # 规范化出发地地址
        "user_lat": float(detail["lat"]),  # 出发地纬度
        "user_lon": float(detail["lon"]),  # 出发地经度
    }  # 出发地坐标字段


def collect_date_details_hitl(state: DateState) -> dict[str, Any]:  # HITL：收集约会基本信息
    """【HITL 节点】收集约会基本信息（地点、日期、时间段）。

    通过 interrupt 向用户提问；若解析失败则带着错误提示循环追问，直到拿到有效信息。
    """
    prompt = (  # 首次向用户展示的引导语（多行字符串，内容即提问文案）
        '先告诉我这次约会的基本信息：\n\n'  # 开场白
        '- 约会地点，请写清楚城市 + 区/商圈/地标\n'  # 地点要求
        '- 约会日期\n'  # 日期要求
        '- 约会时间段，请用 24 小时制表示\n\n'  # 时间段要求
        '示例：6月18日在杭州西湖区湖滨约会，14:00-18:00。'  # 填写示例
    )  # 引导语组装完成
    while True:  # 解析失败则循环追问，直到成功
        # ── 断点⑥（核心）：interrupt() 在此处暂停整个图 ──
        # 执行到这一行时，LangGraph 会：
        #   1. 把 prompt 打包进 Interrupt 对象，写入当前 chunk（体现为 __interrupt__ 键）；
        #   2. 将图的完整状态持久化到 checkpointer（这里是 MemorySaver）；
        #   3. 抛出内部异常让 graph.stream 的迭代提前结束（本轮流结束）。
        # 此行之后的代码【暂时不会执行】，直到下次 graph.stream(Command(resume=...), ...)
        # 才会从这里恢复，并把用户回答作为 interrupt() 的返回值赋给 user_reply。
        user_reply = interrupt(prompt)  # 暂停图，等待用户回复
        # ── 断点⑦：图从此处恢复（即 Command(resume=answer) 触发后的第一行） ──
        # user_reply 的值就是 Command(resume=answer) 里的 answer 字符串。
        try:  # 尝试解析用户回复
            return _parse_date_details_from_text(str(user_reply))  # 解析成功则返回状态更新字典
        except ValueError as exc:  # 解析失败，构造下一轮追问提示
            prompt = (  # 带错误信息的追问文案
                f"{exc}\n\n"  # 上一轮错误原因
                '请重新说明约会地点、日期和 24 小时制时间段。'  # 重填指引
                '日期可以写具体日期，也可以写今天、明天、后天、这周六等相对日期。'  # 日期格式提示
            )  # 追问 prompt 更新完毕


def confirm_departure_hitl(state: DateState) -> dict[str, Any]:  # HITL：确认出发地
    """【HITL 节点】确认用户真实出发地，用于后续公交路线规划。

    循环追问，直到能抽取出地址并成功地理编码为止。
    """
    prompt = (  # 首次向用户展示的出发地引导语
        '为了安排公共交通路线，请告诉我你的真实出发地。\n'  # 说明用途
        '请写清楚城市 + 区/街道/地标，例如：杭州西湖区文三路。'  # 格式要求
    )  # 引导语组装完成

    while True:  # 抽取或编码失败则循环追问
        # ── 断点⑧：第二个 HITL 节点的 interrupt ──
        # 与断点⑥同理：暂停图、持久化状态、等待 Command(resume=...)。
        # 恢复后 reply 拿到用户输入的出发地字符串。
        reply = str(interrupt(prompt)).strip()  # 暂停图，获取用户回复
        extracted = _parse_departure_from_text(reply)  # LLM 抽取出发地地址
        if not extracted:  # 未抽取到有效地址
            prompt = (  # 更新追问提示
                '没有识别到明确的出发地，请重新输入你的真实出发地。\n'  # 抽取失败说明
                '请写清楚城市 + 区/街道/地标，例如：杭州西湖区文三路。'  # 格式要求
            )  # 追问 prompt 更新
            continue  # 进入下一轮 while
        resolved_departure = _resolve_departure_with_map(extracted)  # 对出发地做地理编码
        if resolved_departure:  # 编码成功
            return resolved_departure  # 返回出发地地址和坐标
        # 抽到了地址但查不到经纬度，追问更明确的地址
        prompt = (  # 地理编码失败时的追问文案
            '这个出发地暂时无法通过高德地图查到经纬度，请重新输入更明确的出发地。\n'  # 失败原因
            '请写清楚城市 + 区/街道/地标，例如：杭州西湖区文三路。'  # 格式要求
        )  # 追问 prompt 更新


def research_weather(state: DateState) -> dict[str, Any]:  # 查天气并生成穿搭建议
    """查询目标日期天气并生成穿搭建议。

    用目的地行政区编码/城市查高德天气预报，再匹配约会日期那一天的数据交给 LLM 总结。
    查不到时返回兜底提示，保证方案仍能继续生成。
    """
    area = state["date_area"]  # 约会地点（已规范化）
    target_date = state["date_date"]  # 约会日期（ISO 格式）
    city_or_adcode = str(state.get("destination_adcode") or state.get("destination_city") or "").strip()  # 优先 adcode
    weather = map_weather_forecast(city_or_adcode) if city_or_adcode else None  # 调用高德天气 API
    if not weather:  # 天气查询失败
        return {"weather_summary": "暂时无法获取天气预报，请在出发前再次核实天气，并准备一个室内备选地点。"}  # 兜底文案

    matched_cast = next(  # 从 casts 列表中找出约会当天的预报
        (cast for cast in weather.get("casts") or [] if str(cast.get("date") or "").strip() == target_date),  # 按 date 匹配
        None,  # 找不到则用 None
    )  # next 调用结束
    if not matched_cast:  # 目标日期超出预报范围
        return {"weather_summary": "目标日期暂时超出天气预报范围，请在临近约会时再次核实天气，并准备保守穿搭和室内备选。"}  # 兜底文案

    weather_context = json.dumps(matched_cast, ensure_ascii=False)  # 将当天天气数据序列化为 JSON
    summary = llm.invoke(weather_summary_prompt(area=area, target_date=target_date, weather_context=weather_context))  # LLM 总结
    return {"weather_summary": summary.content}  # 写入天气与穿搭建议


def ask_preferences(state: DateState) -> dict[str, Any]:  # HITL：询问约会偏好
    """【HITL 节点】询问约会偏好，并据此推断低预算搜索关键词。"""
    # ── 断点⑨：第三个 HITL 节点的 interrupt ──
    # 此节点在 confirm_departure_hitl 之后触发，同样会暂停图等待用户回复偏好。
    # 恢复后 reply 拿到用户描述偏好的字符串，交给 _infer_budget_search_terms 判断预算倾向。
    reply = interrupt(  # 暂停图，向用户询问偏好
        '说说你们这次约会的偏好，我会按这些来安排。\n\n'  # 开场白
        '可以包括：氛围（安静/热闹/有仪式感）、预算、餐饮偏好、活动强度、'  # 偏好维度示例
        '是否想拍照、是否需要私密一点、对方忌口或雷区。'  # 更多偏好示例
    )  # interrupt 返回用户回复
    text = str(reply).strip()  # 用户偏好原文
    terms = _infer_budget_search_terms(text)  # 推断是否需要低预算搜索词
    return {  # 写入偏好和低预算关键词
        "date_preferences": text,  # 用户偏好原文
        "budget_search_terms": terms,  # 低预算搜索词（可能为空）
    }  # 状态更新片段


def summarize_transport_options(state: DateState) -> dict[str, Any]:  # 总结公共交通建议
    """总结从出发地到约会地点的公共交通建议。

    用出发地/目的地坐标调用高德公交路径规划，拼成一句提示；查不到时给出兜底文案。
    """
    dest = state["date_area"]  # 约会地点
    departure = state["departure_address"]  # 出发地地址
    transit_summary = map_transit_route_summary(  # 调用高德公交路径规划
        (float(state["user_lat"]), float(state["user_lon"])),  # 出发地坐标 (lat, lon)
        (float(state["destination_lat"]), float(state["destination_lon"])),  # 目的地坐标
        city=str(state.get("destination_city") or dest).strip(),  # 所在城市
        date_value=state.get("date_date"),  # 约会日期（可选）
    )  # 公交摘要查询结束
    fallback = f"从{departure}到{dest}的公共交通路线需出发前用高德地图核实"  # 查不到路线时的兜底文案
    return {"travel_leg_summary": f"公共交通：{transit_summary or fallback}。提醒：预留进出站和步行时间。"}  # 写入交通建议


def _research_recommendations(  # 活动/餐饮推荐的通用实现
        state: DateState,  # 当前图状态
        *,  # 以下参数必须用关键字传入
        query_terms: str,  # 搜索关键词（活动或餐饮）
        prompt_factory: Any,  # 对应的 prompt 工厂函数
        output_key: str,  # 写回状态的结果字段名
        found_key: str,  # 写回状态的“是否搜到”标志字段名
        include_weather: bool = False,  # 是否把天气摘要一并传入 prompt
) -> dict[str, Any]:  # 返回要合并进状态的字典
    """活动/餐饮推荐的通用实现：搜索 → 压缩结果 → LLM 整理。

    参数:
        query_terms: 该类别（活动或餐饮）的搜索关键词。
        prompt_factory: 生成对应提示词的函数（活动或餐饮）。
        output_key: 写回状态的结果字段名。
        found_key: 写回状态的“是否搜到候选”标志字段名。
        include_weather: 是否把天气总结一并喂给提示词（活动需要，餐饮不需要）。
    """
    query = (  # 拼接 Tavily 搜索查询：地点 + 约会 + 类别词 + 偏好 + 预算词 + 日期
        f"{state['date_area']} 约会 {query_terms} "  # 地点与类别词
        f"{state.get('date_preferences', '')} {_budget_search_terms(state)} {state.get('date_date', '')}"  # 偏好/预算/日期
    )  # 搜索词组装完成
    results = search.invoke(query)  # 调用 Tavily 联网搜索
    search_found = bool((results or {}).get("results"))  # 判断是否搜到结果
    compact_results = _compact_search_results(results)  # 压缩搜索结果供 LLM 阅读
    if not search_found:  # 未搜到任何候选
        return {  # 写入失败标志和兜底文案
            output_key: "未搜索到明确候选。",  # 兜底推荐文本
            found_key: False,  # 标记搜索失败
        }  # 提前返回
    prompt_kwargs = dict(  # 构造提示词参数字典
        area=state["date_area"],  # 约会地点
        date_value=state.get("date_date"),  # 约会日期
        preferences=state.get("date_preferences"),  # 用户偏好
        search_results=compact_results,  # 压缩后的搜索结果
    )  # prompt 参数字典
    if include_weather:  # 活动推荐需要结合天气
        prompt_kwargs["weather_summary"] = state.get("weather_summary")  # 注入天气摘要
    msg = llm.invoke(prompt_factory(**prompt_kwargs))  # 调用 LLM 整理候选列表
    return {  # 写入推荐文本和成功标志
        output_key: msg.content,  # LLM 生成的推荐正文
        found_key: True,  # 标记搜索成功
    }  # 状态更新片段


def research_activities(state: DateState) -> dict[str, Any]:  # 搜索并整理活动候选
    """查询适合约会的活动候选（结合天气选择室内/室外）。"""
    return _research_recommendations(  # 复用通用搜索+整理逻辑
        state,  # 传入当前状态
        query_terms=_activity_search_terms(state),  # 动态生成活动搜索词
        prompt_factory=activity_recommendations_prompt,  # 活动推荐 prompt
        output_key="activity_recommendations",  # 写入状态的字段名
        found_key="activity_search_found",  # 是否搜到的标志字段名
        include_weather=True,  # 活动推荐需要参考天气
    )  # 返回状态更新片段


def research_restaurants(state: DateState) -> dict[str, Any]:  # 搜索并整理餐饮候选
    """查询适合约会的餐饮候选。"""
    return _research_recommendations(  # 复用通用搜索+整理逻辑
        state,  # 传入当前状态
        query_terms=_restaurant_search_terms(state),  # 动态生成餐饮搜索词
        prompt_factory=restaurant_recommendations_prompt,  # 餐饮推荐 prompt
        output_key="restaurant_recommendations",  # 写入状态的字段名
        found_key="restaurant_search_found",  # 是否搜到的标志字段名
    )  # 返回状态更新片段（餐饮不需要天气）


def assemble_date_plan(state: DateState) -> dict[str, Any]:  # 整合所有信息生成最终方案
    """整合所有信息，生成最终可执行的约会方案（agenda）。

    若活动和餐饮都没搜到候选，则不硬编方案，而是给出重试建议。
    """
    if state.get("activity_search_found") is False and state.get("restaurant_search_found") is False:  # 两路都失败
        return {  # 返回兜底提示，不调用 LLM 硬编方案
            "agenda": (  # 最终方案字段
                "暂时没有搜索到足够明确的活动和餐饮候选，无法生成可靠的约会行程。"  # 失败说明
                "建议换一个更具体的商圈/地标，或稍后重新搜索后再生成方案。"  # 重试建议
            )  # 兜底 agenda 文案
        }  # 提前返回
    weekday = _date_weekday_label(state.get("date_date"))  # 解析约会日期对应的中文星期几
    date_value = str(state.get("date_date") or "")  # 约会日期字符串
    date_line = f"{date_value} {weekday}".strip()  # 拼接“日期 星期”展示行，如 "2026-06-18 周四"
    prompt = date_plan_prompt(  # 构造最终方案整合 prompt
        area=state["date_area"],  # 约会地点
        date_line=date_line,  # 日期+星期展示行
        time_range=state.get("date_time_range"),  # 约会时间段
        departure=state.get("departure_address"),  # 出发地
        weather_summary=state.get("weather_summary"),  # 天气与穿搭
        travel_summary=state.get("travel_leg_summary"),  # 交通建议
        preferences=state.get("date_preferences"),  # 用户偏好
        activity_recommendations=state.get("activity_recommendations"),  # 活动候选
        restaurant_recommendations=state.get("restaurant_recommendations"),  # 餐饮候选
        weekday=weekday,  # 中文星期
    )  # prompt 构造完成
    result = llm.invoke(prompt)  # 调用 LLM 生成最终约会方案
    return {"agenda": result.content}  # 写入最终方案文本
