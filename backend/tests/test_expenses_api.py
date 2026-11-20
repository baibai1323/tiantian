"""账单接口 HTTP 层测试：新增 / 列表筛选 / 详情 / 修改 / 软删除 / 回收站 / 恢复 / 彻底删除。

全部用 TestClient 走真实请求管线，复用 conftest 里的内存库夹具。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.db import get_session
from app.main import app
from app.models import Category, Expense
from app.routers import expenses as expenses_router

BASE = "/api/expenses"


# ---------------------------------------------------------------- 夹具 / 小工具


@pytest.fixture
def client(seeded):
    def override_get_session():
        yield seeded

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def category_id(session, name: str) -> int:
    row = session.exec(select(Category).where(Category.name == name)).first()
    assert row is not None, f"缺少分类 {name}"
    assert row.id is not None
    return row.id


def add_expense(session, cents: int, spent_on: str, note: str = "", l2: str = "午餐") -> int:
    """直接写库造数据，返回新记录 id。"""
    l2_row = session.exec(select(Category).where(Category.name == l2)).first()
    assert l2_row is not None and l2_row.id is not None
    l1_row = session.get(Category, l2_row.parent_id)
    assert l1_row is not None and l1_row.id is not None
    expense = Expense(
        amount_cents=cents,
        category_l1=l1_row.id,
        category_l2=l2_row.id,
        spent_on=spent_on,
        note=note,
        created_at=f"{spent_on}T10:00:00+08:00",
        updated_at=f"{spent_on}T10:00:00+08:00",
    )
    session.add(expense)
    session.commit()
    session.refresh(expense)
    assert expense.id is not None
    return expense.id


def only_expense(session) -> Expense:
    rows = session.exec(select(Expense)).all()
    assert len(rows) == 1
    return rows[0]


def payload(l2: int, amount: str = "12.50", spent_on: str = "2026-01-05", note: str = "") -> dict:
    return {"amount": amount, "category_l2": l2, "spent_on": spent_on, "note": note}


# ------------------------------------------------------------------ 新增账单


def test_create_expense_returns_cents_and_category_names(client, seeded):
    lunch = category_id(seeded, "午餐")

    resp = client.post(BASE, json=payload(lunch, amount="12.50", note="午饭"))

    assert resp.status_code == 201
    body = resp.json()
    assert body["amount_cents"] == 1250
    assert body["amount_yuan"] == "12.50"
    assert (body["category_l1_name"], body["category_l2_name"]) == ("餐饮", "午餐")
    assert (body["spent_on"], body["note"]) == ("2026-01-05", "午饭")
    assert body["deleted_at"] is None
    assert body["created_at"] != ""


def test_create_expense_persists_category_l1_from_parent(client, seeded):
    lunch = category_id(seeded, "午餐")
    food = category_id(seeded, "餐饮")

    client.post(BASE, json=payload(lunch))

    assert only_expense(seeded).category_l1 == food


def test_create_expense_trims_and_truncates_note(client, seeded):
    lunch = category_id(seeded, "午餐")

    trimmed = client.post(BASE, json=payload(lunch, note="  午饭  ")).json()
    long_note = client.post(BASE, json=payload(lunch, note="备" * 250)).json()

    assert trimmed["note"] == "午饭"
    assert len(long_note["note"]) == 200


@pytest.mark.parametrize("amount", ["0", "-1", "0.001", "10000000.00"])
def test_create_expense_rejects_bad_amount(client, seeded, amount):
    lunch = category_id(seeded, "午餐")

    resp = client.post(BASE, json=payload(lunch, amount=amount))

    assert resp.status_code == 422


@pytest.mark.parametrize("spent_on", ["2026-1-5", "2026-02-30", "2026/01/05", ""])
def test_create_expense_rejects_bad_date(client, seeded, spent_on):
    lunch = category_id(seeded, "午餐")

    resp = client.post(BASE, json=payload(lunch, spent_on=spent_on))

    assert resp.status_code == 422


def test_create_expense_rejects_missing_category(client, seeded):
    resp = client.post(BASE, json=payload(999999))

    assert resp.status_code == 400
    assert resp.json()["detail"] == "请选择一个有效的二级分类"


def test_create_expense_rejects_level1_category(client, seeded):
    """把一级分类当二级传进来必须被挡住，否则 category_l1 会指向自己。"""
    food = category_id(seeded, "餐饮")

    resp = client.post(BASE, json=payload(food))

    assert resp.status_code == 400
    assert resp.json()["detail"] == "请选择一个有效的二级分类"


def test_create_expense_rejects_orphan_category(client, seeded):
    """二级分类的 parent_id 指向不存在的记录：分类数据异常。"""
    orphan = Category(name="孤儿小类", parent_id=987654)
    seeded.add(orphan)
    seeded.commit()
    seeded.refresh(orphan)

    resp = client.post(BASE, json=payload(orphan.id))

    assert resp.status_code == 400
    assert resp.json()["detail"] == "分类数据异常，请检查分类设置"


# -------------------------------------------------------------------- 列表


def test_list_expenses_defaults_to_current_month(client, seeded, monkeypatch):
    monkeypatch.setattr(expenses_router, "current_month", lambda: "2026-03")
    add_expense(seeded, 100, "2026-02-28")
    add_expense(seeded, 200, "2026-03-01")

    resp = client.get(BASE)

    assert resp.status_code == 200
    body = resp.json()
    assert (body["total"], body["sum_cents"], body["sum_yuan"]) == (1, 200, "2.00")


def test_list_expenses_month_boundary_does_not_leak_neighbors(client, seeded):
    add_expense(seeded, 100, "2026-01-31")
    add_expense(seeded, 200, "2026-02-01")

    january = client.get(BASE, params={"month": "2026-01"}).json()
    february = client.get(BASE, params={"month": "2026-02"}).json()

    assert (january["total"], january["sum_cents"]) == (1, 100)
    assert (february["total"], february["sum_cents"]) == (1, 200)


def test_list_expenses_empty_month_returns_zero_totals(client, seeded):
    body = client.get(BASE, params={"month": "2026-09"}).json()

    assert body == {"items": [], "total": 0, "sum_cents": 0, "sum_yuan": "0.00"}


@pytest.mark.parametrize("month", ["2026-13", "2026-00", "abc", "26-1", "2026-1-"])
def test_list_expenses_rejects_bad_month(client, month):
    resp = client.get(BASE, params={"month": month})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "月份格式应为 YYYY-MM"


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 1001}, {"offset": -1}],
)
def test_list_expenses_rejects_out_of_range_paging(client, params):
    resp = client.get(BASE, params=params)

    assert resp.status_code == 422


def test_list_expenses_filters_by_both_levels(client, seeded):
    lunch = category_id(seeded, "午餐")
    other_child = category_id(seeded, "未分类")
    food = category_id(seeded, "餐饮")
    other = category_id(seeded, "其他")
    add_expense(seeded, 100, "2026-01-05", l2="午餐")
    add_expense(seeded, 200, "2026-01-06", l2="未分类")

    by_l1 = client.get(BASE, params={"month": "2026-01", "category_l1": food}).json()
    by_l2 = client.get(BASE, params={"month": "2026-01", "category_l2": other_child}).json()
    crossed = client.get(
        BASE, params={"month": "2026-01", "category_l1": other, "category_l2": lunch}
    ).json()

    assert (by_l1["total"], by_l1["sum_cents"]) == (1, 100)
    assert (by_l2["total"], by_l2["sum_cents"]) == (1, 200)
    assert crossed["total"] == 0


def test_list_expenses_searches_note_and_ignores_blank_query(client, seeded):
    add_expense(seeded, 100, "2026-01-05", note="公司聚餐")
    add_expense(seeded, 200, "2026-01-06", note="打车")

    hit = client.get(BASE, params={"month": "2026-01", "q": "聚餐"}).json()
    blank = client.get(BASE, params={"month": "2026-01", "q": "   "}).json()

    assert (hit["total"], hit["sum_cents"]) == (1, 100)
    assert blank["total"] == 2


def test_list_expenses_paging_keeps_full_total(client, seeded):
    newest = add_expense(seeded, 300, "2026-01-03")
    middle = add_expense(seeded, 200, "2026-01-02")
    oldest = add_expense(seeded, 100, "2026-01-01")

    body = client.get(BASE, params={"month": "2026-01", "limit": 2, "offset": 1}).json()

    assert [item["id"] for item in body["items"]] == [middle, oldest]
    assert body["total"] == 3
    assert body["sum_cents"] == 600
    assert newest not in [item["id"] for item in body["items"]]


def test_list_expenses_orders_by_date_desc_then_id_desc(client, seeded):
    first = add_expense(seeded, 100, "2026-01-05")
    second = add_expense(seeded, 200, "2026-01-05")
    older = add_expense(seeded, 300, "2026-01-03")

    ids = [item["id"] for item in client.get(BASE, params={"month": "2026-01"}).json()["items"]]

    assert ids == [second, first, older]


def test_list_expenses_excludes_deleted_unless_asked(client, seeded):
    keep = add_expense(seeded, 100, "2026-01-05")
    drop = add_expense(seeded, 200, "2026-01-06")
    client.delete(f"{BASE}/{drop}")

    visible = client.get(BASE, params={"month": "2026-01"}).json()
    with_deleted = client.get(
        BASE, params={"month": "2026-01", "include_deleted": True}
    ).json()

    assert [item["id"] for item in visible["items"]] == [keep]
    assert (visible["total"], visible["sum_cents"]) == (1, 100)
    assert (with_deleted["total"], with_deleted["sum_cents"]) == (2, 300)
    assert {item["id"] for item in with_deleted["items"]} == {keep, drop}


# -------------------------------------------------------------------- 详情


def test_get_expense_returns_single_record(client, seeded):
    expense_id = add_expense(seeded, 2800, "2026-01-05", note="午饭")

    resp = client.get(f"{BASE}/{expense_id}")

    assert resp.status_code == 200
    assert resp.json()["amount_yuan"] == "28.00"


def test_get_expense_404_when_missing(client):
    resp = client.get(f"{BASE}/424242")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "这笔记录不存在或已删除"


def test_get_expense_404_when_soft_deleted(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05")
    client.delete(f"{BASE}/{expense_id}")

    resp = client.get(f"{BASE}/{expense_id}")

    assert resp.status_code == 404


# -------------------------------------------------------------------- 修改


def test_patch_expense_updates_all_fields(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05", note="旧")
    other_child = category_id(seeded, "未分类")
    other_root = category_id(seeded, "其他")

    resp = client.patch(
        f"{BASE}/{expense_id}",
        json={"amount": "33.30", "category_l2": other_child, "spent_on": "2026-02-01", "note": "新"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["amount_cents"] == 3330
    assert body["amount_yuan"] == "33.30"
    assert (body["category_l1"], body["category_l1_name"]) == (other_root, "其他")
    assert (body["category_l2"], body["category_l2_name"]) == (other_child, "未分类")
    assert (body["spent_on"], body["note"]) == ("2026-02-01", "新")


def test_patch_expense_partial_keeps_other_fields(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05", note="旧")

    resp = client.patch(f"{BASE}/{expense_id}", json={"note": "只改备注"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["note"] == "只改备注"
    assert (body["amount_cents"], body["spent_on"]) == (100, "2026-01-05")


def test_patch_expense_empty_body_is_noop(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05")

    resp = client.patch(f"{BASE}/{expense_id}", json={})

    assert resp.status_code == 200
    assert resp.json()["amount_cents"] == 100


def test_patch_expense_explicit_null_does_not_clear_fields(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05", note="旧")

    resp = client.patch(
        f"{BASE}/{expense_id}", json={"amount": None, "spent_on": None, "note": None}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert (body["amount_cents"], body["spent_on"], body["note"]) == (100, "2026-01-05", "旧")


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"amount": "0"}, 422),
        ({"amount": "-0.01"}, 422),
        ({"amount": "1.234"}, 422),
        ({"spent_on": "2026-1-5"}, 422),
        ({"category_l2": 999999}, 400),
    ],
)
def test_patch_expense_rejects_bad_payload(client, seeded, body, status):
    expense_id = add_expense(seeded, 100, "2026-01-05")

    resp = client.patch(f"{BASE}/{expense_id}", json=body)

    assert resp.status_code == status
    assert only_expense(seeded).amount_cents == 100


def test_patch_expense_404_when_missing(client):
    resp = client.patch(f"{BASE}/999999", json={"note": "x"})

    assert resp.status_code == 404


def test_patch_expense_404_when_deleted(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05")
    client.delete(f"{BASE}/{expense_id}")

    resp = client.patch(f"{BASE}/{expense_id}", json={"note": "x"})

    assert resp.status_code == 404


# --------------------------------------------------- 软删除 / 回收站 / 恢复


def test_delete_expense_soft_deletes(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05")

    resp = client.delete(f"{BASE}/{expense_id}")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    row = seeded.get(Expense, expense_id)
    assert row is not None
    assert row.deleted_at is not None


def test_delete_expense_twice_is_404(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05")
    client.delete(f"{BASE}/{expense_id}")

    resp = client.delete(f"{BASE}/{expense_id}")

    assert resp.status_code == 404


def test_delete_missing_expense_is_404(client):
    resp = client.delete(f"{BASE}/888888")

    assert resp.status_code == 404


def test_trash_lists_deleted_newest_first_with_sum(client, seeded, monkeypatch):
    first = add_expense(seeded, 100, "2026-01-05")
    second = add_expense(seeded, 250, "2026-01-06")
    stamps = iter(["2026-02-01T10:00:00+08:00", "2026-02-02T10:00:00+08:00"])
    monkeypatch.setattr(expenses_router, "iso_now", lambda: next(stamps))

    client.delete(f"{BASE}/{first}")
    client.delete(f"{BASE}/{second}")
    body = client.get(f"{BASE}/trash").json()

    assert [item["id"] for item in body["items"]] == [second, first]
    assert (body["total"], body["sum_cents"], body["sum_yuan"]) == (2, 350, "3.50")


def test_trash_paging_and_empty_state(client, seeded):
    ids = []
    for day in (1, 2, 3):
        expense_id = add_expense(seeded, day * 100, f"2026-01-0{day}")
        client.delete(f"{BASE}/{expense_id}")
        ids.append(expense_id)

    body = client.get(f"{BASE}/trash", params={"limit": 2, "offset": 1}).json()
    empty = client.get(BASE, params={"month": "2026-05"}).json()

    assert [item["id"] for item in body["items"]] == [ids[1], ids[0]]
    assert body["total"] == 3
    assert body["sum_cents"] == 600
    assert empty["total"] == 0


def test_empty_trash_purges_only_deleted_rows(client, seeded):
    keep = add_expense(seeded, 100, "2026-01-05")
    gone_a = add_expense(seeded, 200, "2026-01-06")
    gone_b = add_expense(seeded, 300, "2026-01-07")
    client.delete(f"{BASE}/{gone_a}")
    client.delete(f"{BASE}/{gone_b}")

    resp = client.delete(f"{BASE}/trash")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": 2}
    remaining = [row.id for row in seeded.exec(select(Expense)).all()]
    assert remaining == [keep]


def test_empty_trash_when_already_empty(client):
    resp = client.delete(f"{BASE}/trash")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": 0}


def test_restore_expense_returns_to_active_list(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05")
    client.delete(f"{BASE}/{expense_id}")

    resp = client.post(f"{BASE}/{expense_id}/restore")

    assert resp.status_code == 200
    assert resp.json()["deleted_at"] is None
    assert client.get(BASE, params={"month": "2026-01"}).json()["total"] == 1
    assert client.get(f"{BASE}/trash").json()["total"] == 0


def test_restore_missing_expense_is_404(client):
    resp = client.post(f"{BASE}/777777/restore")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "这笔记录不存在"


def test_permanent_delete_requires_prior_soft_delete(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05")

    resp = client.delete(f"{BASE}/{expense_id}/permanent")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "请先删除这笔记录，再彻底删除"
    assert seeded.get(Expense, expense_id) is not None


def test_permanent_delete_removes_deleted_row(client, seeded):
    expense_id = add_expense(seeded, 100, "2026-01-05")
    client.delete(f"{BASE}/{expense_id}")

    resp = client.delete(f"{BASE}/{expense_id}/permanent")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert seeded.get(Expense, expense_id) is None
    assert client.get(f"{BASE}/trash").json()["total"] == 0


def test_permanent_delete_missing_is_404(client):
    resp = client.delete(f"{BASE}/666666/permanent")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "这笔记录不存在"
