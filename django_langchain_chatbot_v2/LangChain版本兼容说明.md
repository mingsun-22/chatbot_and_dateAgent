# LangChain 版本兼容说明

## 当前支持的版本

本项目已针对以下 LangChain 版本进行优化和测试：

```
langchain                    >= 0.3.0
langchain-chroma             >= 0.1.4
langchain-community          >= 0.3.0
langchain-core               >= 0.3.0
langchain-openai             >= 0.2.0
langchain-text-splitters     >= 0.3.0
```

### 已验证的版本组合

✅ **推荐配置**（已测试）:
```
langchain                    0.3.7
langchain-chroma             0.1.4
langchain-community          0.3.7
langchain-core               0.3.63
langchain-experimental       0.3.3
langchain-openai             0.2.9
langchain-text-splitters     0.3.8
```

## 主要变更说明

### LangChain 0.3.x 的重要变化

#### 1. 检索器调用方式

**旧版本 (0.2.x)**:
```python
docs = retriever.get_relevant_documents(question)
```

**新版本 (0.3.x)** - 推荐使用:
```python
docs = retriever.invoke(question)
```

**本项目实现** - 兼容两种方式:
```python
try:
    docs = retriever.invoke(question)  # 优先使用新方法
except AttributeError:
    docs = retriever.get_relevant_documents(question)  # 兼容旧版本
```

#### 2. 消息类导入

**统一导入路径**:
```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
```

不再需要从多个地方导入消息类。

#### 3. 文档类导入

**旧版本**:
```python
from langchain.docstore.document import Document
```

**新版本**:
```python
from langchain_core.documents import Document
```

#### 4. 文本分割器导入

**旧版本**:
```python
from langchain.text_splitter import CharacterTextSplitter
```

**新版本**:
```python
from langchain_text_splitters import CharacterTextSplitter
```

## 代码适配详情

### rag.py 中的关键改动

#### 1. 导入部分
```python
# ✅ 正确的导入方式（LangChain 0.3.x）
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import CharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
```

#### 2. 消息构建
```python
# ✅ 直接创建消息对象
messages = []
messages.append(SystemMessage(content=system_prompt))

if chat_history:
    for msg in chat_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

messages.append(HumanMessage(content=question))
```

#### 3. LLM 调用
```python
# ✅ 使用 invoke 方法
response = llm.invoke(messages)
answer = response.content
```

## 向后兼容性

### 支持的最低版本

- **LangChain**: 0.3.0+
- **Python**: 3.8+
- **Django**: 4.2+

### 不兼容的版本

❌ **LangChain 0.2.x 及更早版本**
- 导入路径不同
- API 方法名称变化
- 需要大量代码修改

如果你使用的是 LangChain 0.2.x，建议升级到 0.3.x：

```bash
pip install --upgrade langchain langchain-core langchain-community langchain-openai langchain-text-splitters
```

## 常见问题

### Q1: 提示 "No module named 'langchain.text_splitter'"

**原因**: 使用了旧的导入路径

**解决方案**: 
```python
# 错误
from langchain.text_splitter import CharacterTextSplitter

# 正确
from langchain_text_splitters import CharacterTextSplitter
```

### Q2: 提示 "'Retriever' object has no attribute 'get_relevant_documents'"

**原因**: LangChain 0.3.x 中推荐使用 `invoke` 方法

**解决方案**: 
本项目已经实现了自动兼容，无需修改。如果仍有问题，请检查 LangChain 版本。

### Q3: 消息格式错误

**原因**: 直接传递字典而不是消息对象

**解决方案**:
```python
# 错误
messages = [{"role": "user", "content": "hello"}]

# 正确
from langchain_core.messages import HumanMessage
messages = [HumanMessage(content="hello")]
```

## 升级指南

### 从 LangChain 0.2.x 升级到 0.3.x

1. **备份项目**
```bash
git commit -am "Backup before LangChain upgrade"
```

2. **升级依赖**
```bash
pip install --upgrade -r requirements.txt
```

3. **测试功能**
```bash
python test_multiround_chat.py
```

4. **如有问题，检查导入**
- 确保所有导入使用新的路径
- 检查 API 调用方法是否正确

## 性能优化建议

### 1. 使用异步调用（可选）

LangChain 0.3.x 支持异步操作：

```python
# 异步版本
async def answer_with_rag_async(question: str, chat_history=None):
    # ... 其他代码 ...
    response = await llm.ainvoke(messages)
    return response.content
```

### 2. 批量处理

```python
# 批量调用
responses = llm.batch([messages1, messages2, messages3])
```

### 3. 流式输出

```python
# 流式生成回答
for chunk in llm.stream(messages):
    print(chunk.content, end="", flush=True)
```

## 测试清单

升级后请测试以下功能：

- [ ] FAISS 索引加载正常
- [ ] 单轮问答功能正常
- [ ] 多轮对话上下文正确
- [ ] 联系方式提取正常
- [ ] 负面反馈检测正常
- [ ] 会话历史保存正常
- [ ] 前端交互正常

## 相关资源

- [LangChain 官方文档](https://python.langchain.com/)
- [LangChain 0.3 迁移指南](https://python.langchain.com/docs/versions/v0_3/)
- [LangChain GitHub](https://github.com/langchain-ai/langchain)

## 版本历史

| 日期 | LangChain 版本 | 说明 |
|------|---------------|------|
| 2026-01-30 | 0.3.7 | 初始版本，支持多轮对话 |

---

**最后更新**: 2026-01-30  
**维护者**: AI Assistant

