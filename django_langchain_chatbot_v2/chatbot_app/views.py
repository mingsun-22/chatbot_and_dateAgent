import re  # 导入正则表达式模块，用于模式匹配
import json  # 导入 JSON 模块，用于解析请求体中的 JSON 数据
from django.http import JsonResponse  # 导入 Django 的 JsonResponse，用于返回 JSON 响应
from django.shortcuts import render  # 导入 render 函数，用于渲染 HTML 模板
from django.views.decorators.csrf import csrf_exempt  # 导入 CSRF 豁免装饰器，允许跨站请求
from .models import Contact, NegativeFeedback, ChatSession, ChatMessage  # 导入本地模型
from .rag import answer_with_rag  # 导入本地 RAG（检索增强生成）模块，用于生成回答
import uuid
import os
from langchain_openai import ChatOpenAI
from .db_tools import save_contact

LLM_MODEL = "qwen3.7-plus"


def create_llm():
    """使用 .env 中的阿里云百炼兼容接口创建大模型客户端。"""
    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=1,
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv("DASHSCOPE_BASE_URL"),
    )

# 编译正则表达式：匹配中国大陆手机号（可选国际区号）
PHONE_RE = re.compile(r"(\+?\d{2,4}[- ]?)?(1[3-9]\d{9})")
# 编译正则表达式：匹配微信 ID（6-20 位字母、数字、下划线或减号）
WECHAT_RE = re.compile(r"\b[0-9A-Za-z_-]{6,20}\b")
# 编译正则表达式：匹配 QQ 号（5-12 位数字，首位非 0）
QQ_RE = re.compile(r"\b[1-9][0-9]{4,11}\b")
# 编译正则表达式：匹配消息中是否出现 QQ 或 qq 关键词
QQ_KEYWORD_RE = re.compile(r"QQ|qq")
# 定义负面关键词列表，用于检测用户不满情绪
NEGATIVE_KEYWORDS = ['不满意', '差', '投诉', '糟糕', '失望', '不靠谱', '差评', '无法', '垃圾']


def chat_view(request):
    """渲染聊天页面"""
    return render(request, 'chat.html')


