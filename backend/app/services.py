"""路由共用的查询与序列化逻辑。"""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Category, Expense
from .schemas import ExpenseOut
from .utils import cents_to_yuan


def load_categories(session: Session) -> dict[int, Category]:
    rows = session.exec(select(Category)).all()
    return {row.id: row for row in rows if row.id is not None}


def to_expense_out(expense: Expense, categories: dict[int, Category]) -> ExpenseOut:
    l1 = categories.get(expense.category_l1)
    l2 = categories.get(expense.category_l2)
    return ExpenseOut(
        id=expense.id or 0,
        amount_cents=expense.amount_cents,
        amount_yuan=cents_to_yuan(expense.amount_cents),
        category_l1=expense.category_l1,
        category_l1_name=l1.name if l1 else "未知分类",
        category_l1_icon=l1.icon if l1 else "❓",
        category_l2=expense.category_l2,
        category_l2_name=l2.name if l2 else "未知分类",
        spent_on=expense.spent_on,
        note=expense.note,
        created_at=expense.created_at,
        deleted_at=expense.deleted_at,
    )
