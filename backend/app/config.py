"""全局配置：数据目录、数据库位置、应用常量。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "TianTianJiZhang"
APP_DISPLAY_NAME = "天天记账"
APP_VERSION = "0.4.0"


def default_data_dir() -> Path:
    """按操作系统惯例返回存放数据的目录。

    允许用环境变量 TIANTIAN_DATA_DIR 覆盖（开发、测试时很方便）。
    """
    override = os.environ.get("TIANTIAN_DATA_DIR")
    if override:
        return Path(override).expanduser()

    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        return base / APP_NAME
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / APP_NAME


DATA_DIR = default_data_dir()
DB_PATH = DATA_DIR / "tiantian.db"
BACKUP_DIR = DATA_DIR / "backups"
