from django.contrib import admin
from .models import Contact, NegativeFeedback, ChatSession, ChatMessage


# 联系人模型管理类
@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ('id', 'contact_type', 'contact_value', 'created_at')
    list_filter = ('contact_type', 'created_at')
    search_fields = ('contact_value', 'source_text')
    readonly_fields = ('id', 'created_at')
    fieldsets = (
        ('基本信息', {
            'fields': ('id', 'contact_type', 'contact_value')
        }),
        ('详细信息', {
            'fields': ('source_text', 'created_at')
        }),
    )


# 负面反馈模型管理类
@admin.register(NegativeFeedback)
class NegativeFeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'reason', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('reason', 'source_text')
    readonly_fields = ('id', 'created_at')
    fieldsets = (
        ('反馈信息', {
            'fields': ('id', 'reason', 'source_text', 'created_at')
        }),
    )


# 聊天消息内联管理类（用于在会话中显示消息）
class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('id', 'created_at')
    fields = ('id', 'role', 'content', 'created_at')
    can_delete = True


# 聊天会话模型管理类
@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'session_id', 'user', 'created_at', 'updated_at', 'message_count')
    list_filter = ('created_at', 'updated_at', 'user')
    search_fields = ('session_id', 'user')
    readonly_fields = ('id', 'session_id', 'created_at', 'updated_at')
    inlines = [ChatMessageInline]
    fieldsets = (
        ('会话信息', {
            'fields': ('id', 'session_id', 'user')
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def message_count(self, obj):
        """显示会话中的消息数量"""
        return obj.messages.count()
    message_count.short_description = '消息数量'


# 聊天消息模型管理类
@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'role', 'content_preview', 'created_at')
    list_filter = ('role', 'created_at', 'session')
    search_fields = ('content', 'session__session_id', 'session__user')
    readonly_fields = ('id', 'created_at')
    fieldsets = (
        ('消息信息', {
            'fields': ('id', 'session', 'role', 'content')
        }),
        ('时间信息', {
            'fields': ('created_at',)
        }),
    )
    
    def content_preview(self, obj):
        """显示消息内容预览（前50个字符）"""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = '内容预览'

