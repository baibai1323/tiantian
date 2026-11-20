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

# APIRouter（路由器）负责把「URL + 请求方法」映射到下面的函数；
# 这里统一加了 /api/categories 前缀，所以下面 @router.get("") 实际就是 GET /api/categories。
# tags 只是接口文档（/docs 页面）里的分组名，方便按模块折叠，不影响接口行为。
router = APIRouter(prefix="/api/categories", tags=["categories"])

# 分类名长度上限：按「字符」算而不是按字节，16 个字足够放「交通出行」「人情往来」
# 这类词；再长会把手机端两列的分类格子撑破。改名和新建都会用到这个上限。
MAX_NAME_LEN = 16


def _clean_name(raw: str) -> str:
    """校验并整理用户填写的分类名。

    做什么：先去掉首尾空白，再依次检查三条业务规则——不能为空、不超过
    MAX_NAME_LEN 个字、不能含换行和制表符；任一条不满足就抛 HTTPException
    （HTTP 异常，FastAPI 会把它转换成对应的 400 错误响应返回给前端）。
    参数 raw：接口收到的原始名称；调用方可能传 None，所以下面用 `raw or ""` 兜底。
    返回：清理干净、可以直接写进数据库的名称字符串。
    """
    # `raw or ""` 是个小技巧：None 直接调用 .strip() 会报错，先转成空串再处理。
    name = (raw or "").strip()
    # 只有空格的名字等于没填，这里必须拦住，否则列表里会出现一个看不见的分类。
    if not name:
        raise HTTPException(status_code=400, detail="分类名不能为空")
    # 400 表示「客户端请求有问题」；detail 里的文案会原样显示给用户当提示。
    if len(name) > MAX_NAME_LEN:
        raise HTTPException(status_code=400, detail=f"分类名最多 {MAX_NAME_LEN} 个字")
    # 换行 / 制表符会打乱列表排版，导出 CSV 时还会把一行拆成两行，属于脏数据。
    if any(ch in name for ch in "\r\n\t"):
        raise HTTPException(status_code=400, detail="分类名里不能有换行或制表符")
    return name


def _ensure_unique(
    session: Session, parent_id: int | None, name: str, exclude_id: int | None = None
) -> None:
    """检查同一级下是否已经有同名分类。

    做什么：在「同一个父分类」范围内按名字查重。同名分类允许存在于不同的
    一级分类下面（例如「交通 / 其他」和「餐饮 / 其他」），所以查询条件里
    必须带上 parent_id，不能只按名字查。
    参数 session：数据库会话，可以理解为「一次和数据库对话的上下文」。
    参数 parent_id：父分类 id；传 None 表示要查的是一级分类这一层。
    参数 name：要检查的分类名，调用前已经过 _clean_name 清洗。
    参数 exclude_id：改名时要把自己排除掉，否则「自己的名字」也会被算成重名。
    返回：没有返回值；一旦重名就抛 400 错误（比返回布尔值少一层 if，调用方更省事）。
    """
    stmt = select(Category).where(Category.name == name)
    # 一级分类在数据库里的 parent_id 是 NULL。SQL 中 NULL 不能用 = 比较，
    # 必须写 IS NULL（SQLAlchemy 里对应 is_(None)），否则永远查不到记录。
    if parent_id is None:
        stmt = stmt.where(Category.parent_id.is_(None))
    else:
        stmt = stmt.where(Category.parent_id == parent_id)
    # 改名的场景：把「自己」从候选里排除，不然改成原名也会误报重名。
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    # .first() 只取第一条：只要存在同名记录，这次操作就已经不合法了。
    if session.exec(stmt).first() is not None:
        raise HTTPException(status_code=400, detail=f"同一级下已经有「{name}」了")


