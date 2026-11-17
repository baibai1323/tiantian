"""分类接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import Category
from ..schemas import CategoryNode

router = APIRouter(prefix="/api/categories", tags=["categories"])


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
