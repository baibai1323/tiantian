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
if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    BASE_DIR = Path(__file__).resolve().parents[2]

FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title=f"{APP_DISPLAY_NAME} API", version=APP_VERSION, lifespan=lifespan)

# 开发时前端跑在 5173，允许跨域；正式打包后同源，不受影响。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(categories.router)
app.include_router(expenses.router)
app.include_router(stats.router)
app.include_router(export.router)
app.include_router(importer.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "name": APP_DISPLAY_NAME,
        "version": APP_VERSION,
        "data_dir": str(DATA_DIR),
    }


if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    """把非 /api 的路径都交给前端路由（刷新页面不会 404）。"""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="接口不存在")

    if FRONTEND_DIST.is_dir():
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)

    raise HTTPException(
        status_code=503,
        detail="前端尚未构建。开发模式请访问 http://127.0.0.1:5173，或先执行 npm run build。",
    )
