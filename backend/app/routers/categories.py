"""分类接口：查询树、管理（新增 / 改名 / 删除自定义分类）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func
from sqlmodel import Session, select

from ..db import get_session
from ..models import Category, Expense
from ..schemas import (
    CategoryCreate,
    CategoryDeleteResult,
    CategoryManageNode,
    CategoryNode,
    CategoryUpdate,
)
from ..utils import iso_now

router = APIRouter(prefix="/api/categories", tags=["categories"])

MAX_NAME_LEN = 16


def _clean_name(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="分类名不能为空")
    if len(name) > MAX_NAME_LEN:
        raise HTTPException(status_code=400, detail=f"分类名最多 {MAX_NAME_LEN} 个字")
    if any(ch in name for ch in "\r\n\t"):
        raise HTTPException(status_code=400, detail="分类名里不能有换行或制表符")
    return name


def _ensure_unique(
    session: Session, parent_id: int | None, name: str, exclude_id: int | None = None
) -> None:
    stmt = select(Category).where(Category.name == name)
    if parent_id is None:
        stmt = stmt.where(Category.parent_id.is_(None))
    else:
        stmt = stmt.where(Category.parent_id == parent_id)
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    if session.exec(stmt).first() is not None:
        raise HTTPException(status_code=400, detail=f"同一级下已经有「{name}」了")


def _fallback_pair(session: Session) -> tuple[Category, Category]:
    """删除分类时，账单统一迁到「其他 / 未分类」。"""
    root = session.exec(
        select(Category).where(Category.parent_id.is_(None), Category.name == "其他")
    ).first()
    if root is None:
        raise HTTPException(status_code=500, detail="缺少「其他」兜底分类，请检查数据")
    child = session.exec(
        select(Category).where(Category.parent_id == root.id, Category.name == "未分类")
    ).first()
    if child is None:
        child = session.exec(
            select(Category)
            .where(Category.parent_id == root.id)
            .order_by(Category.sort_order, Category.id)
        ).first()
    if child is None:
        raise HTTPException(status_code=500, detail="缺少「其他」下的兜底小类，请检查数据")
    return root, child


@router.get("", response_model=list[CategoryNode])
def list_categories(session: Session = Depends(get_session)) -> list[CategoryNode]:
    rows = session.exec(
        select(Category)
        .where(Category.is_active == True)  # noqa: E712 - SQLAlchemy 需要显式比较
        .order_by(Category.sort_order, Category.id)
    ).all()

    nodes: dict[int, CategoryNode] = {}
    roots: list[CategoryNode] = []
    for row in rows:
        node = CategoryNode(id=row.id or 0, name=row.name, icon=row.icon)
        nodes[row.id] = node  # type: ignore[index]
        if row.parent_id is None:
            roots.append(node)

    for row in rows:
        if row.parent_id is not None and row.parent_id in nodes:
            nodes[row.parent_id].children.append(nodes[row.id])  # type: ignore[index]

    return roots


@router.get("/manage", response_model=list[CategoryManageNode])
def manage_categories(session: Session = Depends(get_session)) -> list[CategoryManageNode]:
    rows = session.exec(select(Category).order_by(Category.sort_order, Category.id)).all()
    counts = dict(
        session.exec(
            select(Expense.category_l2, func.count())
            .where(Expense.deleted_at.is_(None))
            .group_by(Expense.category_l2)
        ).all()
    )

    nodes: dict[int, CategoryManageNode] = {}
    roots: list[CategoryManageNode] = []
    for row in rows:
        node = CategoryManageNode(
            id=row.id or 0,
            name=row.name,
            icon=row.icon,
            is_system=row.is_system,
            expense_count=int(counts.get(row.id, 0)),
        )
        nodes[row.id] = node
        if row.parent_id is None:
            roots.append(node)

    for row in rows:
        if row.parent_id is not None and row.parent_id in nodes:
            nodes[row.parent_id].children.append(nodes[row.id])  # type: ignore[index]

    for root in roots:
        root.expense_count += sum(child.expense_count for child in root.children)

    return roots


@router.post("", response_model=CategoryNode, status_code=201)
def create_category(
    payload: CategoryCreate, session: Session = Depends(get_session)
) -> CategoryNode:
    name = _clean_name(payload.name)
    parent_id = payload.parent_id

    if parent_id is not None:
        parent = session.get(Category, parent_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="上级分类不存在")
        if parent.parent_id is not None:
            raise HTTPException(status_code=400, detail="分类最多两级，不能在二级分类下继续加")
        parent_id = parent.id

    _ensure_unique(session, parent_id, name)

    max_order = session.exec(
        select(func.max(Category.sort_order)).where(
            Category.parent_id.is_(None) if parent_id is None else Category.parent_id == parent_id
        )
    ).one()
    category = Category(
        parent_id=parent_id,
        name=name,
        icon=(payload.icon or "").strip()[:8],
        sort_order=int(max_order or 0) + 1,
        is_active=True,
        is_system=False,
        created_at=iso_now(),
    )
    session.add(category)
    session.commit()
    session.refresh(category)
    return CategoryNode(id=category.id or 0, name=category.name, icon=category.icon)


@router.patch("/{category_id}", response_model=CategoryNode)
def update_category(
    category_id: int, payload: CategoryUpdate, session: Session = Depends(get_session)
) -> CategoryNode:
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    if category.is_system:
        raise HTTPException(status_code=403, detail="系统自带分类不能修改")

    if payload.name is not None:
        name = _clean_name(payload.name)
        _ensure_unique(session, category.parent_id, name, exclude_id=category_id)
        category.name = name
    if payload.icon is not None:
        category.icon = payload.icon.strip()[:8]

    session.add(category)
    session.commit()
    session.refresh(category)
    return CategoryNode(id=category.id or 0, name=category.name, icon=category.icon)


@router.delete("/{category_id}", response_model=CategoryDeleteResult)
def delete_category(
    category_id: int, session: Session = Depends(get_session)
) -> CategoryDeleteResult:
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    if category.is_system:
        raise HTTPException(status_code=403, detail="系统自带分类不能删除")
    if category.name == "未分类" and category.parent_id is None:
        raise HTTPException(status_code=400, detail="兜底分类不能删除")

    if category.parent_id is None:
        child_ids = [
            row.id
            for row in session.exec(
                select(Category).where(Category.parent_id == category_id)
            ).all()
        ]
    else:
        child_ids = [category_id]

    fallback_l1, fallback_l2 = _fallback_pair(session)
    migrated = 0
    if child_ids:
        expenses = session.exec(
            select(Expense).where(Expense.category_l2.in_(child_ids))
        ).all()
        for expense in expenses:
            expense.category_l1 = fallback_l1.id
            expense.category_l2 = fallback_l2.id
            session.add(expense)
        migrated = len(expenses)
        session.flush()

        if category.parent_id is None:
            session.exec(delete(Category).where(Category.parent_id == category_id))
            session.flush()

    session.delete(category)
    session.commit()
    return CategoryDeleteResult(migrated=migrated)
