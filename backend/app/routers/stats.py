"""统计接口：本月汇总、分类占比、近 N 个月趋势。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import Expense
from ..schemas import CategoryStat, StatsSummary, TrendPoint
from ..services import load_categories, to_expense_out
from ..utils import cents_to_yuan, current_month, is_valid_month, today_str

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummary)
def summary(
    month: str | None = Query(default=None, description="YYYY-MM，默认本月"),
    session: Session = Depends(get_session),
) -> StatsSummary:
    if month is None:
        month = current_month()
    if not is_valid_month(month):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")

    month_conditions = [Expense.deleted_at.is_(None), Expense.spent_on.like(f"{month}-%")]
    total_cents = int(
        session.exec(
            select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(*month_conditions)
        ).one()
    )
    count = int(
        session.exec(select(func.count()).select_from(Expense).where(*month_conditions)).one()
    )
    today_cents = int(
        session.exec(
            select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(
                Expense.deleted_at.is_(None), Expense.spent_on == today_str()
            )
        ).one()
    )

    by_l1_rows = session.exec(
        select(Expense.category_l1, func.sum(Expense.amount_cents))
        .where(*month_conditions)
        .group_by(Expense.category_l1)
        .order_by(func.sum(Expense.amount_cents).desc())
    ).all()

    categories = load_categories(session)
    by_l1: list[CategoryStat] = []
    for category_id, amount in by_l1_rows:
        category = categories.get(int(category_id))
        amount_int = int(amount)
        by_l1.append(
            CategoryStat(
                id=int(category_id),
                name=category.name if category else "未知分类",
                icon=category.icon if category else "❓",
                total_cents=amount_int,
                total_yuan=cents_to_yuan(amount_int),
                percent=round(amount_int / total_cents * 100, 1) if total_cents else 0.0,
            )
        )

    by_l2_rows = session.exec(
        select(Expense.category_l2, func.sum(Expense.amount_cents))
        .where(*month_conditions)
        .group_by(Expense.category_l2)
        .order_by(func.sum(Expense.amount_cents).desc())
    ).all()
    by_l2: list[CategoryStat] = []
    for category_id, amount in by_l2_rows:
        category = categories.get(int(category_id))
        amount_int = int(amount)
        by_l2.append(
            CategoryStat(
                id=int(category_id),
                name=category.name if category else "未知分类",
                icon=category.icon if category else "❓",
                total_cents=amount_int,
                total_yuan=cents_to_yuan(amount_int),
                percent=round(amount_int / total_cents * 100, 1) if total_cents else 0.0,
            )
        )

    recent_rows = session.exec(
        select(Expense)
        .where(Expense.deleted_at.is_(None))
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
        .limit(5)
    ).all()

    return StatsSummary(
        month=month,
        total_cents=total_cents,
        total_yuan=cents_to_yuan(total_cents),
        today_cents=today_cents,
        today_yuan=cents_to_yuan(today_cents),
        count=count,
        by_l1=by_l1,
        by_l2=by_l2,
        recent=[to_expense_out(row, categories) for row in recent_rows],
    )


@router.get("/trend", response_model=list[TrendPoint])
def trend(
    months: int = Query(default=6, ge=1, le=24),
    session: Session = Depends(get_session),
) -> list[TrendPoint]:
    today = date.today()
    keys: list[str] = []
    year, month = today.year, today.month
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    keys.reverse()

    start = keys[0] + "-01"
    rows = session.exec(
        select(func.substr(Expense.spent_on, 1, 7), func.sum(Expense.amount_cents))
        .where(Expense.deleted_at.is_(None), Expense.spent_on >= start)
        .group_by(func.substr(Expense.spent_on, 1, 7))
    ).all()
    totals = {str(key): int(amount) for key, amount in rows}

    return [
        TrendPoint(month=key, total_cents=totals.get(key, 0), total_yuan=cents_to_yuan(totals.get(key, 0)))
        for key in keys
    ]
