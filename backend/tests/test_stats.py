"""统计接口（summary / trend）的行为测试：直接调用路由函数 + 内存 SQLite。

时间一律用 monkeypatch 钉死，避免用例随运行日期漂移。
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.models import Category, Expense
from app.routers import stats as stats_router
from app.routers.stats import summary, trend


# ---------- 辅助 ----------


def category_id(session, name: str) -> int:
    return session.exec(select(Category).where(Category.name == name)).one().id


def add_expense(
    session,
    amount_cents: int,
    *,
    l1: int,
    l2: int,
    spent_on: str,
    note: str = "",
    created_at: str = "2026-01-01T00:00:00+08:00",
    deleted_at: str | None = None,
) -> Expense:
    row = Expense(
        amount_cents=amount_cents,
        category_l1=l1,
        category_l2=l2,
        spent_on=spent_on,
        note=note,
        created_at=created_at,
        updated_at=created_at,
        deleted_at=deleted_at,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


class FixedDate(date):
    """把 stats.trend 里的 date.today() 钉死。"""

    @classmethod
    def today(cls):
        return cls(2026, 1, 15)


@pytest.fixture
def january(monkeypatch):
    monkeypatch.setattr(stats_router, "date", FixedDate)


# ---------- summary：正常路径 ----------


def test_summary_defaults_to_current_month(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "current_month", lambda: "2026-11")
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-19")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 2800, l1=food, l2=lunch, spent_on="2026-11-05")

    # 直接调用时 Query 默认值不会被 FastAPI 解析，用显式 None 模拟「没传 month」
    result = summary(month=None, session=seeded)

    assert result.month == "2026-11"
    assert result.total_cents == 2800


def test_summary_total_cents_only_counts_the_month(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 2800, l1=food, l2=lunch, spent_on="2026-11-02")
    add_expense(seeded, 5000, l1=food, l2=lunch, spent_on="2026-10-31")

    result = summary(month="2026-11", session=seeded)

    assert (result.total_cents, result.total_yuan) == (2800, "28.00")


def test_summary_count_counts_rows_not_amount(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 100, l1=food, l2=lunch, spent_on="2026-11-02")
    add_expense(seeded, 200, l1=food, l2=lunch, spent_on="2026-11-03")
    add_expense(seeded, 300, l1=food, l2=lunch, spent_on="2026-10-03")

    result = summary(month="2026-11", session=seeded)

    assert result.count == 2


def test_summary_today_cents_only_counts_today(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-19")
    monkeypatch.setattr(stats_router, "current_month", lambda: "2026-11")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 2800, l1=food, l2=lunch, spent_on="2026-11-19")
    add_expense(seeded, 1200, l1=food, l2=lunch, spent_on="2026-11-19")
    add_expense(seeded, 5000, l1=food, l2=lunch, spent_on="2026-11-18")

    result = summary(month="2026-11", session=seeded)

    assert (result.today_cents, result.today_yuan) == (4000, "40.00")


def test_summary_today_cents_is_zero_for_past_months(seeded, monkeypatch):
    """查历史月份时不能把今天的支出算进 today_cents。"""
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-19")
    monkeypatch.setattr(stats_router, "current_month", lambda: "2026-11")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 2800, l1=food, l2=lunch, spent_on="2026-11-19")
    add_expense(seeded, 1000, l1=food, l2=lunch, spent_on="2026-10-05")

    result = summary(month="2026-10", session=seeded)

    assert (result.total_cents, result.today_cents) == (1000, 0)


def test_summary_by_l1_is_sorted_desc_with_percent(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    other = category_id(seeded, "其他")
    unclassified = category_id(seeded, "未分类")
    add_expense(seeded, 5000, l1=food, l2=lunch, spent_on="2026-11-02")
    add_expense(seeded, 1000, l1=food, l2=lunch, spent_on="2026-11-03")
    add_expense(seeded, 3000, l1=other, l2=unclassified, spent_on="2026-11-04")

    result = summary(month="2026-11", session=seeded)

    assert [(item.name, item.total_cents, item.percent) for item in result.by_l1] == [
        ("餐饮", 6000, 66.7),
        ("其他", 3000, 33.3),
    ]


def test_summary_by_l2_breakdown(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    other = category_id(seeded, "其他")
    unclassified = category_id(seeded, "未分类")
    add_expense(seeded, 2800, l1=food, l2=lunch, spent_on="2026-11-02")
    add_expense(seeded, 1200, l1=other, l2=unclassified, spent_on="2026-11-03")

    result = summary(month="2026-11", session=seeded)

    assert [(item.id, item.total_cents, item.percent) for item in result.by_l2] == [
        (lunch, 2800, 70.0),
        (unclassified, 1200, 30.0),
    ]


# ---------- summary：分类兜底与除零 ----------


def test_summary_by_l1_unknown_category_falls_back(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    add_expense(seeded, 2800, l1=999, l2=998, spent_on="2026-11-02")

    result = summary(month="2026-11", session=seeded)

    assert (result.by_l1[0].name, result.by_l1[0].icon) == ("未知分类", "❓")


def test_summary_by_l2_unknown_category_falls_back(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    add_expense(seeded, 2800, l1=food, l2=998, spent_on="2026-11-02")

    result = summary(month="2026-11", session=seeded)

    assert (result.by_l2[0].name, result.by_l2[0].icon) == ("未知分类", "❓")


def test_summary_percent_is_zero_when_month_total_is_zero(seeded, monkeypatch):
    """总额为 0 时 by_l1 / by_l2 的占比都要走除零保护，不能 500。"""
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 0, l1=food, l2=lunch, spent_on="2026-11-02")

    result = summary(month="2026-11", session=seeded)

    assert (result.total_cents, result.by_l1[0].percent, result.by_l2[0].percent) == (0, 0.0, 0.0)


# ---------- summary：最近 5 笔 ----------


def test_summary_recent_returns_five_newest(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    for day in range(1, 7):
        add_expense(seeded, day * 100, l1=food, l2=lunch, spent_on=f"2026-08-0{day}")

    result = summary(month="2026-11", session=seeded)

    assert [item.spent_on for item in result.recent] == [
        "2026-08-06",
        "2026-08-05",
        "2026-08-04",
        "2026-08-03",
        "2026-08-02",
    ]


def test_summary_recent_breaks_same_day_ties_by_id_desc(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    first = add_expense(seeded, 100, l1=food, l2=lunch, spent_on="2026-08-10")
    second = add_expense(seeded, 200, l1=food, l2=lunch, spent_on="2026-08-10")

    result = summary(month="2026-11", session=seeded)

    assert [item.id for item in result.recent] == [second.id, first.id]


def test_summary_recent_excludes_soft_deleted(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 100, l1=food, l2=lunch, spent_on="2026-08-01")
    add_expense(
        seeded,
        200,
        l1=food,
        l2=lunch,
        spent_on="2026-09-01",
        deleted_at="2026-09-02T00:00:00+08:00",
    )

    result = summary(month="2026-11", session=seeded)

    assert [item.spent_on for item in result.recent] == ["2026-08-01"]


def test_summary_recent_maps_category_names_and_amount(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 2800, l1=food, l2=lunch, spent_on="2026-11-02", note="午饭")

    result = summary(month="2026-11", session=seeded)

    recent = result.recent[0]
    assert (recent.category_l1_name, recent.category_l1_icon) == ("餐饮", "🍚")
    assert (recent.category_l2_name, recent.amount_yuan) == ("午餐", "28.00")


# ---------- summary：空月份与非法输入 ----------


def test_summary_excludes_soft_deleted_expenses(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 2800, l1=food, l2=lunch, spent_on="2026-11-02")
    add_expense(
        seeded,
        5000,
        l1=food,
        l2=lunch,
        spent_on="2026-11-03",
        deleted_at="2026-11-04T00:00:00+08:00",
    )

    result = summary(month="2026-11", session=seeded)

    assert (result.total_cents, result.count) == (2800, 1)


def test_summary_empty_month_returns_zero_totals(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")

    result = summary(month="2026-11", session=seeded)

    assert (result.total_cents, result.total_yuan, result.count) == (0, "0.00", 0)


def test_summary_empty_month_returns_empty_breakdowns(seeded, monkeypatch):
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")

    result = summary(month="2026-11", session=seeded)

    assert (result.by_l1, result.by_l2, result.recent) == ([], [], [])


@pytest.mark.parametrize("month", ["2026-13", "2026-00", "2026/11", "abc", ""])
def test_summary_rejects_invalid_month(seeded, month):
    with pytest.raises(HTTPException) as exc:
        summary(month=month, session=seeded)

    assert exc.value.status_code == 400
    assert exc.value.detail == "月份格式应为 YYYY-MM"


def test_summary_loose_month_format_is_normalized(seeded, monkeypatch):
    """回归用例：前端传 "2026-1" 这种没补零的月份也要能查到数据。

    修复前：is_valid_month 放宽了 %m 校验，"2026-1" 通过，但 SQL 用
    like '2026-1-%' 过滤，零填充的 '2026-01-05' 匹配不到，静默返回 0。
    """
    monkeypatch.setattr(stats_router, "today_str", lambda: "2026-11-30")
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 2800, l1=food, l2=lunch, spent_on="2026-01-05")

    result = summary(month="2026-1", session=seeded)

    assert (result.month, result.total_cents) == ("2026-01", 2800)


# ---------- trend ----------


def test_trend_returns_months_oldest_first_with_zero_fill(seeded, january):
    result = trend(months=6, session=seeded)

    assert [(point.month, point.total_cents) for point in result] == [
        ("2025-08", 0),
        ("2025-09", 0),
        ("2025-10", 0),
        ("2025-11", 0),
        ("2025-12", 0),
        ("2026-01", 0),
    ]


def test_trend_sums_expenses_by_month(seeded, january):
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    other = category_id(seeded, "其他")
    unclassified = category_id(seeded, "未分类")
    add_expense(seeded, 2800, l1=food, l2=lunch, spent_on="2025-12-03")
    add_expense(seeded, 1200, l1=other, l2=unclassified, spent_on="2025-12-20")
    add_expense(seeded, 500, l1=food, l2=lunch, spent_on="2026-01-02")

    result = trend(months=6, session=seeded)

    assert [(point.month, point.total_cents) for point in result] == [
        ("2025-08", 0),
        ("2025-09", 0),
        ("2025-10", 0),
        ("2025-11", 0),
        ("2025-12", 4000),
        ("2026-01", 500),
    ]


def test_trend_total_yuan_is_two_decimals(seeded, january):
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 4050, l1=food, l2=lunch, spent_on="2026-01-02")

    result = trend(months=1, session=seeded)

    assert result[0].total_yuan == "40.50"


def test_trend_months_one_returns_only_current_month(seeded, january):
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 500, l1=food, l2=lunch, spent_on="2026-01-02")
    add_expense(seeded, 999, l1=food, l2=lunch, spent_on="2025-12-31")

    result = trend(months=1, session=seeded)

    assert [(point.month, point.total_cents) for point in result] == [("2026-01", 500)]


def test_trend_twenty_four_months_crosses_year_boundary(seeded, january):
    result = trend(months=24, session=seeded)

    assert len(result) == 24
    assert result[0].month == "2024-02"
    assert result[-1].month == "2026-01"


def test_trend_excludes_soft_deleted(seeded, january):
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 300, l1=food, l2=lunch, spent_on="2026-01-02")
    add_expense(
        seeded,
        9999,
        l1=food,
        l2=lunch,
        spent_on="2026-01-03",
        deleted_at="2026-01-04T00:00:00+08:00",
    )

    result = trend(months=1, session=seeded)

    assert result[0].total_cents == 300


def test_trend_excludes_expenses_before_window(seeded, january):
    food = category_id(seeded, "餐饮")
    lunch = category_id(seeded, "午餐")
    add_expense(seeded, 9999, l1=food, l2=lunch, spent_on="2025-07-31")
    add_expense(seeded, 700, l1=food, l2=lunch, spent_on="2025-08-01")

    result = trend(months=6, session=seeded)

    assert [point.total_cents for point in result] == [700, 0, 0, 0, 0, 0]
