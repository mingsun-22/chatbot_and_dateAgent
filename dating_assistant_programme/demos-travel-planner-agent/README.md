# 约会助手 Agent (LangGraph + FastAPI + React)

这是一个中文约会方案助手示例。后端使用 LangGraph 编排，对外通过 FastAPI 暴露流式接口，前端使用 React + Vite 复用现有聊天界面。

它适合演示带 human-in-the-loop 的状态机流程、流式响应、interrupt / resume、天气查询、地点检索和酒店候选推荐。

## 这个 Agent 做什么

图 `travel_planner`（保留为兼容旧名）定义在 `agent/graph.py` 中，当前流程是：

1. 先收集约会地点、日期和时长。
   - “今天/明天/后天/本周六/下周六”等相对日期会优先用 `jionlp` 按 `Asia/Shanghai` 当前日期解析。
   - “周末/本周末/下周末”不会默认成周六，会追问用户确认周六还是周日。
   - 半天或一天由模型根据用户整体表达判断，后端只校验结构化结果。
2. 并行推测出发地候选。
3. 必要时追问真实出发地。
4. 拉取天气和穿搭建议。
5. 询问出行方式、是否外住和约会偏好。
6. 结合约会地点做地理编码，生成出行建议。
7. 分别搜索适合约会的活动候选、餐饮候选。
8. 如果需要外住，再搜索酒店候选。
9. 生成完整约会方案，并在结尾询问是否满意。
10. 如果不满意，追问原因，抽取“必须避开 / 倾向偏好 / 必须满足 / 需要重查范围”，按需刷新活动、餐饮、酒店、交通或天气信息后重新生成。

## 技术栈

- Agent: Python, LangGraph, LangChain
- API: FastAPI, SSE 风格流式响应
- LLM: Qwen via DashScope OpenAI-compatible API
- 搜索: Tavily
- Geocoding: AMap API via `httpx`
- 中文时间解析: JioNLP
- Web UI: React, TypeScript, Vite, Tailwind CSS

## 安装

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

把 `.env.example` 复制为 `.env`，并填写：

- `DASHSCOPE_API_KEY`
- `TAVILY_API_KEY`

可选项：

- `QWEN_MODEL` 默认 `qwen-plus`
- `QWEN_BASE_URL` 默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`

占位符可以先用于联调，但真正跑 Agent 还是要换成真实 key。

## 本地运行

启动 Python API：

```bash
uvicorn api.main:app --reload --port 8000
```

启动前端：

```bash
cd web
cp .env.example .env
npm install
npm run dev
```

打开 `http://127.0.0.1:5174`。前端通过 `web/.env` 中的 `VITE_API_BASE_URL` 访问独立运行的 FastAPI。

## 独立部署

后端只提供 API，不托管前端静态文件。使用 `uvicorn api.main:app --host 0.0.0.0 --port 8000` 独立部署。

前端构建前，在 `web/.env.production` 中配置生产 API 地址：

```env
VITE_API_BASE_URL=https://api.example.com
```

然后执行 `cd web && npm run build`，将生成的 `web/dist` 部署到独立 Web 服务器。

## API 合同

前端依赖以下接口：

- `POST /api/date/threads`
- `GET /api/date/threads/{thread_id}/state`
- `POST /api/date/runs/stream-plan`
- `POST /api/date/runs/invoke`

前端右侧“流式响应”开关开启时使用 `stream-plan`，关闭时使用 `invoke`。

`/api/date/runs/stream-plan` 返回 SSE 风格事件：

```json
{"type":"node","name":"research_weather"}
{"type":"interrupt","value":"先告诉我这次约会的基本信息。","values":{},"interrupted":true}
{"type":"final","values":{"agenda":"..."},"interrupted":false}
{"type":"error","message":"..."}
```

最终约会方案统一从 `final.values.agenda` 渲染；中断时从 `interrupt.value` 展示追问，并可用 `interrupt.values` 同步已收集状态。


| 脚本 | 作用 |
|------|------|
| `python test_local.py` | 使用内存 checkpointer 在本地跑通 interrupt / resume 流程。 |
| `python test_deployed.py` | 旧版部署示例。 |
| `uvicorn api.main:app --reload --port 8000` | 启动本地 FastAPI API。 |
| `cd web && npm run dev` | 启动 React 前端。 |

## 目录结构

```text
agent/           # LangGraph 状态、节点和图构建
api/             # FastAPI 包装层
web/             # React + Vite + Tailwind 前端
langgraph.json   # LangGraph 工具用的图配置
requirements.txt # Python 依赖
```
