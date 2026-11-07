"""书籍文件加载器。

负责把磁盘上的书籍文件读成 LangChain 的 Document 列表。目前主要支持 PDF，
读取时会把书名、文件名、来源路径写进 metadata，便于后续在回答里标注引用来源。
"""

from __future__ import annotations  # 允许在类型注解里引用尚未定义的类型名

from dataclasses import dataclass  # 用于定义不可变配置数据类 BookConfig
from pathlib import Path  # 跨平台路径操作

from langchain_community.document_loaders import PyPDFLoader  # LangChain 社区版 PDF 加载器
from langchain_core.documents import Document  # LangChain 标准文档对象（正文 + metadata）


# 允许纳入索引的书籍文件扩展名（当前实际解析的是 .pdf）。
SUPPORTED_BOOK_EXTENSIONS = {".txt", ".md", ".pdf"}  # 白名单：只索引这些后缀的文件


@dataclass(frozen=True)  # 不可变数据类：书名与目录路径绑定后不可修改
class BookConfig:  # 单本书的索引配置（展示名 + 磁盘目录）
    """一本书的配置：展示用书名 + 该书所在的目录路径。"""

    book_name: str  # 展示用书名，会写入 Document.metadata["book_name"]
    path: Path  # 该书在磁盘上的目录路径


def candidate_book_paths(books_dir: Path, book_name: str | None = None) -> list[Path]:  # 解析待建索引的书目录列表
    """在书籍父目录下找出要建索引的书目录列表。

    参数:
        books_dir: 存放各本书子目录的父目录（通常是 data/）。
        book_name: 指定书名则只返回该本；为空则返回目录下所有子目录。
    """
    if not books_dir.exists():  # 父目录不存在时无法建索引
        return []  # 返回空列表，由上层 build_indexes 转成 error 响应
    if book_name:  # 指定了单本书名：只构建该本
        book_path = books_dir / book_name  # 拼出目标书的子目录路径
        return [book_path] if book_path.is_dir() else []  # 目录存在才返回，否则空列表
    return sorted(path for path in books_dir.iterdir() if path.is_dir())  # 未指定书名：返回所有子目录并排序


def book_files(path: Path) -> list[Path]:  # 递归列出某书目录下受支持的文件
    """递归列出某本书目录下所有受支持的文件（按路径排序）。"""
    return [
        item  # 符合条件的文件路径
        for item in sorted(path.rglob("*"))  # 递归遍历书目录下所有文件，按路径排序
        if item.is_file() and item.suffix.lower() in SUPPORTED_BOOK_EXTENSIONS  # 只保留白名单后缀的普通文件
    ]


def load_book_documents(config: BookConfig) -> list[Document]:  # 加载单本书的全部 PDF 页面为 Document 列表
    """加载一本书的全部 PDF 页面为 Document 列表。

    每一页作为一个 Document，并在 metadata 中补充书名/文件名/来源路径，
    这些信息在最终回答标注“来源：《书名》，文件，页码”时会用到。
    """
    documents: list[Document] = []  # 累积本书所有页面的 Document
    for path in book_files(config.path):  # 遍历该书目录下所有受支持文件
        if path.suffix.lower() == ".pdf":  # 当前实现仅解析 PDF（.txt/.md 在白名单但未实现加载器）
            book_page_documents = PyPDFLoader(str(path)).load()  # 按页加载 PDF，每页一个 Document
            for page in book_page_documents:  # 逐页补充 metadata 后并入结果列表
                metadata = dict(page.metadata)  # 复制 PyPDFLoader 自带的页码等元数据
                metadata.update({
                    "book_name": config.book_name,  # 书名，供回答引用标注
                    "file_name": path.name,  # 文件名，供回答引用标注
                    "source": str(path)  # 磁盘完整路径，便于调试溯源
                })
                documents.append(Document(page_content=page.page_content, metadata=metadata))  # 组装最终 Document

    return documents  # 返回本书全部页面文档（可能为空列表）
