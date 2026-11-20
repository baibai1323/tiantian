"""数据库表结构（SQLModel）。"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Category(SQLModel, table=True):
    """分类表：一级和二级都存这里，parent_id 为空表示一级分类。"""

    __tablename__ = "category"
    # 同一个父分类下不允许重名（parent_id + name 联合唯一）；
    # 不同父分类可以同名，比如“交通/餐饮”和“旅行/餐饮”互不冲突。
    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_category_parent_name"),)

    # 自增主键；写成 int | None 是表示“插入前还没有值”，由数据库负责分配。
    id: int | None = Field(default=None, primary_key=True)
    # 父分类 id：为空（NULL）表示这是一级分类，否则指向它所属的一级分类。
    parent_id: int | None = Field(default=None, foreign_key="category.id", index=True)
    name: str = Field(index=True)
    icon: str = ""
    # 一级分类的 sort_order 从 100 起、步长 100，给以后手工插入留出空隙；
    # 二级分类从 10 起、步长 10，保证同一父分类下顺序稳定。
    sort_order: int = 0
    # is_active 为 False 时表示用户“停用”了这个分类：历史账目仍保留，新记账时不再出现。
    is_active: bool = True
    # is_system 为 True 表示这是 seed.py 写入的预置分类，用户只能改名/停用，不能删除。
    is_system: bool = True
    # 时间统一存 ISO 字符串而不是 datetime 列：SQLite 没有原生日期类型，
    # 用字符串便于排序和跨平台，格式见 utils.iso_now()。
    created_at: str = ""


class Expense(SQLModel, table=True):
    """一笔支出。金额以“分”为单位存整数，避免浮点误差。"""

    __tablename__ = "expense"

    id: int | None = Field(default=None, primary_key=True)
    # 金额单位是“分”（1 元 = 100 分）。用整数存钱是财务软件的通行做法：
    # 0.1 + 0.2 在二进制浮点里不等于 0.3，换成整数分就不会有这种误差。
    amount_cents: int = Field(index=False)
    # 一级、二级分类都只存 id（外键指向 category 表），展示名字时再查表，
    # 这样分类改名后，历史账目会自动显示新名字。
    category_l1: int = Field(foreign_key="category.id", index=True)
    category_l2: int = Field(foreign_key="category.id", index=True)
    spent_on: str = Field(index=True)  # 本地日期 YYYY-MM-DD
    note: str = ""
    created_at: str = ""
    updated_at: str = ""
    # 软删除标记：不为空表示这笔账已被删除，但数据行还留在库里。
    # 为什么不真删？用户误删、或以后要做“回收站/恢复”时还有据可查；
    # 因此所有查询都必须带上 deleted_at IS NULL 这个过滤条件。
    deleted_at: str | None = Field(default=None, index=True)


class Setting(SQLModel, table=True):
    """键值对配置表，存 schema_version 这类不值得单独建表的少量全局设置。"""
    __tablename__ = "setting"

    key: str = Field(primary_key=True)
    value: str = ""
