"""书籍文本清洗与切分。

从 PDF 抽取的文本往往夹杂水印广告、PDF 内部对象标记、多余空格换行等噪声。
本模块先做规范化清洗、过滤噪声片段，再用递归字符切分器把长文本切成带重叠的小片段，
以便向量化和后续检索。
"""

from __future__ import annotations  # 允许在类型注解里引用尚未定义的类型名

import re  # 正则表达式：去水印、判断噪声、压缩空白
from typing import Any  # metadata 字典值的类型标注

from langchain_core.documents import Document  # LangChain 标准文档对象
from langchain_text_splitters import RecursiveCharacterTextSplitter  # 按分隔符优先级递归切分长文本


# 需要从正文中剔除的水印/广告文案正则（针对特定盗版电子书的推广水印）。
WATERMARK_PATTERNS = (
    r"\[鏈€鏂扮數瀛愪功鍒嗕韩绀剧兢锛岃鍔犵兢涓籠s*V\s*淇s*303318103\s*娣诲姞澶囨敞鐢靛瓙涔]",
    r"鍔犲井淇s*songshutaoshu\s*[锛?]?\s*杩涗俊鎭簿閫変粯璐圭兢\s*[锛?]?\s*鐪嬫洿澶氬ぇ\s*V\s*浠樿垂鏂囩珷鍜岃祫鏂?",
)  # 水印正则元组：匹配到则替换为空串

# 若片段里出现这些 PDF 内部对象标记，说明是解析出的乱码/元数据，应整段丢弃。
PDF_OBJECT_MARKERS = (
    "/FontDescriptor",
    "/CIDFontType",
    "/DescendantFonts",
    "/Encoding/Identity-H",
    "/Subtype/",
    "/BaseFont/",
)  # PDF 内部对象关键字：出现则说明是解析噪声而非正文


def normalize_extracted_text(text: str) -> str:  # 规范化清洗 PDF 抽取出的单页文本
    """规范化清洗抽取文本：去水印、去中文间多余空格、压缩空白与空行。"""
    normalized = str(text or "")  # 安全转为字符串，None 视为空串
    # 逐个去掉已知水印文案。
    for pattern in WATERMARK_PATTERNS:  # 遍历每条水印正则
        normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE)  # 不区分大小写替换为空
    # 去掉两个汉字之间的多余空格（PDF 常在汉字间插空格）。
    normalized = re.sub(r"(?<=[\u4e00-\u9fff])[ \t]+(?=[\u4e00-\u9fff])", "", normalized)  # 仅删汉字之间的空白
    # 把连续的空白（空格/制表符等）压成单个空格。
    normalized = re.sub(r"[ \t\r\f\v]+", " ", normalized)  # 同行内多余空白合并
    # 把 3 个以上连续换行压成 2 个（即最多空一行）。
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)  # 限制段落间空行数量
    return normalized.strip()  # 去掉首尾空白后返回


def is_noise_chunk(text: str) -> bool:  # 判断文本片段是否为应丢弃的噪声
    """判断一个片段是否为噪声（空内容、PDF 对象乱码、或不含任何有效字符）。"""
    value = str(text or "").strip()  # 去首尾空白后的正文
    if not value:  # 空串直接视为噪声
        return True
    if any(marker in value for marker in PDF_OBJECT_MARKERS):  # 含 PDF 内部对象标记则为乱码
        return True
    return not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", value)  # 无任何中英文或数字则视为无效片段


def split_book_documents(documents: list[Document], max_chars: int = 1200, overlap_chars: int = 120) -> list[Document]:  # 清洗并按语义切分整页文档
    """把整页文档清洗后，按语义边界切成带重叠的小片段。

    参数:
        max_chars: 每个片段最大字符数。
        overlap_chars: 相邻片段的重叠字符数（保留上下文，避免语义被切断）。
    """
    # 第一步：逐页清洗，丢弃噪声页。
    cleaned_documents: list[Document] = []  # 清洗后、待切分的文档列表
    for document in documents:  # 遍历原始按页加载的 Document
        text = normalize_extracted_text(document.page_content)  # 对单页正文做规范化清洗
        if not text or is_noise_chunk(text):  # 空页或噪声页跳过
            continue
        cleaned_documents.append(Document(page_content=text, metadata=base_node_metadata(document)))  # 保留清洗后正文与元数据

    # 第二步：RecursiveCharacterTextSplitter 按 separators 从粗到细尝试切分，
    # 尽量在段落/句号处断开，而不是硬截到 chunk_size 中间打断语义。
    # chunk_overlap 让相邻片段有重叠，检索时边界附近的句子不易丢上下文。
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chars,  # 单片段最大字符数
        chunk_overlap=overlap_chars,  # 相邻片段重叠字符数，保留上下文衔接
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],  # 切分优先级：先段落再句子再字词
    )

    return [chunk for chunk in splitter.split_documents(cleaned_documents) if chunk.page_content.strip()]  # 切分后过滤空片段


def base_node_metadata(document: Document) -> dict[str, Any]:  # 从原页 metadata 派生切分片段的 metadata
    """从原文档 metadata 派生片段 metadata，补齐 page_start/page_end 页码字段。"""
    metadata = dict(document.metadata or {})  # 复制原页 metadata，避免原地修改
    page = metadata.get("page")  # PyPDFLoader 通常写入的 0-based 或 1-based 页码
    metadata.setdefault("page_start", page)  # 片段起始页，供 DOCUMENT_PROMPT_TEMPLATE 引用
    metadata.setdefault("page_end", page)  # 片段结束页（整页切分前与起始页相同）
    return metadata  # 返回供切分后 Document 使用的 metadata 字典
