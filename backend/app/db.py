"""数据库引擎、建表、启动备份。"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from .config import BACKUP_DIR, DATA_DIR, DB_PATH
from .models import Setting
from .seed import seed_categories
from .utils import iso_now

SCHEMA_VERSION = 1
MAX_BACKUPS = 7

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _backup_existing_db() -> Path | None:
    """启动时把已有数据库复制一份到 backups/，只保留最近 7 份。

    备份是“锦上添花”，失败（杀软占用、权限、磁盘满）不能阻止应用启动。
    """
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return None
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = BACKUP_DIR / f"tiantian-{stamp}.db"
        shutil.copy2(DB_PATH, target)

        backups = sorted(BACKUP_DIR.glob("tiantian-*.db"))
        for old in backups[:-MAX_BACKUPS]:
            old.unlink(missing_ok=True)
        return target
    except OSError as exc:  # 备份失败只提示，不中断启动
        print(f"启动备份失败（不影响使用）：{exc}", file=sys.stderr)
        return None


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _backup_existing_db()
    SQLModel.metadata.create_all(engine)
    now = iso_now()
    with Session(engine) as session:
        seed_categories(session, now)
        record = session.get(Setting, "schema_version")
        if record is None:
            session.add(Setting(key="schema_version", value=str(SCHEMA_VERSION)))
            session.commit()


def get_session():
    with Session(engine) as session:
        yield session
