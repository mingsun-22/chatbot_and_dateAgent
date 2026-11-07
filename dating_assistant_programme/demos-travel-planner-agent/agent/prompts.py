"""约会助手用到的所有提示词（Prompt）模板。

把提示词集中放在一个文件里，好处是：
- 业务逻辑（nodes.py）和“对模型说的话”解耦，改文案不用动流程代码；
- 每个函数用 f-string 把运行时数据（地点、日期、搜索结果等）拼进模板。

命名约定：`xxx_prompt(...)` 返回一段完整的提示词字符串。
"""

from __future__ import annotations  # 允许使用 str | None 等现代类型注解


def budget_terms_prompt(text: str) -> str:  # 低预算倾向判断 prompt
    """构造“判断用户是否为低预算倾向”的提示词，要求模型只返回布尔 JSON。"""
    # 下方多行字符串为 LLM 指令模板，{text} 会被用户偏好原文替换
    return f"""请判断用户是否明确表达了低预算、想省钱、不要太贵、平价、性价比、免费或低成本倾向。

只返回 JSON：{{"use_low_budget_terms": true/false}}

规则：
- 只有用户明确强调预算不高、不要太贵、想省钱、平价、性价比、免费、低成本，或给出明显低预算上限时，返回 true。
- 如果用户只是说“预算中等”、没有提预算、预算充足、想要高端/仪式感，不要返回 true。
- 不要做预算计算，只判断是否需要在搜索关键词中加入低预算倾向词。

用户表达：
{text}
"""


def date_details_prompt(*, text: str, today: str, weekday: str) -> str:  # 抽取地点/日期/时间段 prompt
    """构造“从用户消息抽取约会地点/日期/时间段”的信息抽取提示词。

    传入 today、weekday 作为日期基准，要求模型保留用户原始日期表达（不擅自换算）。
    """
    # 信息抽取 prompt：要求模型输出紧凑 JSON，保留用户原始日期/时间段表达
    return f"""你是信息抽取器。请从用户消息中抽取约会计划信息。

只返回一个紧凑 JSON，不要解释，字段如下：
- "date_area": 约会地点，城市/区域/商圈均可
- "date_date": 用户原文中的日期表达，例如“明天”“本周六”“下周末”“5月9日”
- "date_time_range": 用户原文中的约会时间段，必须用 24 小时制表示，例如“14:00-18:00”“18:30-21:00”

日期基准：
- 当前时区：Asia/Shanghai，中国时间。
- 今天是 {today}，{weekday}。
- 不要把相对日期换算成绝对日期，date_date 必须保留用户的原始日期表达。
- 如果用户说“本周末/周末/下周末”，date_date 就原样输出，不要擅自改成周六或周日。

时间段抽取规则：
- 必须抽取明确的开始和结束时间，例如“14:00-18:00”。
- 如果用户只写“下午”“晚上”“下班后”等模糊时间，date_time_range 返回空字符串。
- 不要把半天、一天、全天转换成时间段。

用户消息：
{text}
"""


def departure_prompt(text: str) -> str:  # 抽取出发地地址 prompt
    """构造“从用户消息抽取真实出发地地址”的提示词，返回结构化 JSON。"""
    # 出发地抽取 prompt：区分出发地与约会地点，避免混淆
    return f"""请从用户消息中抽取真实出发地地址。

只返回 JSON：{{"departure_address": "..."}}

规则：
- departure_address 应尽量包含城市 + 区/街道/地标，例如“杭州西湖区文三路”。
- 如果用户说“我在 A，去 B 约会”，departure_address 应为 A。
- 如果用户只给了一个地点，就直接返回这个地点。
- 不要把约会地点误认为出发地。
- 如果没有明确出发地，departure_address 返回空字符串。

用户消息：
{text}
"""


def weather_summary_prompt(*, area: str, target_date: str, weather_context: str) -> str:  # 天气穿搭总结 prompt
    """构造“根据高德天气数据总结穿搭建议”的提示词，限制在 120 字以内。"""
    # 天气总结 prompt：基于高德 casts 数据生成穿搭与室内备选建议
    return f"""请用中文总结 {area} 在 {target_date} 适合约会的天气信息。

要求：
- 第一段用一句话说明天气情况。
- 第二段给出约会穿搭建议。
- 第三段给出一个室内备选提醒。
- 只输出 120 字以内。
- 天气数据来自高德天气预报，请基于数据给建议，不要编造。

天气数据：
{weather_context}
"""


