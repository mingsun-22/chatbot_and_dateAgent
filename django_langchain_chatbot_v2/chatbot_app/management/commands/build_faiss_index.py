from django.core.management.base import BaseCommand
from chatbot_app.rag import build_index_from_folder

class Command(BaseCommand):
    help = '从 data/docs 构建 FAISS 索引（调用 rag.build_index_from_folder）'

    def handle(self, *args, **options):
        n = build_index_from_folder()
        self.stdout.write(self.style.SUCCESS(f'构建完成，文档片段数: {n}'))
