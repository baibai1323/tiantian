"""HTTP 层测试：月份参数在账单列表 / CSV 导出 / 统计接口上的行为。

用 TestClient 走真正的请求管线，补上「直接调用路由函数」覆盖不到的
Query 解析与 400 响应。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.db import get_session
from app.main import app
from app.models import Category, Expense


def category_id(session, name: str) -> int:
    row = session.exec(select(Category).where(Category.name == name)).first()
    assert row is not None, f"缺少分类 {name}"
    return row.id


def add_expense(session, cents: int, spent_on: str, note: str = "") -> None:
    food = category_id(session, "餐饮")
    lunch = category_id(session, "午餐")
    session.add(
        Expense(
            amount_cents=cents,
            category_l1=food,
            category_l2=lunch,
            spent_on=spent_on,
            note=note,
            created_at=f"{spent_on}T10:00:00+08:00",
        )
    )
    session.commit()


@pytest.fixture
def client(seeded):
    """把 get_session 换成测试用的内存库，但保留完整的路由与校验逻辑。"""

    def override_get_session():
        yield seeded

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_expenses_accepts_unpadded_month(client, seeded):
    add_expense(seeded, 2800, "2026-01-05", note="午饭")

    resp = client.get("/api/expenses", params={"month": "2026-1"})

    assert resp.status_code == 200
    body = resp.json()
    assert (body["total"], body["sum_cents"]) == (1, 2800)


def test_list_expenses_rejects_bad_month(client):
    resp = client.get("/api/expenses", params={"month": "2026-13"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "月份格式应为 YYYY-MM"


def test_export_csv_accepts_unpadded_month(client, seeded):
    add_expense(seeded, 2800, "2026-01-05", note="午饭")

    resp = client.get("/api/export/csv", params={"month": "2026-1"})

    assert resp.status_code == 200
    text = resp.content.decode("utf-8-sig")
    assert "2026-01-05" in text
    assert "28.00" in text


def test_export_csv_rejects_bad_month(client):
    resp = client.get("/api/export/csv", params={"month": "abc"})

    assert resp.status_code == 400


def test_summary_http_normalizes_month(client, seeded):
    add_expense(seeded, 2800, "2026-01-05")

    resp = client.get("/api/stats/summary", params={"month": "2026-1"})

    assert resp.status_code == 200
    body = resp.json()
    assert (body["month"], body["total_cents"]) == ("2026-01", 2800)


def test_list_expenses_rejects_non_four_digit_month(client):
    # "26-1" 以前会被补成 "0026-01"，当作合法月份。
    resp = client.get("/api/expenses", params={"month": "26-1"})

    assert resp.status_code == 400


def test_create_expense_rejects_unpadded_date(client, seeded):
    lunch = category_id(seeded, "午餐")
    resp = client.post(
        "/api/expenses",
        json={"amount": "12.50", "category_l2": lunch, "spent_on": "2026-1-5", "note": ""},
    )

    assert resp.status_code == 422


def test_create_expense_rejects_amount_over_limit(client, seeded):
    lunch = category_id(seeded, "午餐")
    resp = client.post(
        "/api/expenses",
        json={"amount": "10000000.00", "category_l2": lunch, "spent_on": "2026-01-05"},
    )

    assert resp.status_code == 422


def test_patch_expense_rejects_amount_over_limit(client, seeded):
    add_expense(seeded, 1250, "2026-01-05")
    expense = seeded.exec(select(Expense)).first()
    assert expense is not None

    resp = client.patch(f"/api/expenses/{expense.id}", json={"amount": "10000000.00"})

    assert resp.status_code == 422


def test_search_escapes_like_wildcards(client, seeded):
    add_expense(seeded, 100, "2026-01-05", note="折扣 100%")
    add_expense(seeded, 200, "2026-01-06", note="普通备注")

    percent = client.get("/api/expenses", params={"month": "2026-01", "q": "%"})
    underscore = client.get("/api/expenses", params={"month": "2026-01", "q": "_"})

    assert percent.json()["total"] == 1
    assert underscore.json()["total"] == 0


def test_search_matches_secondary_category_name(client, seeded):
    # 前端占位符承诺「搜备注、二级分类」，只匹配备注会让人以为坏了。
    add_expense(seeded, 100, "2026-01-05", note="和同事吃饭")
    other = category_id(seeded, "其他")
    uncategorized = category_id(seeded, "未分类")
    seeded.add(
        Expense(
            amount_cents=200,
            category_l1=other,
            category_l2=uncategorized,
            spent_on="2026-01-06",
            note="打车",
            created_at="2026-01-06T10:00:00+08:00",
        )
    )
    seeded.commit()

    resp = client.get("/api/expenses", params={"month": "2026-01", "q": "午餐"})

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_export_csv_guards_formula_injection(client, seeded):
    # 备注以 = 开头时，Excel 会当公式执行；导出必须加文本标记。
    add_expense(seeded, 100, "2026-01-05", note="=HYPERLINK(\"http://evil\")")

    resp = client.get("/api/export/csv", params={"month": "2026-01"})

    assert resp.status_code == 200
    text = resp.content.decode("utf-8-sig")
    assert "'=HYPERLINK" in text


def test_import_csv_undoes_formula_guard(client, seeded):
    # 再导回来时要去掉导出加的单引号，否则备注会被悄悄改写。
    csv_text = (
        "日期,一级分类,二级分类,金额(元),备注\n"
        "2026-01-07,餐饮,午餐,3.00,'=1+1\n"
    )

    resp = client.post("/api/import/csv", json={"content": csv_text})

    assert resp.status_code == 200
    assert resp.json()["imported"] == 1
    row = seeded.exec(select(Expense)).first()
    assert row is not None
    assert row.note == "=1+1"
