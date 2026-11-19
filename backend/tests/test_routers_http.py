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
