"""数据库表结构（SQLModel）。"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Category(SQLModel, table=True):
    """分类表：一级和二级都存这里，parent_id 为空表示一级分类。"""

    __tablename__ = "category"
    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_category_parent_name"),)

    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = Field(default=None, foreign_key="category.id", index=True)
    name: str = Field(index=True)
    icon: str = ""
    sort_order: int = 0
    is_active: bool = True
    is_system: bool = True
    created_at: str = ""


class Expense(SQLModel, table=True):
    """一笔支出。金额以“分”为单位存整数，避免浮点误差。"""

    __tablename__ = "expense"

    id: int | None = Field(default=None, primary_key=True)
    amount_cents: int = Field(index=False)
    category_l1: int = Field(foreign_key="category.id", index=True)
    category_l2: int = Field(foreign_key="category.id", index=True)
    spent_on: str = Field(index=True)  # 本地日期 YYYY-MM-DD
    note: str = ""
    created_at: str = ""
    updated_at: str = ""
    deleted_at: str | None = Field(default=None, index=True)


class Setting(SQLModel, table=True):
    __tablename__ = "setting"

    key: str = Field(primary_key=True)
    value: str = ""
