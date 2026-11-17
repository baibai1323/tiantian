"""CSV 导入（只接受本应用导出的格式）。

设计取舍（D-013）：
- 文件在浏览器端读成文本，接口收 JSON，避免额外引入 multipart 依赖；
- 重复判断：日期 + 金额 + 一级分类 + 二级分类 + 备注 完全相同；
- 分类对不上时归入「其他 / 未分类」并记一条警告，不丢账单。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import Expense
from ..schemas import ImportIssue, ImportRequest, ImportResult
from ..services import load_categories
from ..utils import iso_now, yuan_to_cents

router = APIRouter(prefix="/api/import", tags=["import"])

MAX_ROWS = 20000


def _normalize_header(value: str | None) -> str:
    return (value or "").replace("（", "(").replace("）", ")").replace(" ", "").strip()


def _pick_columns(fieldnames: list[str]) -> dict[str, str]:
    """把实际表头映射到标准字段，容忍全角括号和少量别名。"""
    normalized = {_normalize_header(name): name for name in fieldnames if name}
    aliases = {
        "date": ("日期", "时间", "日 期"),
        "l1": ("一级分类", "大类"),
        "l2": ("二级分类", "小类"),
        "amount": ("金额(元)", "金额", "支出(元)", "支出"),
        "note": ("备注", "说明"),
    }
    found: dict[str, str] = {}
    for key, names in aliases.items():
        for name in names:
            if _normalize_header(name) in normalized:
                found[key] = normalized[_normalize_header(name)]
                break
    missing = [label for key, label in (("date", "日期"), ("l1", "一级分类"), ("l2", "二级分类"), ("amount", "金额(元)")) if key not in found]
    if missing:
        raise HTTPException(status_code=400, detail="CSV 缺少列：" + "、".join(missing))
    return found


def _parse_date(raw: str) -> str | None:
    text = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _parse_cents(raw: str) -> int | None:
    text = (raw or "").strip().replace(",", "").replace("¥", "").replace("￥", "")
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if value <= 0 or value > Decimal("9999999.99") or value.as_tuple().exponent < -2:
        return None
    return yuan_to_cents(value)


@router.post("/csv", response_model=ImportResult)
def import_csv(payload: ImportRequest, session: Session = Depends(get_session)) -> ImportResult:
    content = payload.content.lstrip("\ufeff")
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件是空的")

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="没有读到表头，请确认是天天记账导出的 CSV")
    columns = _pick_columns(list(reader.fieldnames))

    nodes = load_categories(session)
    l1_by_name = {node.name: node.id for node in nodes.values() if node.parent_id is None}
    l2_by_name: dict[tuple[int, str], int] = {}
    for node in nodes.values():
        if node.parent_id is not None and node.parent_id in nodes:
            l2_by_name[(node.parent_id, node.name)] = node.id

    other_l1 = l1_by_name.get("其他")
    other_l2: int | None = None
    if other_l1 is not None:
        for name in ("未分类", "手续费", "其他"):
            other_l2 = l2_by_name.get((other_l1, name))
            if other_l2 is not None:
                break
        if other_l2 is None:
            other_l2 = next(
                (child for (parent, _name), child in l2_by_name.items() if parent == other_l1),
                None,
            )
    if other_l1 is None or other_l2 is None:
        raise HTTPException(status_code=500, detail="分类数据不完整，缺少「其他」兜底分类")

    existing = {
        (row.spent_on, row.amount_cents, row.category_l1, row.category_l2, row.note)
        for row in session.exec(select(Expense)).all()
    }
    seen = set(existing)

    now = iso_now()
    imported = duplicates = invalid = fallback = 0
    errors: list[ImportIssue] = []
    warnings: list[ImportIssue] = []

    for index, raw_row in enumerate(reader, start=2):
        if index > MAX_ROWS + 1:
            raise HTTPException(status_code=400, detail=f"一次最多导入 {MAX_ROWS} 行")

        spent_on = _parse_date(raw_row.get(columns["date"], ""))
        if spent_on is None:
            invalid += 1
            if len(errors) < 50:
                errors.append(ImportIssue(line=index, reason="日期无法识别（应为 2026-11-16 这种格式）"))
            continue

        amount_cents = _parse_cents(raw_row.get(columns["amount"], ""))
        if amount_cents is None:
            invalid += 1
            if len(errors) < 50:
                errors.append(ImportIssue(line=index, reason="金额无法识别（应为大于 0、最多两位小数的数字）"))
            continue

        l1_name = (raw_row.get(columns["l1"], "") or "").strip()
        l2_name = (raw_row.get(columns["l2"], "") or "").strip()
        l1_id = l1_by_name.get(l1_name)
        l2_id = l2_by_name.get((l1_id, l2_name)) if l1_id is not None else None
        used_fallback = l1_id is None or l2_id is None
        if used_fallback:
            l1_id, l2_id = other_l1, other_l2

        note = (raw_row.get(columns.get("note", ""), "") or "").strip()[:200]
        key = (spent_on, amount_cents, l1_id, l2_id, note)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)

        if used_fallback:
            fallback += 1
            if len(warnings) < 50:
                warnings.append(
                    ImportIssue(line=index, reason=f"分类「{l1_name} / {l2_name}」不存在，已归入「其他 / 未分类」")
                )

        session.add(
            Expense(
                amount_cents=amount_cents,
                category_l1=l1_id,
                category_l2=l2_id,
                spent_on=spent_on,
                note=note,
                created_at=now,
                updated_at=now,
            )
        )
        imported += 1

    try:
        session.commit()
    except Exception as exc:  # pragma: no cover - 兜底回滚
        session.rollback()
        raise HTTPException(status_code=500, detail=f"写入数据库失败：{exc}") from exc

    return ImportResult(
        imported=imported,
        duplicates=duplicates,
        invalid=invalid,
        fallback=fallback,
        errors=errors,
        warnings=warnings,
    )
