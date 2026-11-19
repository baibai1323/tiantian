"""CSV 导出（C+5）。"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..db import get_session
from ..models import Expense
from ..services import load_categories
from ..utils import cents_to_yuan, is_valid_month, normalize_month

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/csv")
def export_csv(
    month: str | None = Query(default=None, description="YYYY-MM，不传则导出全部"),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    conditions = [Expense.deleted_at.is_(None)]
    if month:
        month = normalize_month(month)
        if not is_valid_month(month):
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")
        conditions.append(Expense.spent_on.like(f"{month}-%"))

    rows = session.exec(
        select(Expense).where(*conditions).order_by(Expense.spent_on, Expense.id)
    ).all()
    categories = load_categories(session)

    buffer = io.StringIO()
    buffer.write("\ufeff")  # BOM：让 Excel 正确识别 UTF-8 中文
    writer = csv.writer(buffer)
    writer.writerow(["日期", "一级分类", "二级分类", "金额(元)", "备注"])
    for row in rows:
        l1 = categories.get(row.category_l1)
        l2 = categories.get(row.category_l2)
        writer.writerow(
            [
                row.spent_on,
                l1.name if l1 else "",
                l2.name if l2 else "",
                cents_to_yuan(row.amount_cents),
                row.note,
            ]
        )

    filename = f"tiantian-{month or 'all'}.csv"
    return StreamingResponse(
        iter([buffer.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
