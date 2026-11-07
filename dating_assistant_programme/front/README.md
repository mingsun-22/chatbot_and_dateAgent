# 约会助手 Web UI

这是 FastAPI + LangGraph 后端对应的独立 React 前端，主要负责对话输入、流式消息展示和最终方案卡片复用。

## 启动

先启动 Python API：

```bash
uvicorn api.main:app --reload --port 8000
```

再启动前端：

```bash
cp .env.example .env
npm install
npm run dev
```

打开 `http://127.0.0.1:5174`，点击“新建约会”即可开始一轮对话。

## 配置

前端必须通过 `VITE_API_BASE_URL` 配置独立后端地址：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

生产构建时可创建 `.env.production`，填写生产后端地址，然后执行：

```bash
npm run build
```

将生成的 `dist/` 部署到独立 Web 服务器。FastAPI 不会托管该目录。

品牌资源位于 `public/branding/`。
