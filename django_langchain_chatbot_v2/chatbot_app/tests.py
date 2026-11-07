# 作者: 王道 龙哥
# 2026年08月03日14时58分20秒
# xxx@qq.com

"""
chatbot_app 模型单元测试。
右键本文件即可运行全部测试。
"""

import uuid
from datetime import timedelta
from django.test import TestCase
from django.db import IntegrityError
from django.utils import timezone

from .models import Contact, NegativeFeedback, ChatSession, ChatMessage


class ContactModelTest(TestCase):
    """Contact（联系人）模型测试类。"""

    def setUp(self):
        """每个测试用例执行前准备一条联系人记录。"""
        self.contact = Contact.objects.create(
            source_text="请联系我，手机号是 13800138000",
            contact_type="phone",
            contact_value="13800138000",
        )

    def test_create_contact(self):
        """测试创建联系人记录成功，字段值正确保存。"""
        self.assertIsNotNone(self.contact.id)
        self.assertEqual(self.contact.contact_type, "phone")
        self.assertEqual(self.contact.contact_value, "13800138000")
        self.assertEqual(self.contact.source_text, "请联系我，手机号是 13800138000")

    def test_contact_str(self):
        """测试 Contact 的 __str__ 返回格式为 '类型: 值'。"""
        self.assertEqual(str(self.contact), "phone: 13800138000")

    def test_contact_created_at_auto(self):
        """测试 created_at 自动填充且不晚于当前时间。"""
        self.assertIsNotNone(self.contact.created_at)
        self.assertLessEqual(self.contact.created_at, timezone.now())

    def test_create_multiple_contacts(self):
        """测试可创建多种类型的联系方式。"""
        Contact.objects.create(
            source_text="微信：wx_demo",
            contact_type="wechat",
            contact_value="wx_demo",
        )
        Contact.objects.create(
            source_text="QQ：123456",
            contact_type="qq",
            contact_value="123456",
        )
        self.assertEqual(Contact.objects.count(), 3)


class NegativeFeedbackModelTest(TestCase):
    """NegativeFeedback（负面反馈）模型测试类。"""

    def setUp(self):
        """每个测试用例执行前准备一条负面反馈记录。"""
        self.feedback = NegativeFeedback.objects.create(
            source_text="这个回答太差了，完全没用",
            reason="回答质量差",
        )

    def test_create_negative_feedback(self):
        """测试创建负面反馈记录成功，字段值正确保存。"""
        self.assertIsNotNone(self.feedback.id)
        self.assertEqual(self.feedback.source_text, "这个回答太差了，完全没用")
        self.assertEqual(self.feedback.reason, "回答质量差")

    def test_negative_feedback_str(self):
        """测试 NegativeFeedback 的 __str__ 包含 Negative 标识。"""
        self.assertIn("Negative", str(self.feedback))

    def test_reason_optional(self):
        """测试 reason 字段允许为空。"""
        feedback = NegativeFeedback.objects.create(
            source_text="不满意",
            reason=None,
        )
        self.assertIsNone(feedback.reason)
        feedback_blank = NegativeFeedback.objects.create(
            source_text="还是不满意",
            reason="",
        )
        self.assertEqual(feedback_blank.reason, "")

    def test_feedback_created_at_auto(self):
        """测试 created_at 自动填充。"""
        self.assertIsNotNone(self.feedback.created_at)
        self.assertLessEqual(self.feedback.created_at, timezone.now())


