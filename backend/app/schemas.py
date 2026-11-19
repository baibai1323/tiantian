"""接口的请求 / 响应数据结构（Pydantic）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

MAX_AMOUNT = Decimal("9999999.99")


def _normalize_date(value: str) -> str:
    """校验并统一成 YYYY-MM-DD。

    strptime 会接受 "2026-1-5" 这种没补零的写法，但数据库里存进去后
    按月前缀查询（LIKE '2026-01-%'）就再也查不到这笔账，所以这里必须
    严格按补零格式回写。
    """
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("日期格式应为 YYYY-MM-DD") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError("日期格式应为 YYYY-MM-DD（月和日要补零）")
    return value


class CategoryNode(BaseModel):
    id: int
    name: str
    icon: str = ""
    children: list["CategoryNode"] = Field(default_factory=list)


class CategoryCreate(BaseModel):
    parent_id: int | None = None
    name: str
    icon: str = ""


class CategoryUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None


class CategoryManageNode(BaseModel):
    id: int
    name: str
    icon: str
    is_system: bool
    expense_count: int = 0
    children: list["CategoryManageNode"] = Field(default_factory=list)


class CategoryDeleteResult(BaseModel):
    migrated: int = 0


class ExpenseIn(BaseModel):
    amount: Decimal
    category_l2: int
    spent_on: str
    note: str = ""

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("金额必须大于 0")
        if value.as_tuple().exponent < -2:
            raise ValueError("金额最多两位小数")
        if value > MAX_AMOUNT:
            raise ValueError("金额过大")
        return value

    @field_validator("spent_on")
    @classmethod
    def _check_date(cls, value: str) -> str:
        return _normalize_date(value)

    @field_validator("note")
    @classmethod
    def _trim_note(cls, value: str) -> str:
        return value.strip()[:200]


class ExpensePatch(BaseModel):
    amount: Decimal | None = None
    category_l2: int | None = None
    spent_on: str | None = None
    note: str | None = None

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("金额必须大于 0")
        if value.as_tuple().exponent < -2:
            raise ValueError("金额最多两位小数")
        if value > MAX_AMOUNT:
            raise ValueError("金额过大")
        return value

    @field_validator("spent_on")
    @classmethod
    def _check_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_date(value)

    @field_validator("note")
    @classmethod
    def _trim_note(cls, value: str | None) -> str | None:
        return value.strip()[:200] if value is not None else None


class ExpenseOut(BaseModel):
    id: int
    amount_cents: int
    amount_yuan: str
    category_l1: int
    category_l1_name: str
    category_l1_icon: str
    category_l2: int
    category_l2_name: str
    spent_on: str
    note: str
    created_at: str
    deleted_at: str | None = None


class ExpenseListOut(BaseModel):
    items: list[ExpenseOut]
    total: int
    sum_cents: int
    sum_yuan: str


class CategoryStat(BaseModel):
    id: int
    name: str
    icon: str
    total_cents: int
    total_yuan: str
    percent: float


class StatsSummary(BaseModel):
    month: str
    total_cents: int
    total_yuan: str
    today_cents: int
    today_yuan: str
    count: int
    by_l1: list[CategoryStat]
    by_l2: list[CategoryStat] = Field(default_factory=list)
    recent: list[ExpenseOut]


class TrendPoint(BaseModel):
    month: str
    total_cents: int
    total_yuan: str


class ImportRequest(BaseModel):
    content: str


class ImportIssue(BaseModel):
    line: int
    reason: str


class ImportResult(BaseModel):
    imported: int
    duplicates: int
    invalid: int
    fallback: int
    errors: list[ImportIssue] = Field(default_factory=list)
    warnings: list[ImportIssue] = Field(default_factory=list)