def _fallback_pair(session: Session) -> tuple[Category, Category]:
    """删除分类时，账单统一迁到「其他 / 未分类」。"""
    # 「兜底」在这里的含义是：用户删掉的分类里可能还挂着账单，账单不能跟着
    # 分类一起消失，必须先挪到一个保证存在的地方，也就是「其他 / 未分类」。
    # 第一段查询找一级分类「其他」：parent_id 为 NULL 说明它自己就是最顶层。
    root = session.exec(
        select(Category).where(Category.parent_id.is_(None), Category.name == "其他")
    ).first()
    if root is None:
        raise HTTPException(status_code=500, detail="缺少「其他」兜底分类，请检查数据")
    # 500 表示服务端数据本身有问题（种子数据缺失），不是用户操作失败。
    # 第二段查询优先找标准的「未分类」小类；找不到时用下面的排序取第一条子类兜底，
    # 这样即使用户把「未分类」改成别的名字，迁移也不会失败。
    child = session.exec(
        select(Category).where(Category.parent_id == root.id, Category.name == "未分类")
    ).first()
    if child is None:
        child = session.exec(
            select(Category)
            .where(Category.parent_id == root.id)
            .order_by(Category.sort_order, Category.id)
        ).first()
    # sort_order 是用户拖动排序时写入的序号，越小越靠前；序号相同再按 id 排。
    if child is None:
        raise HTTPException(status_code=500, detail="缺少「其他」下的兜底小类，请检查数据")
    # 返回值是元组解包用的两个对象：调用方会写成 `l1, l2 = _fallback_pair(session)`。
    return root, child


@router.get("", response_model=list[CategoryNode])
def list_categories(session: Session = Depends(get_session)) -> list[CategoryNode]:
    """返回给「记一笔」页面用的两级分类树。

    做什么：取出所有启用中的分类，按一级/二级的父子关系拼成一棵树，
    一级分类的 children 里放它下面的二级分类。
    参数 session：数据库会话，由 Depends(get_session) 注入——Depends 是 FastAPI 的
    依赖注入机制，表示「这个参数不用前端传，框架帮你把会话准备好」。
    返回：一级分类节点组成的列表，每个节点通过 children 挂着二级分类；没有数据时返回空列表。
    """
    # is_active 是分类的启用开关，关掉的分类不出现在记账页；这里要显式写 == True，
    # 因为 SQLAlchemy 不会把 Python 的真值判断翻译成 SQL 的 WHERE 条件。
    rows = session.exec(
        select(Category)
        .where(Category.is_active == True)  # noqa: E712 - SQLAlchemy 需要显式比较
        .order_by(Category.sort_order, Category.id)
    ).all()

    # 先把所有行做成「id -> 节点」的字典，后面拼父子关系时能按 id 直接取到节点。
    nodes: dict[int, CategoryNode] = {}
    roots: list[CategoryNode] = []
    for row in rows:
        # `row.id or 0`：新建但还没提交的记录 id 可能是 None，这里退化成 0 防止类型报错。
        node = CategoryNode(id=row.id or 0, name=row.name, icon=row.icon)
        nodes[row.id] = node  # type: ignore[index]
        # parent_id 为空说明是一级分类，直接放进最终要返回的列表。
        if row.parent_id is None:
            roots.append(node)

    # 第二遍遍历才挂子节点：必须等所有节点都建好，否则「子分类先于父分类出现」时会找不到爸爸。
    for row in rows:
        if row.parent_id is not None and row.parent_id in nodes:
            # children 是列表，append 进去的顺序就是查询时 sort_order 决定的顺序。
            nodes[row.parent_id].children.append(nodes[row.id])  # type: ignore[index]

    return roots


