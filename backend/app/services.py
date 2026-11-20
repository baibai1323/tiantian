"""路由共用的查询与序列化逻辑。"""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Category, Expense
from .schemas import ExpenseOut
from .utils import cents_to_yuan


def load_categories(session: Session) -> dict[int, Category]:
    """一次性把所有分类读进内存，返回 {id: Category} 形式的字典。

    参数 session：数据库会话。
    返回：字典；路由要翻译很多账目的分类名，先查一次再按 id 取，
    比每条账目都去查一次库快得多（分类通常只有几十到几百条）。
    """
    # 全量读出后在内存里按 id 取，避免 N+1 查询（每条记录再查一次数据库）。
    rows = session.exec(select(Category)).all()
    # 过滤 id 为 None 只是防御：已入库的行主键一定有值，类型标注却允许 None。
    return {row.id: row for row in rows if row.id is not None}


def to_expense_out(expense: Expense, categories: dict[int, Category]) -> ExpenseOut:
    """把数据库里的 Expense 行转成接口要返回的 ExpenseOut。

    参数 expense：一条支出记录（金额是“分”）。
    参数 categories：load_categories() 得到的 {id: Category} 字典，用来翻译分类名。
    返回：ExpenseOut 对象，金额已经换算成“元”字符串。
    """
    l1 = categories.get(expense.category_l1)
    l2 = categories.get(expense.category_l2)
    # 分类可能被停用、或数据被手工改过，查不到时用“未知分类/❓”兜底，
    # 保证账目照样显示，不会因为一个分类缺失就让整个列表报错。
    return ExpenseOut(
        # ORM 认为尚未入库的记录 id 是 None，而接口约定 id 必须是整数，这里用 0 占位。
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
