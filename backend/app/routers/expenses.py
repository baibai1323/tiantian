"""账单接口：新增、查询、修改、软删除、恢复、彻底删除。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlmodel import Session, select

from ..db import get_session
from ..models import Category, Expense
from ..schemas import ExpenseIn, ExpenseListOut, ExpenseOut, ExpensePatch
from ..services import load_categories, to_expense_out
from ..utils import (
    cents_to_yuan,
    current_month,
    is_valid_month,
    iso_now,
    normalize_month,
    yuan_to_cents,
)

# 这个模块的所有接口都挂在 /api/expenses 下，前端「账单列表 / 回收站」都走这里。
# 「软删除」是本文件的核心概念：删除时只给 deleted_at 写上时间戳，记录仍然留在表里，
# 所以回收站还能看到、还能恢复；只有「彻底删除」才真正把行从表里移除。
router = APIRouter(prefix="/api/expenses", tags=["expenses"])


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符，避免用户搜 "%" 时把全部记录都匹配出来。"""
    # LIKE 是 SQL 的模糊匹配语法：% 代表任意多个字符，_ 代表任意一个字符。
    # 用户输入的这些符号必须先转义，否则搜「50%」会变成「以 50 开头的所有备注」。
    # 反斜杠自己就是转义符，所以必须最先替换，顺序反过来会把刚加的转义符又转义一遍。
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _get_active_expense(session: Session, expense_id: int) -> Expense:
    """按 id 取一笔「没被软删除」的账单，取不到就报 404。

    做什么：查库后同时检查「不存在」和「已进回收站」两种情况——对调用方来说
    这两种都等于「你要操作的账单不可用」，所以统一返回 404。
    参数 session：数据库会话，由框架注入。
    参数 expense_id：账单 id。
    返回：Expense 对象；不存在或已软删除时抛 404。
    """
    expense = session.get(Expense, expense_id)
    # deleted_at 不为空说明这笔账在回收站里，详情、修改、再删除都应该看不见它。
    if expense is None or expense.deleted_at is not None:
        raise HTTPException(status_code=404, detail="这笔记录不存在或已删除")
    return expense


