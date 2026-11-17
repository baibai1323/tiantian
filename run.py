"""天天记账 启动入口。

用法：
    python run.py            # 正式模式：启动内置服务并打开桌面窗口
    python run.py --dev      # 开发模式：后端跑在 8000，窗口指向 Vite 的 5173
    python run.py --no-window  # 只启动后端（调试接口用）
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(__file__).resolve().parent
BASE_DIR = Path(getattr(sys, "_MEIPASS", ROOT)) if FROZEN else ROOT
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

# 打包成无控制台的窗口程序后，sys.stdout / sys.stderr 会是 None。
# uvicorn 配置日志格式时会调用 sys.stderr.isatty()，None 会直接崩溃，
# 因此这里先接上“空设备”，让日志安静地丢弃。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

if not FROZEN and str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

WINDOW_TITLE = "天天记账"


def _log_file() -> Path | None:
    bases = (os.environ.get("LOCALAPPDATA"), os.environ.get("TEMP"), str(Path.home()))
    for base in bases:
        if not base:
            continue
        try:
            folder = Path(base) / "TianTianJiZhang"
            folder.mkdir(parents=True, exist_ok=True)
            return folder / "startup.log"
        except OSError:
            continue
    return None


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    path = _log_file()
    if path is not None:
        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass
    if sys.stdout is not None:
        print(message, flush=True)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def start_server(port: int) -> "uvicorn.Server":
    import uvicorn

    from app.main import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="tiantian-api", daemon=True)
    thread.start()
    return server


def open_in_browser(url: str) -> None:
    log("已在系统默认浏览器中打开。")
    try:
        webbrowser.open(url)
    except Exception as exc:  # pragma: no cover - 极端环境兜底
        log(f"浏览器打开失败：{exc}")
    block_forever()


def open_window(url: str, debug: bool = False) -> None:
    try:
        import webview
    except ImportError:
        log("未安装 pywebview，改用浏览器打开。")
        open_in_browser(url)
        return

    try:
        webview.create_window(
            WINDOW_TITLE,
            url,
            width=1200,
            height=800,
            min_size=(880, 620),
            background_color="#faf7f2",
            text_select=True,
        )
        webview.start(debug=debug)
    except Exception as exc:
        log(f"桌面窗口启动失败：{exc}")
        open_in_browser(url)


def block_forever() -> None:
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def main() -> int:
    multiprocessing.freeze_support()
    log(f"启动：frozen={FROZEN}，dist={FRONTEND_DIST}")

    parser = argparse.ArgumentParser(description="天天记账")
    parser.add_argument("--dev", action="store_true", help="开发模式：后端 8000，前端连 Vite 5173")
    parser.add_argument("--no-window", action="store_true", help="只启动后端，不开窗口")
    parser.add_argument("--debug", action="store_true", help="打开 webview 调试工具")
    args = parser.parse_args()

    if not args.dev and not FRONTEND_DIST.is_dir():
        log("还没有构建前端。请先执行：")
        log("    cd frontend && npm install && npm run build")
        log("或使用开发模式：python run.py --dev")
        return 1

    port = 8000 if args.dev else find_free_port()
    log(f"使用端口：{port}")
    server = start_server(port)

    if not wait_for_server(port):
        log("后端启动失败，请检查依赖是否安装完整。")
        server.should_exit = True
        return 1

    url = "http://127.0.0.1:5173" if args.dev else f"http://127.0.0.1:{port}"
    log(f"天天记账 已启动：{url}")

    if args.no_window:
        block_forever()
    else:
        log("准备打开桌面窗口")
        open_window(url, debug=args.debug)
        log("桌面窗口已关闭")

    server.should_exit = True
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        log("启动失败：\n" + traceback.format_exc())
        raise
