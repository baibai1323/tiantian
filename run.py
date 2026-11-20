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

# FROZEN 记录“当前代码是不是被 PyInstaller 打包成了 exe”。
# 打包后 Python 解释器和源码被塞进同一个可执行文件，运行时 sys.frozen 才是 True；
# 直接执行 python run.py 时没有这个属性，所以用 getattr 兜底成 False。
FROZEN = bool(getattr(sys, "frozen", False))
# ROOT 是 run.py 所在的目录，也就是“项目根目录”。resolve() 把相对路径变成绝对路径。
ROOT = Path(__file__).resolve().parent
# 打包后会出现 sys._MEIPASS：它是 PyInstaller 解压临时资源的目录，
# 打进去的前端 dist 就放在那里，所以优先用它；源码运行时没有它，退回项目根目录。
BASE_DIR = Path(getattr(sys, "_MEIPASS", ROOT)) if FROZEN else ROOT
# 后端 Python 包所在目录。开发时要把它加入 sys.path，否则 import app.main 会失败。
BACKEND_DIR = ROOT / "backend"
# 前端构建产物目录（npm run build 生成的 index.html、js、css 都在这里）。
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

# 打包成无控制台的窗口程序后，sys.stdout / sys.stderr 会是 None。
# uvicorn 配置日志格式时会调用 sys.stderr.isatty()，None 会直接崩溃，
# 因此这里先接上“空设备”，让日志安静地丢弃。
# 注意：这段必须在 import uvicorn 之前执行，否则读日志配置时就已经崩了。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# 开发模式把 backend 目录放到模块搜索路径最前面，
# 这样 backend/app 才能被当成顶层包 app 导入（与打包后的目录结构保持一致）。
if not FROZEN and str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 桌面窗口的标题栏文字。
WINDOW_TITLE = "天天记账"


def _log_file() -> Path | None:
    """找一个可写目录，返回启动日志 startup.log 的完整路径。

    返回：
        Path 对象；候选目录全都不可写时返回 None。
    """
    # 候选目录按“最可能可写”排序：Windows 的 LOCALAPPDATA、系统临时目录、用户主目录。
    bases = (os.environ.get("LOCALAPPDATA"), os.environ.get("TEMP"), str(Path.home()))
    for base in bases:
        if not base:
            continue
        try:
            folder = Path(base) / "TianTianJiZhang"
            # 目录不存在就创建；exist_ok=True 表示已存在时不报错。
            folder.mkdir(parents=True, exist_ok=True)
            return folder / "startup.log"
        except OSError:
            # 这个目录不可写（权限不足、路径失效）就换下一个，别让日志问题拖垮启动。
            continue
    # 一个都写不了时返回 None，调用方会跳过写文件这一步。
    return None


def log(message: str) -> None:
    """把一条带时间戳的消息写进日志文件，并尽量同时打印到标准输出。

    message: 要记录的文本。
    """
    # 时间戳精确到秒，方便对照“启动失败”发生在哪一步。
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    path = _log_file()
    if path is not None:
        try:
            # 用追加模式打开，多次启动的日志都会留在同一个文件里。
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            # 写盘失败（磁盘满、被杀毒软件占用等）时静默忽略，日志不能反过来弄崩程序。
            pass
    if sys.stdout is not None:
        # 传入 flush=True 让文字立刻输出，程序卡住时也能看到最后一行。
        print(message, flush=True)


def find_free_port() -> int:
    """向操作系统申请一个当前空闲的端口号并返回。

    返回：
        int 类型的端口号。
    """
    # 端口写 0 表示“让系统随便挑一个没人用的端口”：
    # 这样用户同时开两个实例、或 8000 被别的软件占用时都不会启动失败。
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        # getsockname() 返回 (地址, 端口)，取第二个元素就是系统分配的端口。
        return int(sock.getsockname()[1])


def wait_for_server(port: int, timeout: float = 20.0) -> bool:
    """轮询后端健康检查接口，直到服务就绪或超时。

    port: 后端监听的端口号。
    timeout: 最多等待多少秒，默认 20 秒。
    返回：
        True 表示接口返回 200；False 表示超时后仍不可用。
    """
    # deadline 是“截止时刻”：循环里不断拿当前时间和它比较。
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            # 把单次请求的超时设成 1 秒，防止某次请求卡死把整个等待流程拖长。
            with urllib.request.urlopen(url, timeout=1) as response:
                # HTTP 200 是“请求成功”的标准状态码，说明后端已经能正常响应。
                if response.status == 200:
                    return True
        except Exception:
            # 服务还没起来时连接会被拒绝，这是预期内的，歇 0.2 秒再试。
            time.sleep(0.2)
    return False


def start_server(port: int) -> "uvicorn.Server":
    """在后台线程里启动 FastAPI 后端，并立刻返回 uvicorn 的 Server 对象。

    port: 后端要监听的端口。
    返回：
        uvicorn.Server 实例，调用方可以用 should_exit 通知它退出。
    """
    # 延迟 import：只有真要启动服务时才加载 uvicorn 和业务代码，
    # 这样 --help 之类的路径更快，也避免打包时提前加载重量级依赖。
    import uvicorn

    from app.main import app

    # 日志级别用 warning、并关掉访问日志：桌面应用不需要把每个请求都打到控制台。
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    # 创建线程时传 daemon=True：主线程（窗口）退出时这个线程会自动结束，不会把进程挂住。
    thread = threading.Thread(target=server.run, name="tiantian-api", daemon=True)
    thread.start()
    return server


