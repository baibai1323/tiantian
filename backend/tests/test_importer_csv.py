"""import_csv 的行为测试：直接调用函数 + 内存数据库，不走 HTTP 层。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.models import Category, Expense
from app.routers.importer import import_csv
from app.schemas import ImportRequest

HEADER = "日期,一级分类,二级分类,金额(元),备注"
GOOD_ROW = "2026-11-16,餐饮,午餐,28.00,午饭"


def make_csv(*rows: str, header: str = HEADER) -> str:
    return header + "\n" + "\n".join(rows) + "\n"


def run(session, content: str):
    return import_csv(ImportRequest(content=content), session)


# ---------- 正常路径 ----------


def test_imports_one_row_and_writes_expense(seeded):
    result = run(seeded, make_csv(GOOD_ROW))

    assert (result.imported, result.duplicates, result.invalid, result.fallback) == (1, 0, 0, 0)
    row = seeded.exec(select(Expense)).one()
    assert row.amount_cents == 2800
    assert row.spent_on == "2026-11-16"
    assert row.note == "午饭"


def test_created_and_updated_at_are_filled(seeded):
    run(seeded, make_csv(GOOD_ROW))

    row = seeded.exec(select(Expense)).one()
    assert row.created_at != ""
    assert row.created_at == row.updated_at


def test_bom_prefix_is_stripped(seeded):
    result = run(seeded, "\ufeff" + make_csv(GOOD_ROW))

    assert result.imported == 1


# ---------- 幂等与去重 ----------


def test_reimporting_same_file_yields_duplicates(seeded):
    run(seeded, make_csv(GOOD_ROW))

    result = run(seeded, make_csv(GOOD_ROW))

    assert (result.imported, result.duplicates) == (0, 1)
    assert len(seeded.exec(select(Expense)).all()) == 1


def test_duplicate_rows_inside_one_file_are_counted(seeded):
    result = run(seeded, make_csv(GOOD_ROW, GOOD_ROW))

    assert (result.imported, result.duplicates) == (1, 1)


# ---------- 非法行 ----------


def test_invalid_date_is_reported_with_line_number(seeded):
    result = run(seeded, make_csv("2026-13-01,餐饮,午餐,28.00,午饭"))

    assert result.invalid == 1
    assert result.imported == 0
    assert result.errors[0].line == 2
    assert "日期" in result.errors[0].reason


def test_invalid_amount_is_reported(seeded):
    result = run(seeded, make_csv("2026-11-16,餐饮,午餐,28.567,午饭"))

    assert result.invalid == 1
    assert "金额" in result.errors[0].reason


def test_one_bad_row_does_not_block_the_rest(seeded):
    result = run(seeded, make_csv("坏日期,餐饮,午餐,28.00,坏行", GOOD_ROW))

    assert (result.imported, result.invalid) == (1, 1)


def test_errors_are_capped_at_50(seeded):
    rows = ["坏日期,餐饮,午餐,1.00,x"] * 60

    result = run(seeded, make_csv(*rows))

    assert result.invalid == 60
    assert len(result.errors) == 50


# ---------- 分类兜底 ----------


def test_unknown_category_falls_back_to_other(seeded):
    result = run(seeded, make_csv("2026-11-16,不存在的一级,不存在的二级,28.00,备注"))

    assert (result.imported, result.fallback) == (1, 1)
    assert "归入" in result.warnings[0].reason

    other = seeded.exec(select(Category).where(Category.name == "其他")).one()
    unclassified = seeded.exec(select(Category).where(Category.name == "未分类")).one()
    row = seeded.exec(select(Expense)).one()
    assert (row.category_l1, row.category_l2) == (other.id, unclassified.id)


def test_other_without_named_child_uses_first_child(session):
    """「其他」下没有 未分类/手续费/其他 时，退而取第一个子分类。"""
    other = Category(name="其他", icon="❓")
    session.add(other)
    session.commit()
    session.refresh(other)
    session.add(Category(name="杂项", icon="🧩", parent_id=other.id))
    session.commit()

    result = run(session, make_csv("2026-11-16,不存在,不存在,28.00,备注"))

    assert (result.imported, result.fallback) == (1, 1)
    misc = session.exec(select(Category).where(Category.name == "杂项")).one()
    assert session.exec(select(Expense)).one().category_l2 == misc.id


def test_known_l1_but_unknown_l2_falls_back(seeded):
    result = run(seeded, make_csv("2026-11-16,餐饮,不存在的二级,28.00,备注"))

    assert result.fallback == 1


# ---------- 文件级异常 ----------


@pytest.mark.parametrize("content", ["", "   ", "\n\n"])
def test_empty_content_raises_400(seeded, content):
    with pytest.raises(HTTPException) as exc:
        run(seeded, content)

    assert exc.value.status_code == 400
    assert "空" in exc.value.detail


def test_missing_required_column_raises_400(seeded):
    with pytest.raises(HTTPException) as exc:
        run(seeded, make_csv(GOOD_ROW, header="日期,一级分类,二级分类,备注"))

    assert exc.value.status_code == 400
    assert "金额(元)" in exc.value.detail


def test_missing_header_raises_400(seeded):
    with pytest.raises(HTTPException) as exc:
        run(seeded, "\n2026-11-16,餐饮,午餐,28.00,午饭\n")

    assert exc.value.status_code == 400
    assert "表头" in exc.value.detail


def test_categories_missing_raises_500(session):
    with pytest.raises(HTTPException) as exc:
        run(session, make_csv(GOOD_ROW))

    assert exc.value.status_code == 500
    assert "分类数据不完整" in exc.value.detail


# ---------- 边界 ----------


def test_too_many_rows_raises_400(seeded):
    rows = [GOOD_ROW] * 20001

    with pytest.raises(HTTPException) as exc:
        run(seeded, make_csv(*rows))

    assert exc.value.status_code == 400
    assert "20000" in exc.value.detail


def test_note_is_truncated_to_200_chars(seeded):
    result = run(seeded, make_csv(f"2026-11-16,餐饮,午餐,28.00,{'x' * 300}"))

    assert result.imported == 1
    assert len(seeded.exec(select(Expense)).one().note) == 200


def test_soft_deleted_expense_still_blocks_reimport(seeded):
    """当前行为：软删除的账单仍参与去重，删了再导入会被判为重复。疑似 bug，见交付报告。"""
    run(seeded, make_csv(GOOD_ROW))
    row = seeded.exec(select(Expense)).one()
    row.deleted_at = "2026-11-17T00:00:00+08:00"
    seeded.add(row)
    seeded.commit()

    result = run(seeded, make_csv(GOOD_ROW))

    assert (result.imported, result.duplicates) == (0, 1)
