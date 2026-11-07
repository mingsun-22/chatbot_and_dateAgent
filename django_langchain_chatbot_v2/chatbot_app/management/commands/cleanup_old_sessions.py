"""
清理旧会话的Django管理命令

使用方法:
python manage.py cleanup_old_sessions --days 7

这将删除7天前的会话及其相关消息
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from chatbot_app.models import ChatSession


class Command(BaseCommand):
    help = '清理指定天数之前的旧会话'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='删除多少天之前的会话（默认30天）'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅显示将要删除的会话数量，不实际删除'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        
        # 计算截止日期
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # 查找旧会话
        old_sessions = ChatSession.objects.filter(updated_at__lt=cutoff_date)
        count = old_sessions.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(f'没有找到{days}天之前的会话')
            )
            return
        
        # 统计消息数量
        total_messages = sum(session.messages.count() for session in old_sessions)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[模拟运行] 将删除 {count} 个会话和 {total_messages} 条消息'
                )
            )
            self.stdout.write('使用 --no-dry-run 参数实际执行删除')
        else:
            # 实际删除
            old_sessions.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f'成功删除 {count} 个会话和 {total_messages} 条消息'
                )
            )