class ChatSessionModelTest(TestCase):
    """ChatSession（聊天会话）模型测试类。"""

    def setUp(self):
        """每个测试用例执行前准备一条会话记录。"""
        self.session = ChatSession.objects.create(user="test_user")

    def test_create_session(self):
        """测试创建会话成功，默认生成 UUID，用户名正确。"""
        self.assertIsNotNone(self.session.id)
        self.assertIsInstance(self.session.session_id, uuid.UUID)
        self.assertEqual(self.session.user, "test_user")

    def test_default_user_anonymous(self):
        """测试未指定 user 时默认为 anonymous。"""
        session = ChatSession.objects.create()
        self.assertEqual(session.user, "anonymous")

    def test_session_id_unique(self):
        """测试 session_id 具有唯一性约束。"""
        duplicate_id = self.session.session_id
        with self.assertRaises(IntegrityError):
            ChatSession.objects.create(session_id=duplicate_id, user="other")

    def test_session_str(self):
        """测试 ChatSession 的 __str__ 包含 session_id 与 user。"""
        result = str(self.session)
        self.assertIn(str(self.session.session_id), result)
        self.assertIn("test_user", result)

    def test_session_timestamps(self):
        """测试 created_at 与 updated_at 自动填充。"""
        self.assertIsNotNone(self.session.created_at)
        self.assertIsNotNone(self.session.updated_at)

    def test_session_ordering(self):
        """测试会话按 updated_at 倒序排列。"""
        older = ChatSession.objects.create(user="older")
        newer = ChatSession.objects.create(user="newer")
        # 手动拉开 updated_at 间隔，避免同一秒内精度导致排序不稳定
        now = timezone.now()
        ChatSession.objects.filter(pk=older.pk).update(updated_at=now - timedelta(minutes=2))
        ChatSession.objects.filter(pk=newer.pk).update(updated_at=now)
        ChatSession.objects.filter(pk=self.session.pk).update(updated_at=now - timedelta(minutes=1))
        sessions = list(ChatSession.objects.all())
        self.assertEqual(sessions[0].id, newer.id)
        self.assertEqual(sessions[-1].id, older.id)


class ChatMessageModelTest(TestCase):
    """ChatMessage（聊天消息）模型测试类。"""

    def setUp(self):
        """每个测试用例执行前准备会话及一条用户消息。"""
        self.session = ChatSession.objects.create(user="msg_user")
        self.message = ChatMessage.objects.create(
            session=self.session,
            role="user",
            content="你好，请问课程价格是多少？",
        )

    def test_create_message(self):
        """测试创建消息成功，字段值正确保存。"""
        self.assertIsNotNone(self.message.id)
        self.assertEqual(self.message.role, "user")
        self.assertEqual(self.message.content, "你好，请问课程价格是多少？")
        self.assertEqual(self.message.session, self.session)

    def test_create_assistant_message(self):
        """测试可创建助手角色消息。"""
        reply = ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content="课程价格为 998 元。",
        )
        self.assertEqual(reply.role, "assistant")
        self.assertEqual(self.session.messages.count(), 2)

    def test_message_str(self):
        """测试 ChatMessage 的 __str__ 包含角色与内容前缀。"""
        result = str(self.message)
        self.assertTrue(result.startswith("user:"))
        self.assertIn("你好，请问课程价格是多少？", result)

    def test_message_str_truncates_long_content(self):
        """测试超长内容在 __str__ 中只保留前 50 个字符。"""
        long_content = "测" * 80
        msg = ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content=long_content,
        )
        result = str(msg)
        # "assistant: " + 前 50 个字
        self.assertEqual(result, f"assistant: {long_content[:50]}")

    def test_related_name_messages(self):
        """测试通过 related_name='messages' 反向查询会话消息。"""
        ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content="回复内容",
        )
        messages = self.session.messages.all()
        self.assertEqual(messages.count(), 2)

    def test_cascade_delete(self):
        """测试删除会话时级联删除其下所有消息。"""
        ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content="将被级联删除",
        )
        self.assertEqual(ChatMessage.objects.count(), 2)
        self.session.delete()
        self.assertEqual(ChatMessage.objects.count(), 0)

    def test_message_ordering(self):
        """测试消息按 created_at 正序排列。"""
        msg2 = ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content="第二条消息",
        )
        messages = list(self.session.messages.all())
        self.assertEqual(messages[0].id, self.message.id)
        self.assertEqual(messages[1].id, msg2.id)

    def test_message_created_at_auto(self):
        """测试消息 created_at 自动填充。"""
        self.assertIsNotNone(self.message.created_at)
        self.assertLessEqual(self.message.created_at, timezone.now())