@csrf_exempt
def api_chat(request):
    """处理聊天 API 请求：提取联系方式、检测负面反馈并生成回答，支持多轮对话"""
    # 仅允许 POST 方法
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    # 解析请求体中的 JSON 数据
    data = json.loads(request.body.decode('utf-8'))
    msg = data.get('message', '')  # 获取用户发送的消息内容
    user = data.get('user', 'anonymous')  # 获取用户标识，默认为匿名
    session_id_str = data.get('session_id', None)  # 获取会话ID

    # 获取或创建会话
    if session_id_str:  # 如果提供了 session_id
        try:
            session_uuid = uuid.UUID(session_id_str)  # 将 session_id_str 转换为 UUID 对象
            session = ChatSession.objects.filter(session_id=session_uuid).first()  # 根据 UUID 查询会话
            if not session:  # 如果没有查到对应的会话
                session = ChatSession.objects.create(user=user)  # 则新建一个会话
        except (ValueError, AttributeError):  # 如果转换 UUID 失败或 session_id_str 无效
            session = ChatSession.objects.create(user=user)  # 则新建一个会话
    else:  # 如果没有提供 session_id
        session = ChatSession.objects.create(user=user)  # 创建新会话

    # 保存用户消息（用户提问）
    ChatMessage.objects.create(session=session, role='user', content=msg)


    contact_recorded = False


    # 按优先级提取联系方式：QQ > 手机号 > 微信，三者互斥只执行其中一个
    mqq = QQ_RE.search(msg)  # 尝试匹配 QQ 号数字
    m = PHONE_RE.search(msg)  # 尝试匹配手机号
    # QQ：必须同时命中 QQ/qq 关键词 与 QQ 号数字正则
    if QQ_KEYWORD_RE.search(msg) and mqq:
        qq = mqq.group(0)  # 获取匹配到的 QQ 号
        # 将提取到的 QQ 号保存到 Contact 数据表中
        Contact.objects.create(source_text=msg, contact_type='qq', contact_value=qq)
        contact_recorded = True  # 标记已记录联系方式
    # 使用正则提取手机号并保存到数据库
    elif m:
        phone = m.group(2) if m.groups() else m.group(0)  # 优先提取纯手机号部分
        # 将提取到的手机号保存到 Contact 数据表中
        Contact.objects.create(source_text=msg, contact_type='phone',  )
        contact_recorded = True
    # 检测消息内容是否包含“微信”相关关键词，再尝试提取微信 ID
    elif '微信' in msg or 'wx' in msg.lower() or 'wechat' in msg.lower():
        mwx = WECHAT_RE.search(msg)  # 用正则尝试提取微信号
        if mwx:
            # 保存微信号到 Contact 数据表
            Contact.objects.create(source_text=msg, contact_type='wechat', contact_value=mwx.group(0))
            contact_recorded = True  # 标记已记录联系方式

    # 若正则未命中，调用LLM进行兜底抽取联系方式并写库
    if not contact_recorded:
        try:
            llm = create_llm()
            prompt = (
                "你是信息抽取助手。请从如下文本中抽取用户联系方式（手机、微信、QQ、邮箱或其它）。"
                "如果不存在联系方式，返回：{\"has_contact\": false}。"
                "如果存在，返回严格的JSON："
                "{\"has_contact\": true, \"type\": \"phone|wechat|qq|email|other\", \"value\": \"具体值\"}。\n"
                f"文本：{msg}"
            )
            resp = llm.invoke(prompt)  # 调用 LLM 返回响应
            content = getattr(resp, "content", str(resp))  # 获取返回内容（适配 OpenAI/字典格式）
            data = json.loads(content)  # 解析 JSON 字符串为 Python 对象（python对象是一个字典）
            if isinstance(data, dict) and data.get("has_contact") and data.get("value"):  # 判断是否成功抽取到联系方式
                ctype = (data.get("type") or "other").lower()  # 获取联系方式类型，并转换为小写
                cvalue = str(data.get("value"))  # 获取联系方式的具体数值
                save_contact(source_text=msg, contact_type=ctype, contact_value=cvalue)  # 保存联系方式到数据库
                contact_recorded = True  # 标记已记录联系方式
        except Exception:
            # 兜底失败则忽略，继续后续流程
            pass

    # 遍历负面关键词，若命中则记录负面反馈并跳出循环
    feedback_recorded = False  # 标志变量，标记当前是否已经记录负面反馈
    for kw in NEGATIVE_KEYWORDS:  # 遍历负面反馈关键词列表
        if kw in msg:  # 如果用户消息中包含该负面关键词
            NegativeFeedback.objects.create(source_text=msg, reason=kw)  # 在数据库中创建一条负面反馈记录
            feedback_recorded = True  # 设置标志为已记录
            break  # 已命中关键词，无需继续检查

    # 未命中关键词时，调用 LLM 兜底识别负面反馈
    if not feedback_recorded:
        try:
            llm = create_llm()
            prompt = (
                "你是一个服务反馈识别助手。请判断下面文本是否表达负面反馈（不满意、投诉、批评、建议改进等）。"
                "仅返回严格的JSON：如果是负面反馈，"
                "{\"is_negative\": true, \"reason\": \"一句话原因或关键词\"};"
                "如果不是，{\"is_negative\": false}。文本：\n"
                f"{msg}"
            )
            resp = llm.invoke(prompt)
            content = getattr(resp, "content", str(resp))  # 获取LLM响应的内容（兼容不同类型的返回）
            data = json.loads(content)  # 将JSON字符串内容解析为Python对象
            if isinstance(data, dict) and data.get("is_negative"):  # 如果返回是字典且标记为负面反馈
                NegativeFeedback.objects.create(  # 创建一条负面反馈记录
                    source_text=msg,  # 保存原始用户消息
                    reason=str(data.get("reason", ""))[:256]  # 原因字段（若提供），并限制长度为256
                )
                feedback_recorded = True  # 标记已记录负面反馈
        except Exception:
            pass

    # 获取对话历史（最近10条消息，不包括刚保存的用户消息）
    # 获取所有历史消息，按时间排序
    all_messages = list(ChatMessage.objects.filter(session=session).order_by('created_at'))
    # 排除最后一条（刚保存的用户消息），并限制为最近10轮对话（20条消息）
    history_messages = all_messages[:-1][-20:] if len(all_messages) > 1 else []
    chat_history = [{"role": msg.role, "content": msg.content} for msg in history_messages]

    # 使用RAG生成回答，传入对话历史
    answer, sources = answer_with_rag(msg, chat_history=chat_history)

    prefix_parts = []
    if contact_recorded:
        prefix_parts.append("已经将你的联系方式记录，后面会客服联系你；")
    if feedback_recorded:
        prefix_parts.append("非常感谢你的意见，我们会积极努力改进")
    final_answer = "".join(prefix_parts) + (answer or "")

    # 保存助手回复
    ChatMessage.objects.create(session=session, role='assistant', content=final_answer)

    # 返回 JSON 响应，包含回答、来源信息和会话ID
    return JsonResponse({
        'answer': final_answer,
        'sources': sources,
        'session_id': str(session.session_id)
    })


def health_check(request):
    """健康检查接口，返回服务状态"""
    return JsonResponse({'status': 'ok'})


def sessions_view(request):
    """查看所有会话历史"""
    sessions = ChatSession.objects.all().prefetch_related('messages')[:20]  # 最近20个会话
    total_sessions = ChatSession.objects.count()
    total_messages = ChatMessage.objects.count()

    return render(request, 'sessions.html', {
        'sessions': sessions,
        'total_sessions': total_sessions,
        'total_messages': total_messages
    })