@router.get("/manage", response_model=list[CategoryManageNode])
def manage_categories(session: Session = Depends(get_session)) -> list[CategoryManageNode]:
    """返回「分类管理」页面用的分类树，额外带上每类下的账单笔数。

    做什么：先查全部分类（包括停用的，管理员要能看到），再统计每个二级分类
    下还没被软删除的账单数量，最后把子分类的笔数累加到父分类上。
    参数 session：数据库会话，由框架注入。
    返回：一级分类节点列表；每个节点带 is_system（是否系统自带，系统分类禁止改删）
    和 expense_count（该分类及其子分类下的账单总数）。
    """
    # 这里不按 is_active 过滤：管理页需要展示全部分类，停用的也要能看见。
    rows = session.exec(select(Category).order_by(Category.sort_order, Category.id)).all()
    # 一次分组查询就拿到「二级分类 id -> 笔数」，避免在循环里对每个分类各查一次数据库
    # （那就是典型的 N+1 查询，分类一多会明显变慢）。
    # deleted_at 为空 = 没被软删除，回收站里的账单不该算进统计。
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
        # 统计结果里可能没有这个分类（一笔账都没有），get 的默认值 0 就是兜底。
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

    # 和 list_categories 一样，等所有节点建好后再挂 children，避免顺序问题。
    for row in rows:
        if row.parent_id is not None and row.parent_id in nodes:
            nodes[row.parent_id].children.append(nodes[row.id])  # type: ignore[index]

    # 父分类自己的笔数只统计「直接挂在父分类下」的账单（正常为 0），
    # 所以要把每个子分类的笔数加总上去，管理页才能显示整个大类共记了多少笔。
    for root in roots:
        root.expense_count += sum(child.expense_count for child in root.children)

    return roots


@router.post("", response_model=CategoryNode, status_code=201)
def create_category(
    payload: CategoryCreate, session: Session = Depends(get_session)
) -> CategoryNode:
    """新建一个自定义分类（一级或二级）。

    做什么：先校验名字，再确认上级分类存在且没有超过两级，接着查重，
    最后从同级最大排序号加 1 放到末尾并写库。
    参数 payload：前端提交的 JSON，包含 parent_id（不传表示建一级分类）、name、icon。
    参数 session：数据库会话，由框架注入。
    返回：新建成功的分类节点（只带 id / name / icon），状态码 201 表示「已创建」。
    """
    # 名字统一走 _clean_name，保证长度和字符规则与改名接口一致。
    name = _clean_name(payload.name)
    parent_id = payload.parent_id

    # parent_id 有值才需要检查上级；不传就是建一级分类，跳过这段。
    if parent_id is not None:
        parent = session.get(Category, parent_id)
        # 404 = 找不到资源；前端可能拿了一个已经被删掉的分类 id 来建子类。
        if parent is None:
            raise HTTPException(status_code=404, detail="上级分类不存在")
        # 业务规则：分类最多两级。父分类自己还有 parent_id，说明它是二级，
        # 再往下加就成三级了，直接拒绝。
        if parent.parent_id is not None:
            raise HTTPException(status_code=400, detail="分类最多两级，不能在二级分类下继续加")
        # 用数据库里的真实 id 覆盖入参，避免类型上的 Optional 继续往下传。
        parent_id = parent.id

    # 同一级下不能重名，否则前端按名字回显时会分不清是哪一个。
    _ensure_unique(session, parent_id, name)

    # 取同级当前最大的排序号：新分类排到最后，用户之后可以拖动调整。
    # 这里用条件表达式区分「一级（parent_id 为 NULL）」和「某个父分类下」两种情况。
    max_order = session.exec(
        select(func.max(Category.sort_order)).where(
            Category.parent_id.is_(None) if parent_id is None else Category.parent_id == parent_id
        )
    ).one()
    # `int(max_order or 0) + 1`：该层还没有任何分类时 max 返回 NULL，用 0 兜底；
    # 得到的排序号从 1 开始，0 留给种子数据或特殊情况。
    category = Category(
        parent_id=parent_id,
        name=name,
        icon=(payload.icon or "").strip()[:8],
        sort_order=int(max_order or 0) + 1,
        is_active=True,
        is_system=False,
        created_at=iso_now(),
    )
    # 图标字段在库里是短字符串，[:8] 截断防止前端塞进一整段文字把界面撑坏。
    # 标记为非系统分类：用户新建的都属于自定义分类，之后允许改名和删除。
    session.add(category)
    # commit 才会真正写进数据库；refresh 把数据库生成的 id / 默认值读回对象，
    # 否则下面返回的 category.id 还是 None。
    session.commit()
    session.refresh(category)
    return CategoryNode(id=category.id or 0, name=category.name, icon=category.icon)


