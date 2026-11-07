# 导入操作系统模块，用于文件和路径操作
import os
# 导入OpenAI的嵌入模型，用于将文本转为向量
from langchain_openai import OpenAIEmbeddings
# 导入FAISS向量数据库，用于高效相似度检索
from langchain_community.vectorstores import FAISS
# 导入文本分割器，用于将长文本切分为小块
from langchain_text_splitters import CharacterTextSplitter
# 导入文档类，用于封装文本及其元数据
from langchain_core.documents import Document
# 导入OpenAI大语言模型

from dotenv import load_dotenv

# 获取项目根目录（当前文件的上两级目录）
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))
# 拼接FAISS索引文件保存路径
INDEX_PATH = os.path.join(BASE_DIR, 'faiss_index')


def load_faiss_index():
    # 如果索引目录不存在，抛出异常提示用户先构建索引
    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError('FAISS index not found. Please run `python manage.py build_faiss_index`')
    # 初始化OpenAI嵌入模型
    embeddings = OpenAIEmbeddings(
        model="text-embedding-v3",
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv("DASHSCOPE_BASE_URL"),
        check_embedding_ctx_length=False,
        chunk_size=10,  # text-embedding-v3 单次最多约 10 条
    )
    # 从本地加载FAISS索引
    db = FAISS.load_local(INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
    # 返回加载好的向量数据库
    return db


def answer_with_rag(question: str, chat_history=None):
    """
    使用RAG生成答案，支持多轮对话上下文
    
    Args:
        question: 用户当前问题
        chat_history: 对话历史列表，格式为 [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    
    Returns:
        (answer, sources): 答案和来源列表的元组
    """
    try:
        # 尝试加载FAISS索引
        db = load_faiss_index()
    except Exception as e:
        # 加载失败时返回中文提示及空列表
        return (f"知识库未构建，请联系管理员或运行构建脚本。{e}", [])

    # 将向量数据库转换为检索器，设置返回最相似的4个文档
    retriever = db.as_retriever(search_kwargs={'k': 4})

    # 初始化ChatOpenAI模型，temperature使用默认值1
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    llm = ChatOpenAI(
        model="qwen3.7-plus",
        temperature=1,
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv("DASHSCOPE_BASE_URL"),
    )

    # 检索相关文档
    try:
        docs = retriever.invoke(question)  # 使用 invoke 方法（LangChain 0.3.x 推荐）
    except AttributeError:
        docs = retriever.get_relevant_documents(question)  # 兼容旧版本

    context = "\n\n".join([doc.page_content for doc in docs])  # 将关联的文档列表转为字符串

    # 构建包含历史对话的消息列表
    messages = []

    # 添加系统提示
    system_prompt = f"""你是一个智能客服助手。请根据以下知识库内容回答用户问题。
    如果知识库中没有相关信息，请礼貌地告知用户。

    知识库内容：
    {context}

    请结合对话历史和知识库内容，给出准确、友好的回答。"""

    messages.append(SystemMessage(content=system_prompt))

    # 添加历史对话（保留最近10条消息，即5轮对话）
    if chat_history:
        recent_history = chat_history[-10:]  # 最多保留最近10条消息
        for msg in recent_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

    # 添加当前问题
    messages.append(HumanMessage(content=question))

    # 调用LLM生成回答
    response = llm.invoke(messages)
    answer = response.content

    # 返回答案及来源标识列表
    return (answer, ['local_faiss'])


def build_index_from_folder(folder='data/docs'):
    # 动态导入glob模块，用于递归匹配文件
    import glob
    # 递归获取指定目录下所有txt文件路径
    files = glob.glob(os.path.join(folder, '**', '*.txt'), recursive=True)
    # 用于存储所有文本内容
    texts = []
    # 用于存储对应的元数据（文件路径）
    metadatas = []
    # 遍历每个txt文件
    for f in files:
        # 以UTF-8编码打开文件
        with open(f, 'r', encoding='utf-8') as fh:
            # 读取完整文本
            txt = fh.read()
            # 将文本加入列表
            texts.append(txt)
            # 将文件路径，包含文件名作为元数据加入列表
            metadatas.append({'source': f})

    # 初始化字符级文本分割器，每块1000字符，重叠200字符
    splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    # 用于存储分割后的文档对象
    docs = []
    # 遍历文本与元数据
    for t, m in zip(texts, metadatas):
        # 对每段文本进行分割
        for i, chunk in enumerate(splitter.split_text(t)):
            # 创建Document对象，记录块内容、源文件路径及块序号
            docs.append(Document(page_content=chunk, metadata={**m, 'chunk': i}))

    # 初始化OpenAI嵌入模型
    embeddings = OpenAIEmbeddings(
        model="text-embedding-v3",
        api_key=os.getenv("DASHSCOPE_API_KEY"), 
        base_url=os.getenv("DASHSCOPE_BASE_URL"),
        check_embedding_ctx_length=False,
        chunk_size=10,  # text-embedding-v3 单次最多约 10 条
    )
    # 将文档列表转为FAISS向量数据库
    db = FAISS.from_documents(docs, embeddings)
    # 如果索引目录不存在，则创建
    if not os.path.exists(INDEX_PATH):
        os.makedirs(INDEX_PATH)
    # 将FAISS索引保存到本地
    db.save_local(INDEX_PATH)
    # 返回构建的文档总数
    return len(docs)
