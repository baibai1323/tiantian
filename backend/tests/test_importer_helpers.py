"""CSV 导入的四个纯函数：表头归一化、列名映射、日期解析、金额解析。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.importer import _normalize_header, _parse_cents, _parse_date, _pick_columns


# ---------- _normalize_header ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("金额（元）", "金额(元)"),
        ("日 期", "日期"),
        ("  备注  ", "备注"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_header(raw, expected):
    assert _normalize_header(raw) == expected


# ---------- _pick_columns ----------


def test_pick_columns_standard_header():
    cols = _pick_columns(["日期", "一级分类", "二级分类", "金额(元)", "备注"])

    assert cols == {
        "date": "日期",
        "l1": "一级分类",
        "l2": "二级分类",
        "amount": "金额(元)",
        "note": "备注",
    }


def test_pick_columns_accepts_aliases():
    cols = _pick_columns(["时间", "大类", "小类", "支出", "说明"])

    assert cols["date"] == "时间"
    assert cols["l1"] == "大类"
    assert cols["l2"] == "小类"
    assert cols["amount"] == "支出"
    assert cols["note"] == "说明"


def test_pick_columns_tolerates_fullwidth_parens():
    cols = _pick_columns(["日期", "一级分类", "二级分类", "金额（元）"])

    assert cols["amount"] == "金额（元）"


def test_pick_columns_note_is_optional():
    cols = _pick_columns(["日期", "一级分类", "二级分类", "金额(元)"])

    assert "note" not in cols


@pytest.mark.parametrize(
    "header, missing_label",
    [
        (["一级分类", "二级分类", "金额(元)"], "日期"),
        (["日期", "二级分类", "金额(元)"], "一级分类"),
        (["日期", "一级分类", "金额(元)"], "二级分类"),
        (["日期", "一级分类", "二级分类"], "金额(元)"),
    ],
)
def test_pick_columns_reports_each_missing_column(header, missing_label):
    with pytest.raises(HTTPException) as exc:
        _pick_columns(header)

    assert exc.value.status_code == 400
    assert missing_label in exc.value.detail


def test_pick_columns_ignores_empty_fieldname():
    cols = _pick_columns(["日期", "", "一级分类", "二级分类", "金额(元)"])

    assert cols["date"] == "日期"


# ---------- _parse_date ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-11-16", "2026-11-16"),
        ("2026/11/16", "2026-11-16"),
        ("2026.11.16", "2026-11-16"),
        ("  2026-11-16  ", "2026-11-16"),
        ("2026-1-6", "2026-01-06"),
    ],
)
def test_parse_date_accepts_and_normalizes(raw, expected):
    assert _parse_date(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "2026-13-01", "2026-02-30", "16/11/2026", "昨天", "2026-11"],
)
def test_parse_date_rejects_garbage(raw):
    assert _parse_date(raw) is None


# ---------- _parse_cents ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("28.00", 2800),
        ("28.5", 2850),
        ("1,234.56", 123456),
        ("¥28", 2800),
        ("￥28.00", 2800),
        ("0.01", 1),
        ("9999999.99", 999999999),
        ("  28.00  ", 2800),
    ],
)
def test_parse_cents_accepts(raw, expected):
    assert _parse_cents(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "0", "0.00", "-1", "-0.01", "28.567", "10000000", "10000000.00", "abc", "1.2.3"],
)
def test_parse_cents_rejects(raw):
    assert _parse_cents(raw) is None