def _resolve_category(session: Session, category_l2: int) -> tuple[Category, Category]:
    """根据二级分类 id 找到它自己以及它的一级分类。

    做什么：账单表里同时存了一级和二级分类 id（查询统计更快），所以新增或
    改分类时要靠这个函数把「二级 -> 一级」的父子关系补全。
    参数 session：数据库会话，由框架注入。
    参数 category_l2：用户选择的二级分类 id。
    返回：元组（一级分类对象, 二级分类对象）；分类不存在或不是二级分类时抛 400。
    """
    l2 = session.get(Category, category_l2)
    # parent_id 为空说明用户传进来的其实是个一级分类，账单必须挂在二级分类上。
    if l2 is None or l2.parent_id is None:
        raise HTTPException(status_code=400, detail="请选择一个有效的二级分类")
    l1 = session.get(Category, l2.parent_id)
    # 理论上外键保证父分类存在，但分类表被手动改过时仍可能落空，这里做防御。
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
    """按月份 / 分类 / 关键字分页查询账单列表。

    做什么：把各个可选条件拼成一组 SQL WHERE 条件，先算总数和金额合计，
    再取当前页的数据，最后把数据库行转成带分类名字的输出对象。
    参数 month：月份字符串 YYYY-MM；不传默认本月。会先补零再校验格式。
    参数 category_l1：一级分类 id，传了就只看这个大类的账单。
    参数 category_l2：二级分类 id，比一级更精确，通常和 category_l1 二选一。
    参数 q：备注关键字，模糊匹配；% 和 _ 会被当普通字符处理。
    参数 limit：本页最多返回几条，默认 200，范围 1~1000（防止一次拉爆内存）。
    参数 offset：跳过前面多少条，配合 limit 实现翻页。
    参数 include_deleted：是否包含回收站里的记录；默认 False，只看正常账单。
    参数 session：数据库会话，由框架注入。
    返回：ExpenseListOut，含 items（本页数据）、total（总条数）、sum_cents / sum_yuan（合计金额）。
    """
    # 不传月份时用「当前月」，这是打开首页时的默认视图。
    if month is None:
        month = current_month()
    # normalize_month 负责把 "2026-1" 补成 "2026-01"：数据库里存的是补零格式，
    # 不补零会拼出 LIKE "2026-1-%" 而一条都查不到（这是个真实踩过的坑）。
    month = normalize_month(month)
    # 补零后仍不合法（比如 "2026-13"）就返回 400，别拿脏值去查库。
    if not is_valid_month(month):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")

    # spent_on 存的是 "YYYY-MM-DD" 字符串，用 "YYYY-MM-%" 前缀匹配整月。
    # 之所以能这么写，是因为日期在写入时已经强制补零，格式统一。
    conditions = [Expense.spent_on.like(f"{month}-%")]
    # 默认过滤掉软删除（deleted_at 有值）的记录，这就是「软删除即隐藏」的效果。
    if not include_deleted:
        conditions.append(Expense.deleted_at.is_(None))
    if category_l1 is not None:
        conditions.append(Expense.category_l1 == category_l1)
    if category_l2 is not None:
        conditions.append(Expense.category_l2 == category_l2)
    # `q and q.strip()`：既挡掉没传，也挡掉只输入空格的搜索。
    if q and q.strip():
        # 传入 escape 参数是告诉数据库「用反斜杠识别转义符」，配合 _escape_like 一起用，
        # 否则用户搜 "%" 会把全部账单都匹配出来。
        keyword = f"%{_escape_like(q.strip())}%"
        note_cond = Expense.note.like(keyword, escape="\\")
        # 前端占位符写的是「搜备注、二级分类」，所以分类名也要能搜到：
        # 先按名字查出匹配的分类 id，再把「备注命中 或 二级分类命中」合并成一个条件。
        matched_l2 = session.exec(
            select(Category.id).where(Category.name.like(keyword, escape="\\"))
        ).all()
        if matched_l2:
            conditions.append(or_(note_cond, Expense.category_l2.in_(matched_l2)))
        else:
            conditions.append(note_cond)

    # 分两次查：一次只要总数，一次只要当前页数据。
    # 合计金额用 coalesce(sum(...), 0)：没有记录时 sum 返回 NULL，包一层变成 0。
    total = session.exec(select(func.count()).select_from(Expense).where(*conditions)).one()
    sum_cents = session.exec(
        select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(*conditions)
    ).one()
    # 排序规则：先按消费日期倒序（新的在上），同一天再按 id 倒序，
    # 保证同一天内后录入的排在前面，翻页时顺序也稳定。
    rows = session.exec(
        select(Expense)
        .where(*conditions)
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    # 分类表一次读进内存做成字典，转输出时按 id 查名字，避免每条账单都查一次库。
    categories = load_categories(session)
    return ExpenseListOut(
        items=[to_expense_out(row, categories) for row in rows],
        total=int(total),
        # sum_cents 是「分」，同时给一份「元」的字符串，前端不用自己做除法。
        sum_cents=int(sum_cents),
        sum_yuan=cents_to_yuan(int(sum_cents)),
    )


@router.post("", response_model=ExpenseOut, status_code=201)
def create_expense(payload: ExpenseIn, session: Session = Depends(get_session)) -> ExpenseOut:
    """新增一笔账单。

    做什么：先用二级分类反查一级分类，把金额从「元」换算成整数「分」，
    再写入数据库并回读，最后转成带分类名字的输出对象。
    参数 payload：前端提交的账单，含 amount（元，最多两位小数）、category_l2、
    spent_on（YYYY-MM-DD）和 note（备注）。
    参数 session：数据库会话，由框架注入。
    返回：新建成功的账单，状态码 201 表示「已创建」。
    """
    # 下划线开头的 _l2 表示「这个变量后面用不到」，只需要它的一级分类。
    l1, _l2 = _resolve_category(session, payload.category_l2)
    # 创建时间和修改时间先取同一个时间戳，后续修改时才会只更新 updated_at。
    now = iso_now()
    expense = Expense(
        # 金额一律以「分」为单位存整数，避免 0.1 + 0.2 != 0.3 这类浮点误差。
        # 换算函数由 Pydantic 在入口处保证「最多两位小数」，这里不会丢精度。
        amount_cents=yuan_to_cents(payload.amount),
        category_l1=l1.id,  # type: ignore[arg-type]
        category_l2=payload.category_l2,
        spent_on=payload.spent_on,
        note=payload.note,
        created_at=now,
        updated_at=now,
    )
    session.add(expense)
    # commit 落库，refresh 读回数据库生成的 id，缺一不可。
    session.commit()
    session.refresh(expense)
    # 重新加载分类表：输出时要显示「餐饮 / 午饭」这样的中文名，而不只是 id。
    categories = load_categories(session)
    return to_expense_out(expense, categories)


@router.get("/trash", response_model=ExpenseListOut)
def list_trash(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ExpenseListOut:
    """回收站：所有已软删除的记录，按删除时间倒序。"""
    # 「回收站」= 进过删除操作、但还没有彻底删除的账单集合。
    # is_not(None) 等价于 SQL 的 IS NOT NULL：deleted_at 有值才在回收站里。
    conditions = [Expense.deleted_at.is_not(None)]  # type: ignore[union-attr]
    # 和列表接口一样，分别查总数、金额合计和当前页数据；回收站不分月份。
    total = session.exec(select(func.count()).select_from(Expense).where(*conditions)).one()
    sum_cents = session.exec(
        select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(*conditions)
    ).one()
    # 按删除时间倒序：最近删掉的排最前面，用户一般先恢复刚误删的那条。
    rows = session.exec(
        select(Expense)
        .where(*conditions)
        .order_by(Expense.deleted_at.desc(), Expense.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    # 回收站里的账单也要显示分类名，所以同样要加载分类字典。
    categories = load_categories(session)
    return ExpenseListOut(
        items=[to_expense_out(row, categories) for row in rows],
        total=int(total),
        sum_cents=int(sum_cents),
        sum_yuan=cents_to_yuan(int(sum_cents)),
    )


@router.delete("/trash")
def empty_trash(session: Session = Depends(get_session)) -> dict[str, int]:
    """清空回收站：把所有已软删除的记录真正删掉。"""
    # 这是不可撤销的操作：下面用 ORM 的 delete 逐条删除，之后无法恢复。
    # 只取 deleted_at 有值的行，正常账单不会被误删。
    rows = session.exec(select(Expense).where(Expense.deleted_at.is_not(None))).all()  # type: ignore[union-attr]
    for row in rows:
        session.delete(row)
    # 一次 commit 提交全部删除，中途出错不会只删掉一半。
    session.commit()
    # 返回删除条数，前端可以提示「已清空 N 条」。
    return {"deleted": len(rows)}


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, session: Session = Depends(get_session)) -> ExpenseOut:
    """查询单笔账单的详情。

    做什么：按 id 取一笔未删除的账单，转成带分类名字的输出对象。
    参数 expense_id：账单 id，来自 URL。
    参数 session：数据库会话，由框架注入。
    返回：ExpenseOut；账单不存在或在回收站里时抛 404。
    """
    # 复用 _get_active_expense，保证「已软删除 = 查不到」的规则只有一处实现。
    expense = _get_active_expense(session, expense_id)
    return to_expense_out(expense, load_categories(session))


@router.patch("/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int, payload: ExpensePatch, session: Session = Depends(get_session)
) -> ExpenseOut:
    """修改一笔账单的部分字段（PATCH 语义）。

    做什么：只更新前端真正传了的字段，没传的保持原值；改分类时会重新解析
    一级分类，最后刷新 updated_at 并返回最新数据。
    参数 expense_id：要修改的账单 id，来自 URL。
    参数 payload：可能只含其中几个字段；字段为 None 表示「这次不改」。
    参数 session：数据库会话，由框架注入。
    返回：修改后的账单；账单不存在或已在回收站时抛 404。
    """
    expense = _get_active_expense(session, expense_id)

    # 每个 if 都是「传了才改」，这样前端不必先把完整数据读出来再整体提交。
    if payload.amount is not None:
        expense.amount_cents = yuan_to_cents(payload.amount)
    if payload.category_l2 is not None:
        # 改二级分类时一级分类要跟着变，否则统计按一级汇总会漏掉这笔账。
        l1, _l2 = _resolve_category(session, payload.category_l2)
        expense.category_l2 = payload.category_l2
        expense.category_l1 = l1.id  # type: ignore[assignment]
    if payload.spent_on is not None:
        expense.spent_on = payload.spent_on
    if payload.note is not None:
        expense.note = payload.note

    # updated_at 记录最后一次修改时间，方便排查「这条数据什么时候被改过」。
    expense.updated_at = iso_now()
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return to_expense_out(expense, load_categories(session))


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, session: Session = Depends(get_session)) -> dict[str, bool]:
    """把一笔账单挪进回收站（软删除）。

    做什么：不清空数据，只给 deleted_at 写当前时间；之后列表接口默认查不到它，
    但回收站能看到、也能恢复。
    参数 expense_id：要删除的账单 id。
    参数 session：数据库会话，由框架注入。
    返回：{"ok": True}，前端据此提示删除成功。
    """
    # 先确认账单存在且还没被删：重复删除会给出 404，而不是悄悄改一次时间戳。
    expense = _get_active_expense(session, expense_id)
    # 这一步就是「软删除」的全部动作：只打一个删除时间标记。
    expense.deleted_at = iso_now()
    session.add(expense)
    session.commit()
    return {"ok": True}


@router.delete("/{expense_id}/permanent")
def purge_expense(expense_id: int, session: Session = Depends(get_session)) -> dict[str, bool]:
    """彻底删除：只允许删除已进回收站（软删除）的记录，删掉后无法恢复。"""
    # 「彻底删除」和软删除的区别：这里是真的执行 DELETE，数据行会从表里消失，
    # 之后既不能在回收站看到，也没有任何恢复接口，所以要求用户分两步操作。
    expense = session.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="这笔记录不存在")
    # 还在正常列表里的账单不允许直接彻底删除，必须先走一次软删除，
    # 这样用户至少有一次「确认删除」的缓冲，避免误点永久丢数据。
    if expense.deleted_at is None:
        raise HTTPException(status_code=400, detail="请先删除这笔记录，再彻底删除")
    session.delete(expense)
    session.commit()
    return {"ok": True}


@router.post("/{expense_id}/restore", response_model=ExpenseOut)
def restore_expense(expense_id: int, session: Session = Depends(get_session)) -> ExpenseOut:
    """把回收站里的账单恢复到正常列表。

    做什么：把 deleted_at 清空（None）就表示「不再处于删除状态」，
    同时刷新 updated_at，最后返回恢复后的账单。
    参数 expense_id：要恢复的账单 id。
    参数 session：数据库会话，由框架注入。
    返回：恢复后的 ExpenseOut；账单不存在时抛 404（已在正常列表里也可以重复恢复）。
    """
    # 这里不用 _get_active_expense：那个函数会把「已删除」当错误，而恢复恰恰要操作已删除的。
    expense = session.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="这笔记录不存在")
    # 清空删除时间 = 撤销软删除；这就是「恢复」的全部动作，数据一直都在，所以不会丢东西。
    expense.deleted_at = None
    expense.updated_at = iso_now()
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return to_expense_out(expense, load_categories(session))
