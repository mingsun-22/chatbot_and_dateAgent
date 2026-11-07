"""外部服务客户端封装模块。

约会助手需要调用两类外部能力：
1. Tavily 联网搜索——找活动/餐饮候选；
2. 高德地图 API——地理编码（地址→经纬度）、天气预报、公交路径规划。

本模块把这些 HTTP 调用封装成简单函数，统一做好超时控制和异常兜底：
任何网络/解析错误都返回 None 或空字符串，而不是抛异常中断整个图的运行。
"""

from __future__ import annotations  # 允许使用 dict[str, Any] | None 等现代类型注解

from typing import Any  # 通用字典值类型

import httpx  # 轻量 HTTP 客户端，用于调用高德 REST API
from langchain_tavily import TavilySearch  # LangChain 封装的 Tavily 联网搜索工具

from core.llm import create_llm  # 项目内 LLM 工厂函数
from core.settings import settings  # 全局配置（API Key、超时等）


# 高德地图三个接口地址：地理编码、公交路径规划、天气预报。
AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"  # 地址 → 经纬度
AMAP_TRANSIT_URL = "https://restapi.amap.com/v3/direction/transit/integrated"  # 公交路径规划
AMAP_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"  # 天气预报

# 模块级共享实例：搜索工具（最多返回 4 条）和大模型客户端，避免每次调用都重建。
# TavilySearch 是 LangChain 工具：`.invoke("查询词")` → 返回含 results 列表的 dict。
# nodes 里活动/餐饮节点会把它的结果压缩后塞进 prompt 再交给 llm 整理。
search = TavilySearch(max_results=4)  # 创建 Tavily 搜索实例，单次最多 4 条结果
llm = create_llm()  # 创建共享 LLM 客户端，供 nodes 调用


def map_geocode_detail(query: str) -> dict[str, Any] | None:  # 地址 → 经纬度等归一化地理信息
    """
    高德地理编码接口典型原始返回：

    {
        "status": "1",
        "info": "OK",
        "count": "1",
        "geocodes": [
            {
                "formatted_address": "浙江省杭州市西湖区文三路",
                "country": "中国",
                "province": "浙江省",
                "city": "杭州市",
                "district": "西湖区",
                "adcode": "330106",
                "location": "120.130260,30.274084",
                "level": "道路"
            }
        ]
    }

    本方法会把高德的经纬度字符串拆成 lat/lon，并只返回后续节点需要的归一化字段。
    """
    q = (query or "").strip()  # 去除输入地址字符串首尾空白
    if not q or not settings.amap_api_key:  # 如果地址或高德 API KEY 缺失，则返回 None
        return None  # 缺少必要参数，无法请求
    try:  # 发起 HTTP 请求并解析 JSON
        with httpx.Client(timeout=settings.map_timeout_seconds) as client:  # 创建 httpx 客户端，设置超时时间
            r = client.get(  # GET 请求高德地理编码接口
                AMAP_GEOCODE_URL,  # 访问高德地理编码接口
                params={  # 查询参数
                    "key": settings.amap_api_key,      # 高德 API KEY
                    "address": q,                      # 查询地址
                    "output": "JSON",                  # 返回 JSON 格式
                },  # params 结束
            )  # client.get 结束
            r.raise_for_status()  # HTTP 请求有状态异常时抛出异常
            data = r.json()       # 解析响应为 json
    except (httpx.HTTPError, ValueError, TypeError):  # 捕获网络、JSON解析等异常
        return None  # 请求或解析失败

    if str(data.get("status")) != "1":  # 接口状态不为 1，视为失败
        return None  # 高德返回失败状态
    rows = data.get("geocodes") or []   # 提取 "geocodes" 列表
    if not rows or not isinstance(rows, list):  # 不是列表或为空视为失败
        return None  # 无有效 geocodes
    row = rows[0]   # 只取第一个结果
    try:  # 解析 "经度,纬度" 字符串
        location = str(row.get("location") or "")  # 取经纬度字符串
        lon_text, lat_text = location.split(",", 1)  # 使用逗号分割为 [经度, 纬度]
        lon = float(lon_text)   # 转换为浮点数
        lat = float(lat_text)  # 纬度转浮点数
    except (ValueError, TypeError):  # 经度/纬度格式不对则失败
        return None  # location 字段无法解析
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):  # 经纬度范围合法性检查
        return None  # 坐标超出合法范围
    return {  # 返回标准格式的地址信息
        "lat": lat,  # 纬度
        "lon": lon,  # 经度
        "adcode": str(row.get("adcode") or "").strip(),  # 区域编码
        "city": str(row.get("city") or "").strip(),  # 城市名
        "province": str(row.get("province") or "").strip(),  # 省份名
        "district": str(row.get("district") or "").strip(),  # 区/县名
        "formatted_address": str(row.get("formatted_address") or "").strip(),  # 完整地址
    }  # 地理编码成功


