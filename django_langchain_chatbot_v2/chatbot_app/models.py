from django.db import models  # 导入Django的模型模块
import uuid  # 导入uuid模块，用于生成唯一会话ID


# 联系人模型，用于存储从文本中提取的联系方式
class Contact(models.Model):
    id = models.BigAutoField(primary_key=True)  # 显式定义主键，使用BigAutoField
    source_text = models.TextField()  # 原始文本内容
    contact_type = models.CharField(max_length= 32)  # 联系方式类型（如邮箱、电话等）
    contact_value = models.CharField(max_length=128)  # 具体的联系方式值
    created_at = models.DateTimeField(auto_now_add=True)  # 记录创建时间，自动设置为当前时间

    def __str__(self):
        return f"{self.contact_type}: {self.contact_value}"  # 返回格式化的联系方式字符串


# 负面反馈模型，用于记录用户对某些内容的负面反馈
class NegativeFeedback(models.Model):
    id = models.BigAutoField(primary_key=True)  # 显式定义主键，使用BigAutoField
    source_text = models.TextField()  # 收到负面反馈的原始文本内容
    reason = models.CharField(max_length=256, null=True, blank=True)  # 负面反馈的原因，可选填
    created_at = models.DateTimeField(auto_now_add=True)  # 记录创建时间，自动设置为当前时间

    def __str__(self):
        return f"Negative @ {self.created_at}"  # 返回带时间戳的负面反馈标识字符串


# 聊天会话模型，用于管理多轮对话的会话
class ChatSession(models.Model):
    id = models.BigAutoField(primary_key=True)  # 显式定义主键
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)  # 会话唯一标识符
    user = models.CharField(max_length=128, default='anonymous')  # 用户标识
    created_at = models.DateTimeField(auto_now_add=True)  # 会话创建时间
    updated_at = models.DateTimeField(auto_now=True)  # 会话最后更新时间

    def __str__(self):
        return f"Session {self.session_id} - {self.user}"

    class Meta:
        ordering = ['-updated_at']  # 按更新时间倒序排列


# 聊天消息模型，用于存储会话中的每条消息
class ChatMessage(models.Model):
    id = models.BigAutoField(primary_key=True)  # 显式定义主键
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')  # 关联会话
    role = models.CharField(max_length=16, choices=[('user', '用户'), ('assistant', '助手')])  # 消息角色
    content = models.TextField()  # 消息内容
    created_at = models.DateTimeField(auto_now_add=True)  # 消息创建时间

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"

    class Meta:
        ordering = ['created_at']  # 按创建时间正序排列