def open_in_browser(url: str) -> None:
    """用系统默认浏览器打开页面，并让主线程一直挂着不退出。

    url: 要打开的地址。
    """
    log("已在系统默认浏览器中打开。")
    try:
        webbrowser.open(url)
    except Exception as exc:  # pragma: no cover - 极端环境兜底
        log(f"浏览器打开失败：{exc}")
    # 浏览器是独立进程，Python 这边如果没有阻塞代码会立刻退出，
    # 后端线程也会跟着结束，页面就打不开了，所以这里必须一直等待。
    block_forever()


def open_window(url: str, debug: bool = False) -> None:
    """打开 pywebview 桌面窗口；失败时自动降级为浏览器。

    url: 窗口要加载的地址。
    debug: 是否开启 webview 调试工具（开发时用）。
    """
    try:
        # 延迟 import：没装 pywebview 时也能走浏览器方案。
        import webview
    except ImportError:
        log("未安装 pywebview，改用浏览器打开。")
        open_in_browser(url)
        return

    try:
        webview.create_window(
            WINDOW_TITLE,
            url,
            # 初始窗口尺寸和最小尺寸：保证侧边栏加内容区不会被挤变形。
            width=1200,
            height=800,
            min_size=(880, 620),
            # 背景色和应用主色一致，避免窗口打开瞬间闪一下白屏。
            background_color="#faf7f2",
            # 允许用户选中并复制页面上的文字（桌面窗口默认常常不能选）。
            text_select=True,
        )
        # webview.start() 会阻塞当前线程，直到用户关掉窗口才返回。
        webview.start(debug=debug)
    except Exception as exc:
        # 窗口创建失败（比如系统缺 WebView2 运行库）不该让用户什么都看不到，
        # 退回到浏览器至少还能继续用。
        log(f"桌面窗口启动失败：{exc}")
        open_in_browser(url)


def block_forever() -> None:
    """让主线程无限期休眠，直到用户按 Ctrl+C 中断。"""
    try:
        # 睡 3600 秒只是“睡很久”的意思，实际会被 Ctrl+C 立刻打断。
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        # 用户主动中断属于正常退出，不用打印错误。
        pass


def main() -> int:
    """解析命令行参数、启动后端，并按模式打开窗口或浏览器。

    返回：
        进程退出码，0 表示正常结束，1 表示启动失败。
    """
    # PyInstaller 打包后，multiprocessing 在 Windows 上会重新导入主模块；
    # freeze_support() 用来拦住这次重复执行，避免窗口被打开两次。
    multiprocessing.freeze_support()
    log(f"启动：frozen={FROZEN}，dist={FRONTEND_DIST}")

    # argparse 负责把命令行里的 --dev / --no-window / --debug 解析成布尔开关。
    parser = argparse.ArgumentParser(description="天天记账")
    parser.add_argument("--dev", action="store_true", help="开发模式：后端 8000，前端连 Vite 5173")
    parser.add_argument("--no-window", action="store_true", help="只启动后端，不开窗口")
    parser.add_argument("--debug", action="store_true", help="打开 webview 调试工具")
    args = parser.parse_args()

    # 正式模式必须有构建好的前端；没有就提示用户去 build，而不是打开一个空白窗口。
    if not args.dev and not FRONTEND_DIST.is_dir():
        log("还没有构建前端。请先执行：")
        log("    cd frontend && npm install && npm run build")
        log("或使用开发模式：python run.py --dev")
        return 1

    # 开发模式固定 8000：前端 Vite 的代理写死了这个端口，必须对上。
    # 正式模式用系统分配的空闲端口，避免和用户电脑上别的服务撞车。
    port = 8000 if args.dev else find_free_port()
    log(f"使用端口：{port}")
    server = start_server(port)

    # 后端线程是异步启动的，必须等健康检查通过再开窗口，否则窗口会先显示“连接失败”。
    if not wait_for_server(port):
        log("后端启动失败，请检查依赖是否安装完整。")
        server.should_exit = True
        return 1

    # 开发模式页面由 Vite 开发服务器（5173）提供，正式模式由后端自己托管静态文件。
    url = "http://127.0.0.1:5173" if args.dev else f"http://127.0.0.1:{port}"
    log(f"天天记账 已启动：{url}")

    if args.no_window:
        # 不开窗口时也要阻塞住，否则主线程一结束就会把后端线程一起带走。
        block_forever()
    else:
        log("准备打开桌面窗口")
        open_window(url, debug=args.debug)
        log("桌面窗口已关闭")

    # 走到这里说明窗口已经关闭：通知 uvicorn 停止，进程才能干净退出。
    server.should_exit = True
    return 0


# 只有直接运行本文件时才执行启动流程；被其他模块 import 时不会自动启动。
if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:
        # 这里捕获所有异常，是为了先把完整堆栈写进日志再往外抛：
        # 窗口模式下用户看不到控制台，日志文件是唯一能查到的现场。
        log("启动失败：\n" + traceback.format_exc())
        raise
