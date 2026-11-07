"""中文日期解析模块。

用户在对话里往往说的是“今天/明天/本周六/下周末/6月18日”这类自然语言日期，
本模块借助 JioNLP 把它们解析成标准的 ISO 日期（YYYY-MM-DD），并统一按“中国时区”作为基准。
"""

from __future__ import annotations  # 允许在类型提示中使用 date | None 等前向引用写法

from datetime import date, datetime, timedelta, timezone  # 日期/时间处理标准库
import jionlp as jio  # JioNLP：中文自然语言日期解析库


# 固定为东八区（中国标准时间），保证相对日期（今天/明天）解析基准正确。
CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")  # 东八区时区对象
# 星期索引到中文名的映射，weekday() 返回 0=周一 ... 6=周日。
WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")  # 索引 0-6 对应周一到周日


def current_date_context() -> tuple[date, str]:  # 获取中国时区“今天”及中文星期
    """返回“当前中国时间”的今天日期和对应的中文星期。

    返回:
        (今天的 date 对象, 中文星期字符串)，供提示词告知模型日期基准。
    """
    today = datetime.now(CHINA_TZ).date()  # 取东八区当前时刻对应的日期
    return today, WEEKDAYS[today.weekday()]  # 返回 (日期对象, 中文星期名)


def resolve_date_text(date_text: str) -> str:  # 对外入口：自然语言日期 → ISO 字符串
    """把自然语言日期文本解析为 ISO 日期字符串。

    参数:
        date_text: 用户原始日期表达，如“下周六”“6月18日”。

    返回:
        形如 "2026-06-18" 的 ISO 日期字符串。

    异常:
        ValueError: 当文本为空或无法可靠解析时抛出，交由上层节点追问用户。
    """
    text = date_text.strip()  # 去掉首尾空白
    if not text:  # 空字符串无法解析
        raise ValueError("没有可靠识别约会日期，请提供明确日期或常见相对日期说法。")  # 空输入直接失败

    parsed = _resolve_date_with_jionlp(text)  # 调用 JioNLP 内部解析
    if parsed is None:  # 解析失败时向上层抛出友好错误
        raise ValueError("没有可靠识别约会日期，请换一种更明确的说法，例如具体日期、今天、明天或下周六。")  # JioNLP 无法解析
    return parsed.isoformat()  # 转成 "YYYY-MM-DD" 字符串返回


def _resolve_date_with_jionlp(date_text: str) -> date | None:  # 内部：JioNLP 解析，失败返回 None
    """内部方法：调用 JioNLP 解析日期，失败时返回 None（不抛异常）。

    JioNLP `parse_time` 的典型返回结构：

        {
            "type": "time_point",
            "definition": "accurate",
            "time": ["2026-06-18 00:00:00", "2026-06-18 23:59:59"]
        }

    说明：
    - `time_base` 传入“当前时间戳”，用于把“下周六”等相对日期换算成绝对日期。
    - 我们只关心日期部分，所以取 time[0] 的前 10 位（YYYY-MM-DD）。
    """
    try:  # 调用 JioNLP，捕获库内部异常
        base = datetime.now(CHINA_TZ)  # 以当前中国时间为解析基准
        # time_base 用当前时间戳作为解析基准，保证相对日期正确。
        parsed = jio.parse_time(date_text, time_base=base.timestamp())  # 调用 JioNLP 解析
    except Exception:  # JioNLP 抛错时不向上传播
        # JioNLP 内部异常时不影响主流程，返回 None 让上层追问。
        return None  # 解析失败
    if not isinstance(parsed, dict):  # 返回结构异常则视为失败
        return None  # 非 dict 结构
    time_range = parsed.get("time")  # 取出时间区间列表，如 ["2026-06-18 00:00:00", "..."]
    if not isinstance(time_range, (list, tuple)) or not time_range:  # 必须是非空列表/元组
        return None  # time 字段无效
    first_value = str(time_range[0] or "").strip()  # 取区间起点并转为字符串
    # 至少要有 "YYYY-MM-DD" 这 10 个字符才算有效。
    if len(first_value) < 10:  # 日期部分长度不足
        return None  # 字符串太短
    try:  # 尝试把前 10 位解析为 date
        return date.fromisoformat(first_value[:10])  # 截取前 10 位转为 date 对象
    except ValueError:  # ISO 格式不合法
        return None  # 解析 date 失败