@router.patch("/{category_id}", response_model=CategoryNode)
def update_category(
    category_id: int, payload: CategoryUpdate, session: Session = Depends(get_session)
) -> CategoryNode:
    """修改自定义分类的名字或图标。

    做什么：先确认分类存在、且不是系统自带的，然后只更新前端真正传了的字段
    （PATCH 语义：没传的字段保持原样），改名时还要重新查重。
    参数 category_id：要修改的分类 id，来自 URL 路径 /{category_id}。
    参数 payload：可能只含 name、只含 icon，或两者都有；字段为 None 表示「不改」。
    参数 session：数据库会话，由框架注入。
    返回：更新后的分类节点（id / name / icon）。
    """
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    # 系统自带分类（如「餐饮」「其他 / 未分类」）是种子数据，代码和统计都依赖它们，
    # 允许改名会让兜底逻辑找不到「其他」，所以这里直接拒绝（403 = 没有权限操作）。
    if category.is_system:
        raise HTTPException(status_code=403, detail="系统自带分类不能修改")

    # 只有显式传了 name 才处理；传 null 或干脆不传都表示「这次不改名字」。
    if payload.name is not None:
        name = _clean_name(payload.name)
        # 查重时把「自己」排除（exclude_id 传的就是当前分类 id），否则改成原名会提示「已存在」。
        _ensure_unique(session, category.parent_id, name, exclude_id=category_id)
        category.name = name
    # 图标允许传空串（表示清空图标），所以这里判断的是「有没有传」而不是「真不真」。
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
    """删除一个自定义分类，并把它名下的账单迁移到「其他 / 未分类」。

    做什么：拒绝删除系统分类和兜底分类；算出要一起处理的子分类 id；
    把这些分类下的账单改挂到兜底分类；删掉子分类和分类本身；
    整个过程在一个事务里完成，最后返回迁移了多少笔账单。
    参数 category_id：要删除的分类 id，来自 URL。
    参数 session：数据库会话，由框架注入。
    返回：CategoryDeleteResult，其中 migrated 是本次被改挂到兜底分类的账单笔数。
    """
    category = session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="分类不存在")
    # 系统分类是种子数据，删掉会让导入、迁移的兜底逻辑失效，直接 403。
    if category.is_system:
        raise HTTPException(status_code=403, detail="系统自带分类不能删除")
    # 双重保险：「未分类」是删除别人时的落脚点，如果连它都被删了，下一次删除就没有兜底了。
    # 判断 parent_id is None 是为了只拦一级的「未分类」，二级同名分类不受影响。
    if category.name == "未分类" and category.parent_id is None:
        raise HTTPException(status_code=400, detail="兜底分类不能删除")

    # 要处理的范围：删一级分类时连它下面的所有二级分类一起删，所以收集子分类 id；
    # 删二级分类时范围就是它自己。账单挂在 category_l2 上，用这个列表去筛选。
    if category.parent_id is None:
        child_ids = [
            row.id
            for row in session.exec(
                select(Category).where(Category.parent_id == category_id)
            ).all()
        ]
    else:
        child_ids = [category_id]

    # 先拿到兜底分类（一级「其他」+ 二级「未分类」），后面给账单改挂用。
    fallback_l1, fallback_l2 = _fallback_pair(session)
    migrated = 0
    if child_ids:
        # 一次性查出这些分类下的所有账单，包括回收站里的（没加 deleted_at 过滤），
        # 因为它们同样不能失去所属分类。
        expenses = session.exec(
            select(Expense).where(Expense.category_l2.in_(child_ids))
        ).all()
        for expense in expenses:
            # 一级和二级必须同时改，否则统计按一级分类汇总时会对不上号。
            expense.category_l1 = fallback_l1.id
            expense.category_l2 = fallback_l2.id
            session.add(expense)
        migrated = len(expenses)
        # flush 把上面的修改先发给数据库（还没提交），保证下面删分类时外键关系不会打架。
        session.flush()

        # 删一级分类时，它下面的二级分类也要一起删；否则这些二级分类会变成
        # 挂在一个不存在的父节点下的「孤儿数据」。
        if category.parent_id is None:
            session.exec(delete(Category).where(Category.parent_id == category_id))
            session.flush()

    # 最后删分类自己。delete 只是标记删除，commit 之后才真正生效。
    session.delete(category)
    session.commit()
    return CategoryDeleteResult(migrated=migrated)
