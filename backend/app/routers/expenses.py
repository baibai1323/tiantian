"""账单接口：新增、查询、修改、软删除、恢复。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import Category, Expense
from ..schemas import ExpenseIn, ExpenseListOut, ExpenseOut, ExpensePatch
from ..services import load_categories, to_expense_out
from ..utils import cents_to_yuan, current_month, is_valid_month, iso_now, yuan_to_cents

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


def _get_active_expense(session: Session, expense_id: int) -> Expense:
    expense = session.get(Expense, expense_id)
    if expense is None or expense.deleted_at is not None:
        raise HTTPException(status_code=404, detail="这笔记录不存在或已删除")
    return expense


def _resolve_category(session: Session, category_l2: int) -> tuple[Category, Category]:
    l2 = session.get(Category, category_l2)
    if l2 is None or l2.parent_id is None:
        raise HTTPException(status_code=400, detail="请选择一个有效的二级分类")
    l1 = session.get(Category, l2.parent_id)
    if l1 is None:
        raise HTTPException(status_code=400, detail="分类数据异常，请检查分类设置")
    return l1, l2


@router.get("", response_model=ExpenseListOut)
def list_expenses(
    month: str | None = Query(default=None, description="YYYY-MM，默认本月"),
    category_l1: int | None = None,
    category_l2: int | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False, description="是否包含已软删除的记录"),
    session: Session = Depends(get_session),
) -> ExpenseListOut:
    if month is None:
        month = current_month()
    if not is_valid_month(month):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")

    conditions = [Expense.spent_on.like(f"{month}-%")]
    if not include_deleted:
        conditions.append(Expense.deleted_at.is_(None))
    if category_l1 is not None:
        conditions.append(Expense.category_l1 == category_l1)
    if category_l2 is not None:
        conditions.append(Expense.category_l2 == category_l2)
    if q:
        conditions.append(Expense.note.like(f"%{q.strip()}%"))

    total = session.exec(select(func.count()).select_from(Expense).where(*conditions)).one()
    sum_cents = session.exec(
        select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(*conditions)
    ).one()
    rows = session.exec(
        select(Expense)
        .where(*conditions)
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    categories = load_categories(session)
    return ExpenseListOut(
        items=[to_expense_out(row, categories) for row in rows],
        total=int(total),
        sum_cents=int(sum_cents),
        sum_yuan=cents_to_yuan(int(sum_cents)),
    )


@router.post("", response_model=ExpenseOut, status_code=201)
def create_expense(payload: ExpenseIn, session: Session = Depends(get_session)) -> ExpenseOut:
    l1, _l2 = _resolve_category(session, payload.category_l2)
    now = iso_now()
    expense = Expense(
        amount_cents=yuan_to_cents(payload.amount),
        category_l1=l1.id,  # type: ignore[arg-type]
        category_l2=payload.category_l2,
        spent_on=payload.spent_on,
        note=payload.note,
        created_at=now,
        updated_at=now,
    )
    session.add(expense)
    session.commit()
    session.refresh(expense)
    categories = load_categories(session)
    return to_expense_out(expense, categories)


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, session: Session = Depends(get_session)) -> ExpenseOut:
    expense = _get_active_expense(session, expense_id)
    return to_expense_out(expense, load_categories(session))


@router.patch("/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int, payload: ExpensePatch, session: Session = Depends(get_session)
) -> ExpenseOut:
    expense = _get_active_expense(session, expense_id)

    if payload.amount is not None:
        expense.amount_cents = yuan_to_cents(payload.amount)
    if payload.category_l2 is not None:
        l1, _l2 = _resolve_category(session, payload.category_l2)
        expense.category_l2 = payload.category_l2
        expense.category_l1 = l1.id  # type: ignore[assignment]
    if payload.spent_on is not None:
        expense.spent_on = payload.spent_on
    if payload.note is not None:
        expense.note = payload.note

    expense.updated_at = iso_now()
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return to_expense_out(expense, load_categories(session))


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, session: Session = Depends(get_session)) -> dict[str, bool]:
    expense = _get_active_expense(session, expense_id)
    expense.deleted_at = iso_now()
    session.add(expense)
    session.commit()
    return {"ok": True}


@router.post("/{expense_id}/restore", response_model=ExpenseOut)
def restore_expense(expense_id: int, session: Session = Depends(get_session)) -> ExpenseOut:
    expense = session.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="这笔记录不存在")
    expense.deleted_at = None
    expense.updated_at = iso_now()
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return to_expense_out(expense, load_categories(session))
