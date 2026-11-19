"""测试夹具：内存 SQLite，一次一份，用完即弃。"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import Category


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def seeded(session):
    """种下最小分类树：其他/未分类（兜底） + 餐饮/午餐。"""
    other = Category(name="其他", icon="❓")
    food = Category(name="餐饮", icon="🍚")
    session.add(other)
    session.add(food)
    session.commit()
    session.refresh(other)
    session.refresh(food)

    for parent, name, icon in ((other, "未分类", "❓"), (food, "午餐", "🍜")):
        session.add(Category(name=name, icon=icon, parent_id=parent.id))
    session.commit()
    return session