def activity_recommendations_prompt(  # 活动候选整理 prompt
    *,  # 强制关键字传参，避免参数顺序搞混
    area: str,  # 约会地点
    date_value: str | None,  # 约会日期
    preferences: str | None,  # 用户偏好
    weather_summary: str | None,  # 天气摘要（决定室内/室外）
    search_results: str,  # Tavily 压缩后的搜索结果
) -> str:  # 返回完整 prompt 字符串
    """构造“基于搜索结果整理约会活动候选”的提示词，结合天气选择室内/室外。"""
    # 活动推荐 prompt：结合天气、偏好和 Tavily 搜索结果整理 4 个短候选
    return f"""请基于搜索结果，用中文整理适合约会的活动候选。

约会地点：{area}
约会日期：{date_value}
用户偏好：{preferences or '未说明'}
天气情况：{weather_summary or '暂无'}

要求：
- 给出 4 个短候选，用编号列表输出。
- 每个候选必须包含：名称、开放时间、室内/室外、约会风格、特点、费用/预算、注意事项。
- 结合天气选择室内/室外活动；天气差时优先室内，天气适合时可保留户外散步、夜景、拍照。
- 每个候选控制在 80 字以内，不要写长段落。
- 不要承诺实时营业状态，提醒下单或出发前核实。
- 搜索结果没有明确开放时间或费用时，写“需出发前核实”，不要编造精确值。

搜索结果：
{search_results}
"""


def restaurant_recommendations_prompt(*, area: str, date_value: str | None, preferences: str | None, search_results: str) -> str:  # 餐饮候选整理 prompt
    """构造“基于搜索结果整理约会餐饮候选”的提示词，输出 4 个短候选。"""
    # 餐饮推荐 prompt：基于 Tavily 搜索结果整理 4 个短候选
    return f"""请基于搜索结果，用中文整理适合约会的餐饮候选。

约会地点：{area}
约会日期：{date_value}
用户偏好：{preferences or '未说明'}

要求：
- 给出 4 个短候选，用编号列表输出。
- 每个候选必须包含：名称、营业时间、类型、约会风格、特点、人均/预算、注意事项。
- 每个候选控制在 80 字以内，不要写长段落。
- 不要承诺实时价格、排队、营业状态或可订位。
- 搜索结果没有明确营业时间或人均时，写“需出发前核实”，不要编造精确值。

搜索结果：
{search_results}
"""


def date_plan_prompt(  # 最终约会方案整合 prompt
    *,  # 全部使用关键字参数
    area: str,  # 约会地点
    date_line: str,  # 日期 + 星期展示行
    time_range: str | None,  # 约会时间段
    departure: str | None,  # 出发地
    weather_summary: str | None,  # 天气与穿搭
    travel_summary: str | None,  # 交通建议
    preferences: str | None,  # 用户偏好
    activity_recommendations: str | None,  # 活动候选
    restaurant_recommendations: str | None,  # 餐饮候选
    weekday: str,  # 中文星期（模型必须沿用，勿重算）
) -> str:  # 返回完整 prompt 字符串
    """构造“汇总所有信息生成最终约会方案”的提示词。

    把天气、出行、偏好、活动候选、餐饮候选等全部拼进模板，要求模型输出固定四段结构
    （时间线、简短总结、预算估算、备选提醒）。
    """
    # 最终方案整合 prompt：汇总所有节点产出，要求固定四段输出结构
    return f"""你是专业中文约会策划助手。请生成一份可执行的约会方案。

约会地点：{area}
约会日期：{date_line}
约会时间段：{time_range or '未说明'}
出发地：{departure or '未确认'}

天气与穿搭：
{weather_summary or '暂无'}

出行建议：
{travel_summary or '暂无'}

用户偏好：
{preferences or '未说明'}

活动候选：
{activity_recommendations or '暂无'}

餐饮候选：
{restaurant_recommendations or '暂无'}

输出要求：
- 全文中文，只输出以下四段，不要写长篇解释。
- 第一段标题为“时间线”，只用表格或短列表输出，并严格覆盖约会时间段：{time_range or '未说明'}。
- 时间线每段必须包含：时间、地点/事项、做什么、预计预算、关键提醒。
- 第二段标题为“简短总结”，控制在 120 字以内，说明路线风格、节奏和适合点。
- 第三段标题为“预算估算”，控制在 80 字以内，给出区间估算；没有价格依据时写“需出发前核实”。
- 第四段标题为“备选提醒”，只写 1 句话，说明雨天、闭店或人多时怎么替换。
- 必须使用约会日期中的星期：{weekday or '未识别'}，不要自行重新计算星期。
- 不要编造已经预订、实时价格、实时车位或确定营业状态。
"""