def map_weather_forecast(city_or_adcode: str) -> dict[str, Any] | None:  # 查城市/adcode 的多日天气预报
    """
    高德天气预报接口典型原始返回：

    {
        "status": "1",
        "info": "OK",
        "forecasts": [
            {
                "city": "杭州市",
                "adcode": "330100",
                "province": "浙江",
                "reporttime": "2026-06-03 10:00:00",
                "casts": [
                    {
                        "date": "2026-06-03",
                        "week": "3",
                        "dayweather": "多云",
                        "nightweather": "阴",
                        "daytemp": "28",
                        "nighttemp": "21",
                        "daywind": "东",
                        "nightwind": "东",
                        "daypower": "≤3",
                        "nightpower": "≤3"
                    }
                ]
            }
        ]
    }

    本方法保留 forecasts[0] 的城市信息和 casts 列表，天气节点再按 date 匹配目标日期。
    """
    city = (city_or_adcode or "").strip()  # 去除 city_or_adcode 两端空白
    if not city or not settings.amap_api_key:  # 若 city 为空或未配置高德 API KEY 则返回 None
        return None  # 缺少查询目标或密钥
    try:  # 发起 HTTP 请求
        with httpx.Client(timeout=settings.map_timeout_seconds) as client:  # 打开 httpx 客户端，设置超时
            r = client.get(  # GET 请求天气预报接口
                AMAP_WEATHER_URL,  # 调用高德天气预报接口
                params={  # 查询参数
                    "key": settings.amap_api_key,  # 高德 API KEY
                    "city": city,                  # 查询的城市名或 adcode
                    "extensions": "all",           # 查询全部预报信息
                    "output": "JSON",              # 返回 JSON 格式
                },  # params 结束
            )  # client.get 结束
            r.raise_for_status()  # 检查响应状态是否正常，不正常则抛异常
            data = r.json()       # 解析响应内容为 JSON
    except (httpx.HTTPError, ValueError, TypeError):  # 捕获网络、解析等异常
        return None  # 请求失败

    if str(data.get("status")) != "1":  # 检查 status 是否为 "1"（成功），否则返回 None
        return None  # 接口返回失败
    forecasts = data.get("forecasts") or []  # 取得 forecasts 列表
    if not isinstance(forecasts, list) or not forecasts:  # forecasts 不是列表或为空，返回 None
        return None  # 无预报数据
    first = forecasts[0] or {}  # 取第一个城市的天气预报信息
    casts = first.get("casts") or []  # 取得该城市的 casts（具体预报）
    if not isinstance(casts, list):  # casts 非列表则置为空
        casts = []  # 兜底为空列表
    return {  # 返回精简后的天气数据结构
        "city": str(first.get("city") or "").strip(),           # 城市名
        "adcode": str(first.get("adcode") or "").strip(),       # 区域编码
        "province": str(first.get("province") or "").strip(),   # 省份名
        "reporttime": str(first.get("reporttime") or "").strip(),  # 报告时间
        "casts": [cast for cast in casts if isinstance(cast, dict)],  # 只保留字典类型的 casts
    }  # 天气数据整理完成


def _amap_lnglat(coords: tuple[float, float]) -> str:  # (lat, lon) → 高德 "lon,lat" 字符串
    """把 (纬度, 经度) 元组转成高德要求的 "经度,纬度" 字符串格式。

    注意：高德接口的坐标顺序是“经度在前、纬度在后”，与常见 (lat, lon) 相反。
    """
    lat, lon = coords  # 解包元组：第一个是纬度，第二个是经度
    return f"{lon:.6f},{lat:.6f}"  # 格式化为高德要求的 "经度,纬度" 字符串（保留 6 位小数）


