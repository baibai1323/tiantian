"""数据库引擎、建表、启动备份。"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from .config import BACKUP_DIR, DATA_DIR, DB_PATH
from .models import Setting
from .seed import seed_categories
from .utils import iso_now

# 数据库结构的版本号，写在 setting 表里；将来改表结构时据此判断要不要迁移。
SCHEMA_VERSION = 1
# 启动备份最多保留 7 份（大约一周的启动次数），更旧的自动删除，防止备份目录无限膨胀。
MAX_BACKUPS = 7

# 把 check_same_thread 设为 False：FastAPI 的请求可能在不同线程里共用连接池，
# 关掉 SQLite 默认的“只允许创建它的线程使用”检查，否则会报线程错误。
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    """给每个新建的数据库连接打开外键约束和 WAL 日志模式。

    参数 dbapi_connection：SQLAlchemy 建好的底层 sqlite3 连接对象。
    参数 _connection_record：连接池的记录对象，本函数用不到，下划线开头表示忽略。
    返回：None，只修改这个连接的 PRAGMA 设置，不返回数据。
    """
    cursor = dbapi_connection.cursor()
    # 外键约束默认是关的：不打开的话，写入不存在的分类 id 也会成功，数据就脏了。
    cursor.execute("PRAGMA foreign_keys=ON")
    # WAL（Write-Ahead Log，预写日志）让读写互不阻塞：记账时还能同时查列表；
    # 代价是会多出 tiantian.db-wal / tiantian.db-shm 两个文件，备份时必须用 backup API。
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _backup_existing_db() -> Path | None:
    """启动时把已有数据库备份一份到 backups/，只保留最近 7 份。

    用 sqlite3 的 backup API 而不是直接复制文件：WAL 模式下最近提交的数据
    可能还在 tiantian.db-wal 里，只复制主文件会得到一个缺数据的备份。
    备份是“锦上添花”，失败（杀软占用、权限、磁盘满）不能阻止应用启动。
    """
    # 文件不存在或是空文件（0 字节）说明是首次启动，没有可备份的内容。
    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        return None
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        # 时间戳精确到秒；同一秒内重复启动会覆盖同名文件，这在实践中可以接受。
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = BACKUP_DIR / f"tiantian-{stamp}.db"
        # 用 sqlite3 的 backup() 会连 WAL 里尚未合并进主文件的数据一起复制，
        # 得到一份一致的快照；直接复制 .db 文件可能丢最近的提交。
        with sqlite3.connect(DB_PATH) as source, sqlite3.connect(target) as dest:
            source.backup(dest)

        # 文件名带日期，按名字排序就是时间顺序；只保留最后 MAX_BACKUPS 份。
        backups = sorted(BACKUP_DIR.glob("tiantian-*.db"))
        for old in backups[:-MAX_BACKUPS]:
            old.unlink(missing_ok=True)
        return target
    except (OSError, sqlite3.Error) as exc:  # 备份失败只提示，不中断启动
        print(f"启动备份失败（不影响使用）：{exc}", file=sys.stderr)
        return None


def init_db() -> None:
    """应用启动时初始化数据库：建目录、备份旧库、建表、灌预置分类。

    返回：None。重复调用是安全的：建表语句本身幂等，
    预置分类只在分类表为空时才写入（是否为空由 seed.py 判断）。
    """
    # 先确保数据目录存在，否则 SQLite 打不开库文件。
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 建表之前先备份，万一升级/迁移把老数据弄坏，还能从 backups/ 回退。
    _backup_existing_db()
    SQLModel.metadata.create_all(engine)
    # 这次初始化内所有写入共用同一个时间戳，日志里更容易对上。
    now = iso_now()
    with Session(engine) as session:
        seed_categories(session, now)
        # schema_version 只在第一次写入；已存在就不覆盖，保留库里的真实版本号。
        record = session.get(Setting, "schema_version")
        if record is None:
            session.add(Setting(key="schema_version", value=str(SCHEMA_VERSION)))
            session.commit()


def get_session():
    """FastAPI 依赖注入用的数据库会话。

    参数：无（yield 出去的 session 由 FastAPI 自动注入给路由函数）。
    返回：生成器；请求处理完退出 with 块时会自动关闭会话、把连接还给连接池。
    """
    with Session(engine) as session:
        yield session
