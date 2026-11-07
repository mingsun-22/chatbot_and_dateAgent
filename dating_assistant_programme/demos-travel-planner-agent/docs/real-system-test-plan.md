# 真实环境系统测试文档

本文档沉淀当前后端全链路真实环境测试方案。测试不使用 mock，不重建情感书籍索引，直接访问 `.env` 中配置的 Qwen、Tavily、高德地图、Redis 和 Chroma。

## 测试范围

- 情感咨询：书籍路由、章节摘要路由、Chroma 检索、LLM 流式回答、Redis 会话记忆。
- 约会规划：LangGraph interrupt/resume、天气、地理编码、交通、活动/餐饮搜索、方案生成、不满意后重规划。
- API：约会线程接口、情感咨询 SSE 流式接口。
- 不覆盖浏览器 UI 自动化，不执行索引重建。

## 环境要求

运行前确认 `.env` 已包含真实配置：

- `DASHSCOPE_API_KEY`
- `QWEN_MODEL`
- `QWEN_BASE_URL`
- `TAVILY_API_KEY`
- `AMAP_API_KEY`
- `CHROMA_HOST`
- `CHROMA_PORT`
- `REDIS_URL`

运行命令：

```powershell
python -m unittest discover -s tests/real -p "test_*.py"
```

单独运行：

```powershell
python -m unittest tests.real.test_environment_real
python -m unittest tests.real.test_emotion_real
python -m unittest tests.real.test_date_agent_real
python -m unittest tests.real.test_api_real
```

## 测试案例

### 环境预检

| 编号 | 场景 | 输入/操作 | 预期 |
| --- | --- | --- | --- |
| ENV-01 | 配置完整性 | 读取 `core.settings` | 真实环境必要配置均存在 |
| ENV-02 | Redis 可用 | `PING` | 返回成功 |
| ENV-03 | Chroma 可用 | `heartbeat/list_collections` | 能连接远端 Chroma |
| ENV-04 | 高德地理编码 | 查询“杭州湖滨” | 返回合法经纬度 |
| ENV-05 | Qwen 可用 | 简短问答 | 返回非空中文内容 |

### 情感咨询

| 编号 | 场景 | 输入/操作 | 预期 |
| --- | --- | --- | --- |
| EMO-01 | 第八章黄灯信号召回 | “忽冷忽热是不是黄灯信号？” | 命中《科学脱单指南》第八章，section 包含“对你的态度非常不稳定” |
| EMO-02 | 过去感情经历召回 | “对方不愿意说过去的感情经历，这正常吗？” | 前几个结果包含“回避谈论过去的感情经历” |
| EMO-03 | 第九章沟通召回 | “确立关系后总是吵架，怎么有效沟通？” | top 结果来自第九章 |
| EMO-04 | 流式聊天 | 调用 `EmotionRagService.stream_chat` | 返回 `ready/route/delta/sources/done`，sources 有真实书籍片段 |
| EMO-05 | Redis 滑动窗口 | 写入超过 15 条消息并触发裁剪 | 真实 Redis 中只保留 15 条 |

### 约会规划

| 编号 | 场景 | 输入/操作 | 预期 |
| --- | --- | --- | --- |
| DATE-01 | 首次规划 | 杭州湖滨、明天下午、半天、打车、安静咖啡/湖边散步/晚餐 | 完成天气、交通、活动、餐饮、方案生成 |
| DATE-02 | 不满意重规划 | 首版后回复“不满意”，原因“节奏太赶，不要网红餐厅，希望同一商圈” | 记录反馈约束并重新生成方案 |
| DATE-03 | 最终确认 | 重规划后回复“满意” | 生成 `final_message`，最终 state 可读 |

### API

| 编号 | 场景 | 输入/操作 | 预期 |
| --- | --- | --- | --- |
| API-01 | 约会线程 | `POST /api/date/threads`、`GET /api/date/threads/{id}/state` | 线程创建成功，状态接口可读 |
| API-02 | 情感 SSE | `POST /api/emotion/chat/stream` | SSE 中包含 delta、sources、done |

## 验收标准

- 所有真实测试通过，或失败项能明确指向外部依赖、额度、网络、索引或业务逻辑问题。
- 测试不会清空或重建 Chroma collection。
- 测试结束后清理 `codex-real-test-*` 相关 Redis 会话 key。
- 每个长链路测试打印耗时，方便后续定位慢节点。

## 最近执行结果

执行时间：2026-05-12

命令：

```powershell
python -m unittest discover -s tests/real -p "test_*.py"
```

结果：11 个测试全部通过。

耗时摘要：

| 测试项 | 耗时 |
| --- | ---: |
| API 情感 SSE | 13725 ms |
| API 恋爱报告 PDF | 65267 ms |
| 约会规划完整重规划链路 | 68005 ms |
| 情感第八章召回 | 14225 ms |
| 情感第九章召回 | 3315 ms |
| 情感流式聊天 | 13950 ms |
| 情感 Tool Calling 恋爱报告 | 77641 ms |
| 环境预检 | 2272 ms |
| 总测试耗时 | 253.691 s |

观察到的非阻塞 warning：

- `RunnableWithMessageHistory is deprecated`：现有情感会话记忆实现仍可用，后续可迁移到 LangGraph persistence。
- `LangChainPendingDeprecationWarning`：LangGraph checkpointer 序列化默认值未来会变化，不影响当前测试。
