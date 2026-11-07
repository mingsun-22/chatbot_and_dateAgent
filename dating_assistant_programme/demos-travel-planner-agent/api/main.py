"""FastAPI 应用入口。

这是整个后端的启动点：`uvicorn api.main:app` 里的 `app` 就是这里创建的实例。
职责：
1. 创建 FastAPI 应用；
2. 配置 CORS（允许前端跨域访问）；
3. 挂载两个业务路由：情感咨询（emotion）和约会规划（date）。
"""

from __future__ import annotations  # 启用延迟注解求值，允许用 str 等前向引用类型

from fastapi import FastAPI  # FastAPI 框架核心类，用于创建 Web 应用
from fastapi.middleware.cors import CORSMiddleware  # 跨域资源共享中间件

from api.date_routes import router as date_router  # 约会规划相关路由
from api.emotion_routes import router as emotion_router  # 情感咨询相关路由


# 创建应用实例，title 会显示在自动生成的 /docs 文档里。
app = FastAPI(title="Dating Assistant Agent API")  # 全局 FastAPI 应用对象，uvicorn 启动时引用此变量

# 配置跨域中间件：前端（如 http://127.0.0.1:5174）与后端端口不同，属于跨域请求，
# 这里放开所有来源/方法/头，方便本地教学联调（生产环境应收紧 allow_origins）。
app.add_middleware(  # 向应用注册中间件，请求会先经过 CORS 再进入路由
    CORSMiddleware,  # 使用 Starlette 提供的 CORS 中间件类
    allow_origins=["*"],  # 允许任意来源的跨域请求（本地开发方便，生产应改为具体域名列表）
    allow_credentials=False,  # 不允许携带 Cookie 等凭证（与 allow_origins=["*"] 配合使用）
    allow_methods=["*"],  # 允许所有 HTTP 方法（GET/POST/PUT/DELETE 等）
    allow_headers=["*"],  # 允许前端发送任意请求头
)


# 挂载业务路由。每个 router 内部已带好各自的路径前缀（/api/emotion、/api/date）。
app.include_router(emotion_router)  # 注册情感咨询接口到主应用
app.include_router(date_router)  # 注册约会规划接口到主应用
