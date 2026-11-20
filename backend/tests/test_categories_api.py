"""分类接口 HTTP 层测试：树查询 / 管理视图 / 新增 / 改名 / 删除与账单迁移。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.db import get_session
from app.main import app
from app.models import Category, Expense

BASE = "/api/categories"


@pytest.fixture
def client(seeded):
    def override_get_session():
        yield seeded

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def empty_client(session):
    """不种数据的空库客户端，用来测空表行为。"""

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def find(session, name: str) -> Category:
    row = session.exec(select(Category).where(Category.name == name)).first()
    assert row is not None, f"缺少分类 {name}"
    return row


def make_custom(session, name: str, parent: Category | None = None, icon: str = "") -> Category:
    """直接写库造一个自定义分类（is_system=False），绕过接口的排序逻辑。"""
    row = Category(
        name=name,
        icon=icon,
        parent_id=parent.id if parent else None,
        is_system=False,
        sort_order=99,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def add_expense(session, cents: int, l2: Category, deleted: bool = False) -> Expense:
    l1 = session.get(Category, l2.parent_id)
    assert l1 is not None
    row = Expense(
        amount_cents=cents,
        category_l1=l1.id,
        category_l2=l2.id,
        spent_on="2026-01-05",
        note="",
        created_at="2026-01-05T10:00:00+08:00",
        deleted_at="2026-01-06T10:00:00+08:00" if deleted else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# ------------------------------------------------------------------ 树查询


def test_list_categories_builds_two_level_tree(client, seeded):
    resp = client.get(BASE)

    assert resp.status_code == 200
    roots = {node["name"]: node for node in resp.json()}
    assert set(roots) == {"其他", "餐饮"}
    assert [child["name"] for child in roots["餐饮"]["children"]] == ["午餐"]
    assert roots["餐饮"]["icon"] == "🍚"


def test_list_categories_skips_inactive_rows(client, seeded):
    hidden = find(seeded, "午餐")
    hidden.is_active = False
    seeded.add(hidden)
    seeded.commit()

    roots = {node["name"]: node for node in client.get(BASE).json()}

    assert roots["餐饮"]["children"] == []


def test_list_categories_empty_db_returns_empty_list(empty_client):
    assert empty_client.get(BASE).json() == []


# ------------------------------------------------------------------ 管理视图


def test_manage_categories_counts_expenses_per_level(client, seeded):
    lunch = find(seeded, "午餐")
    add_expense(seeded, 100, lunch)
    add_expense(seeded, 200, lunch)

    roots = {node["name"]: node for node in client.get(f"{BASE}/manage").json()}

    assert roots["餐饮"]["expense_count"] == 2
    assert roots["餐饮"]["children"][0]["expense_count"] == 2
    assert roots["其他"]["expense_count"] == 0
    assert roots["餐饮"]["is_system"] is True


def test_manage_categories_excludes_trashed_expenses_from_count(client, seeded):
    lunch = find(seeded, "午餐")
    add_expense(seeded, 100, lunch)
    add_expense(seeded, 200, lunch, deleted=True)

    roots = {node["name"]: node for node in client.get(f"{BASE}/manage").json()}

    assert roots["餐饮"]["expense_count"] == 1


# -------------------------------------------------------------------- 新增


def test_create_category_at_root_level(client, seeded):
    resp = client.post(BASE, json={"name": " 交通 ", "icon": "🚌"})

    assert resp.status_code == 201
    body = resp.json()
    assert (body["name"], body["icon"]) == ("交通", "🚌")
    assert body["children"] == []
    row = find(seeded, "交通")
    assert (row.is_system, row.parent_id) == (False, None)


def test_create_category_under_parent(client, seeded):
    food = find(seeded, "餐饮")

    resp = client.post(BASE, json={"parent_id": food.id, "name": "晚餐"})

    assert resp.status_code == 201
    assert find(seeded, "晚餐").parent_id == food.id


def test_create_category_assigns_increasing_sort_order(client, seeded):
    food = find(seeded, "餐饮")
    first = client.post(BASE, json={"parent_id": food.id, "name": "晚餐"}).json()
    second = client.post(BASE, json={"parent_id": food.id, "name": "夜宵"}).json()

    names = [child["name"] for child in client.get(BASE).json() if child["name"] == "餐饮"][0]
    children = next(node for node in client.get(BASE).json() if node["name"] == "餐饮")["children"]

    assert [child["name"] for child in children] == ["午餐", "晚餐", "夜宵"]
    assert first["id"] < second["id"]
    assert names  # 显式说明：排序按 sort_order 递增


@pytest.mark.parametrize("name", ["", "   ", "十" * 17, "有\t制表符", "有\n换行"])
def test_create_category_rejects_bad_name(client, name):
    resp = client.post(BASE, json={"name": name})

    assert resp.status_code == 400


def test_create_category_rejects_duplicate_under_same_parent(client, seeded):
    food = find(seeded, "餐饮")

    resp = client.post(BASE, json={"parent_id": food.id, "name": "午餐"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "同一级下已经有「午餐」了"


def test_create_category_allows_same_name_under_different_parent(client, seeded):
    other = find(seeded, "其他")

    resp = client.post(BASE, json={"parent_id": other.id, "name": "午餐"})

    assert resp.status_code == 201


def test_create_category_404_when_parent_missing(client):
    resp = client.post(BASE, json={"parent_id": 424242, "name": "子类"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "上级分类不存在"


def test_create_category_rejects_third_level(client, seeded):
    lunch = find(seeded, "午餐")

    resp = client.post(BASE, json={"parent_id": lunch.id, "name": "冒菜"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "分类最多两级，不能在二级分类下继续加"


def test_create_category_truncates_icon_to_eight_chars(client, seeded):
    """图标超过 8 个字符时截断，避免前端布局被撑破。"""
    body = client.post(BASE, json={"name": "长图标", "icon": "1234567890"}).json()

    assert body["icon"] == "12345678"


# -------------------------------------------------------------------- 改名


def test_update_category_renames_custom_category(client, seeded):
    custom = make_custom(seeded, "交通")

    resp = client.patch(f"{BASE}/{custom.id}", json={"name": "出行", "icon": "🚇"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "出行"
    row = seeded.get(Category, custom.id)
    assert row is not None
    assert (row.name, row.icon) == ("出行", "🚇")


def test_update_category_404_when_missing(client):
    resp = client.patch(f"{BASE}/424242", json={"name": "出行"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "分类不存在"


def test_update_category_rejects_system_category(client, seeded):
    lunch = find(seeded, "午餐")

    resp = client.patch(f"{BASE}/{lunch.id}", json={"name": "午饭"})

    assert resp.status_code == 403
    assert resp.json()["detail"] == "系统自带分类不能修改"


def test_update_category_rejects_duplicate_sibling_name(client, seeded):
    food = find(seeded, "餐饮")
    custom = make_custom(seeded, "晚餐", parent=food)

    resp = client.patch(f"{BASE}/{custom.id}", json={"name": "午餐"})

    assert resp.status_code == 400


def test_update_category_ignores_null_fields(client, seeded):
    custom = make_custom(seeded, "交通", icon="🚌")

    resp = client.patch(f"{BASE}/{custom.id}", json={"name": None, "icon": None})

    assert resp.status_code == 200
    assert resp.json()["name"] == "交通"


# ------------------------------------------------------------ 删除与迁移


def test_delete_category_404_when_missing(client):
    resp = client.delete(f"{BASE}/424242")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "分类不存在"


def test_delete_category_rejects_system_category(client, seeded):
    lunch = find(seeded, "午餐")

    resp = client.delete(f"{BASE}/{lunch.id}")

    assert resp.status_code == 403
    assert resp.json()["detail"] == "系统自带分类不能删除"


def test_delete_level2_category_migrates_expenses_to_fallback(client, seeded):
    food = find(seeded, "餐饮")
    custom = make_custom(seeded, "晚餐", parent=food)
    expense = add_expense(seeded, 1234, custom)
    other = find(seeded, "其他")
    fallback = find(seeded, "未分类")

    resp = client.delete(f"{BASE}/{custom.id}")

    assert resp.status_code == 200
    assert resp.json() == {"migrated": 1}
    seeded.refresh(expense)
    assert (expense.category_l1, expense.category_l2) == (other.id, fallback.id)
    assert seeded.get(Category, custom.id) is None


def test_delete_level1_category_removes_children_and_migrates(client, seeded):
    custom_root = make_custom(seeded, "交通")
    child = make_custom(seeded, "地铁", parent=custom_root)
    expense = add_expense(seeded, 500, child)
    fallback = find(seeded, "未分类")

    resp = client.delete(f"{BASE}/{custom_root.id}")

    assert resp.status_code == 200
    assert resp.json() == {"migrated": 1}
    assert seeded.get(Category, custom_root.id) is None
    assert seeded.get(Category, child.id) is None
    seeded.refresh(expense)
    assert expense.category_l2 == fallback.id


def test_delete_empty_category_reports_zero_migrated(client, seeded):
    custom = make_custom(seeded, "交通")

    resp = client.delete(f"{BASE}/{custom.id}")

    assert resp.status_code == 200
    assert resp.json() == {"migrated": 0}


def test_delete_category_migrates_trashed_expenses_too(client, seeded):
    food = find(seeded, "餐饮")
    custom = make_custom(seeded, "晚餐", parent=food)
    trashed = add_expense(seeded, 100, custom, deleted=True)

    resp = client.delete(f"{BASE}/{custom.id}")

    assert resp.json() == {"migrated": 1}
    seeded.refresh(trashed)
    assert trashed.category_l2 == find(seeded, "未分类").id


# ------------------------------------------------------ 兜底分类缺失 / 异常


def test_delete_category_falls_back_to_any_child_when_uncategorized_missing(client, seeded):
    """「其他」下没有「未分类」时，退而用它的第一个子分类接住账单。"""
    other = find(seeded, "其他")
    uncategorized = find(seeded, "未分类")
    seeded.delete(uncategorized)
    seeded.commit()
    surrogate = make_custom(seeded, "杂项", parent=other, icon="📦")
    food = find(seeded, "餐饮")
    custom = make_custom(seeded, "晚餐", parent=food)
    expense = add_expense(seeded, 800, custom)

    resp = client.delete(f"{BASE}/{custom.id}")

    assert resp.status_code == 200
    assert resp.json() == {"migrated": 1}
    seeded.refresh(expense)
    assert expense.category_l1 == other.id
    assert expense.category_l2 == surrogate.id


def test_delete_category_500_when_fallback_root_missing(client, seeded):
    other = find(seeded, "其他")
    for row in seeded.exec(select(Category).where(Category.parent_id == other.id)).all():
        seeded.delete(row)
    seeded.delete(other)
    seeded.commit()
    food = find(seeded, "餐饮")
    custom = make_custom(seeded, "晚餐", parent=food)

    resp = client.delete(f"{BASE}/{custom.id}")

    assert resp.status_code == 500
    assert resp.json()["detail"] == "缺少「其他」兜底分类，请检查数据"


def test_delete_category_500_when_fallback_has_no_child(client, seeded):
    other = find(seeded, "其他")
    uncategorized = find(seeded, "未分类")
    seeded.delete(uncategorized)
    seeded.commit()
    food = find(seeded, "餐饮")
    custom = make_custom(seeded, "晚餐", parent=food)

    resp = client.delete(f"{BASE}/{custom.id}")

    assert resp.status_code == 500
    assert resp.json()["detail"] == "缺少「其他」下的兜底小类，请检查数据"
    assert other is not None


def test_delete_root_named_uncategorized_is_blocked_by_name(client, seeded):
    """记录现状：拦截用的是「名字叫未分类且是一级分类」，

    而真正的兜底分类其实是「其他 / 未分类」（二级）。用户自己建的一级「未分类」也会被这条挡住。
    """
    impostor = Category(name="未分类", parent_id=None, is_system=False)
    seeded.add(impostor)
    seeded.commit()
    seeded.refresh(impostor)

    resp = client.delete(f"{BASE}/{impostor.id}")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "兜底分类不能删除"
