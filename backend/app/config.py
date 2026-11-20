"""全局配置：数据目录、数据库位置、应用常量。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 应用内部标识：用来拼数据目录名（例如 Windows 下的 %APPDATA%\TianTianJiZhang）。
# 它必须是纯英文、无空格，才能直接当文件夹名和安装包名使用。
APP_NAME = "TianTianJiZhang"
APP_DISPLAY_NAME = "天天记账"
APP_VERSION = "0.5.1"


# 数据目录集中在这里决定：数据库、备份都放在它下面，
# 这样备份/迁移时只要搬这一个文件夹。不用“当前工作目录”，
# 是因为双击启动时工作目录可能是任意位置，数据会跟着乱跑。
def default_data_dir() -> Path:
    """按操作系统惯例返回存放数据的目录。

    允许用环境变量 TIANTIAN_DATA_DIR 覆盖（开发、测试时很方便）。
    """
    # 环境变量优先：开发时把数据指到临时目录，测试就不会污染真实账本。
    override = os.environ.get("TIANTIAN_DATA_DIR")
    if override:
        return Path(override).expanduser()

    # 没设环境变量时，按各系统“用户数据”的惯例位置存放；
    # Path.home() 是当前用户的主目录（Windows 下形如 C:\Users\张三）。
    home = Path.home()
    # Windows 惯例是 %APPDATA%（漫游配置目录）；取不到就退回主目录下的默认路径。
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        return base / APP_NAME
    # macOS 惯例是 ~/Library/Application Support，苹果要求应用数据放这里。
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    # Linux 等类 Unix 系统遵循 XDG 规范：优先 $XDG_DATA_HOME，否则 ~/.local/share。
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / APP_NAME


# 下面三个路径在模块导入时就算好，整个进程共用同一份，
# 避免运行中因为环境变量变化，出现“数据库在这里、备份在那里”的情况。
DATA_DIR = default_data_dir()
DB_PATH = DATA_DIR / "tiantian.db"
BACKUP_DIR = DATA_DIR / "backups"
