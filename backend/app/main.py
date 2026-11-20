"""FastAPI 应用入口。

开发时：uvicorn app.main:app --reload（在 backend 目录下执行）
正式时：由根目录 run.py 启动，并用 PyWebView 开窗口。
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import APP_DISPLAY_NAME, APP_VERSION, DATA_DIR
from .db import init_db
from .routers import categories, expenses, export, importer, stats

# 开发时：<项目根>/frontend/dist；PyInstaller 打包后：<解包目录>/frontend/dist
# 两种运行方式的“根目录”不同：源码运行时是仓库根目录，
# PyInstaller 打包后代码被解到临时目录（_MEIPASS），前端静态文件也放在那儿。
if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    BASE_DIR = Path(__file__).resolve().parents[2]

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用启动/关闭的钩子（FastAPI 的 lifespan 机制）。

    参数 _app：FastAPI 应用实例，这里用不到，下划线开头表示故意忽略。
    返回：异步生成器；yield 之前做启动初始化，之后可做清理（当前没有清理动作）。
    """
    # 建表、备份、灌预置分类放在这里而不是模块导入时，
    # 是为了让测试可以先改环境变量，再创建应用。
    init_db()
    yield


# title / version 会显示在 /docs 自动生成的接口文档页面上。
app = FastAPI(title=f"{APP_DISPLAY_NAME} API", version=APP_VERSION, lifespan=lifespan)

# 开发时前端跑在 5173，允许跨域；正式打包后同源，不受影响。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 各业务路由统一挂在 /api 前缀下（前缀在 routers/*.py 里定义），
# 这样接口路径和前端静态页面不会抢同一个地址。
app.include_router(categories.router)
app.include_router(expenses.router)
app.include_router(stats.router)
app.include_router(export.router)
app.include_router(importer.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    """健康检查接口，前端启动时用它确认后端已经就绪。

    返回：包含状态、应用名、版本号和数据目录的字典；带上数据目录，
    是为了让用户能直接找到自己的账本文件。
    """
    # 返回普通字典即可，前端只关心 status 是不是 "ok"。
    return {
        "status": "ok",
        "name": APP_DISPLAY_NAME,
        "version": APP_VERSION,
        "data_dir": str(DATA_DIR),
    }


# 前端构建产物存在时才挂静态资源；没构建时跳过，开发模式直接走 Vite 的 5173 端口。
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    """把非 /api 的路径都交给前端路由（刷新页面不会 404）。"""
    # /api 开头的路径是接口，没匹配到就该返回 404，不能回退成 index.html；
    # 否则前端会把一段 HTML 当成 JSON 解析，报错信息很难懂。
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="接口不存在")

    if FRONTEND_DIST.is_dir():
        # 先看请求的路径是不是真实存在的静态文件（如 favicon.ico），是就直接返回。
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # 其余路径（如 /stats）都交给前端路由，刷新页面才不会 404。
        index = FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)

    # 连 index.html 都没有，说明前端还没构建；503 比 404 更能提示“服务尚未就绪”。
    raise HTTPException(
        status_code=503,
        detail="前端尚未构建。开发模式请访问 http://127.0.0.1:5173，或先执行 npm run build。",
    )