def _format_minutes(raw_seconds: object) -> str:  # 秒数 → "约 N 分钟" 中文描述
    """把“秒”为单位的时长格式化为“约 N 分钟”，无法解析时给出兜底提示。"""
    try:  # 尝试把秒数转为分钟
        minutes = max(1, round(float(str(raw_seconds)) / 60))  # 秒转分钟，至少 1 分钟
    except (TypeError, ValueError):  # 无法解析时返回兜底文案
        return "时间需出发前核实"  # 时长字段异常
    return f"约{minutes}分钟"  # 返回中文时长描述


def map_transit_route_summary(  # 公交路径规划：返回给用户看的路线摘要
    origin: tuple[float, float],  # 起点 (纬度, 经度)
    destination: tuple[float, float],  # 终点 (纬度, 经度)
    city: str,  # 所在城市（高德公交接口必填）
    date_value: str | None = None,  # 可选约会日期，用于时刻表优化
) -> str:  # 成功时返回线路+耗时摘要，失败返回空串
    """
    高德公交路径规划接口典型原始返回：

    {
        "status": "1",
        "info": "OK",
        "route": {
            "origin": "120.130260,30.274084",
            "destination": "120.155070,30.274150",
            "transits": [
                {
                    "duration": "2460",
                    "walking_distance": "680",
                    "cost": "4.0",
                    "segments": [
                        {
                            "walking": {"distance": "320"},
                            "bus": {
                                "buslines": [
                                    {
                                        "name": "地铁1号线(湘湖--萧山国际机场)",
                                        "departure_stop": {"name": "武林广场"},
                                        "arrival_stop": {"name": "龙翔桥"}
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    }

    本方法只取第一条公交方案，提取线路名和总耗时，拼成给用户看的摘要。
    """
    if not settings.amap_api_key or not city:  # 缺少密钥或城市则无法查公交
        return ""  # 前置条件不满足
    # 构造请求参数
    params: dict[str, object] = {  # 高德公交 API 参数字典
        "key": settings.amap_api_key,  # 高德API KEY
        "origin": _amap_lnglat(origin),  # 起点坐标
        "destination": _amap_lnglat(destination),  # 终点坐标
        "city": city,  # 城市
    }  # 基础参数组装完成
    # 如果有日期参数，加入请求参数中
    if date_value:  # 若提供了约会日期，加入请求参数以优化时刻表
        params["date"] = date_value  # 追加日期字段

    try:  # 发起 HTTP 请求
        # 初始化 httpx 客户端，并设置超时时间
        with httpx.Client(timeout=settings.map_timeout_seconds) as client:  # 短连接客户端
            # 发起 GET 请求到高德公交路径规划接口
            response = client.get(AMAP_TRANSIT_URL, params=params)  # 调用公交规划 API
            # 如果响应状态码不是 2xx，则抛出异常
            response.raise_for_status()  # 非 2xx 则进入 except
            # 解析响应的 JSON 数据
            data = response.json()  # 转为 Python dict
    except (httpx.HTTPError, ValueError, TypeError):  # 网络或 JSON 异常
        # 网络请求或数据解析出错时，返回空字符串
        return ""  # 请求失败

    # 如果响应的 status 字段不是 "1"，说明接口查询失败，返回空字符串
    if str(data.get("status")) != "1":  # 高德业务状态失败
        return ""  # 无有效路线
    # 尝试获取返回结果中的 transit 方案列表
    transits = (data.get("route") or {}).get("transits")  # 公交方案数组
    # 如果没有查询到公交方案，返回空字符串
    if not transits:  # 方案列表为空
        return ""  # 查不到公交
    # 只取第一条公交方案
    first = transits[0]  # 只取推荐的第一条公交方案
    # 从方案中提取所有公交线路的名称，组成列表
    line_names = [  # 遍历 segments 收集线路名
        str(busline.get("name") or "").strip()  # 单条公交线路名称
        for segment in first.get("segments") or []  # 遍历每个segment，包含步行和公交
        for busline in (segment.get("bus") or {}).get("buslines") or []  # 获取每个segment中的所有公交线路
        if str(busline.get("name") or "").strip()  # 仅保留有名字的线路
    ]  # 线路名列表组装完成
    # 拼接所有公交线路名，如果没有则给出兜底文案
    route_text = "；".join(line_names) if line_names else "路线详情需出发前用高德地图核实"  # 线路摘要
    # 格式化耗时信息
    duration = _format_minutes(first.get("duration"))  # 总耗时（秒→分钟）
    # 返回组装好的摘要文本
    return f"{route_text}。全程{duration}。"  # 最终给用户看的公交摘要

