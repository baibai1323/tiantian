"""统计接口：本月汇总、分类占比、近 N 个月趋势。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import Expense
from ..schemas import CategoryStat, StatsSummary, TrendPoint
from ..services import load_categories, to_expense_out
from ..utils import cents_to_yuan, current_month, is_valid_month, normalize_month, today_str

# 上面几个工具函数都来自 app/utils.py，先认识一下再往下读：
# current_month() 返回 "2026-11" 这样的当前月字符串；
# normalize_month() 把 "2026-1" 补成 "2026-01"；
# is_valid_month() 判断月份格式对不对；
# cents_to_yuan() 把整数「分」转成 "28.00" 这样的两位小数「元」字符串；
# today_str() 返回今天的 "YYYY-MM-DD"，用来查「今天花了多少」。
router = APIRouter(prefix="/api/stats", tags=["stats"])

# 统计接口和记账接口分开放：这里只读不写，做的是「把很多行汇总成几个数」的聚合查询，
# 聚合 = SQL 里的 SUM / COUNT / GROUP BY，由数据库算完再把结果传回来，比在 Python 里累加快得多。


@router.get("/summary", response_model=StatsSummary)
def summary(
    month: str | None = Query(default=None, description="YYYY-MM，默认本月"),
    session: Session = Depends(get_session),
) -> StatsSummary:
    """返回某个月的汇总数据：总额、笔数、今日支出、分类占比和最近几笔。

    做什么：以「月份」为范围做四次查询——总额与笔数、今日支出（仅当前月）、
    按一级/二级分类汇总、最近 5 笔账单，再拼成一个响应对象。
    参数 month：月份字符串 YYYY-MM；不传默认本月，会先补零再校验。
    参数 session：数据库会话，由框架注入。
    返回：StatsSummary，包含总额（分和元两种单位）、笔数、今日支出、分类占比列表和最近账单。
    """
    # 默认查本月：打开首页看到的通常就是当月统计。
    if month is None:
        month = current_month()
    # 补零：数据库里存的是 "2026-01-05" 这种格式，"2026-1" 直接拿去 LIKE 会查不到。
    month = normalize_month(month)
    if not is_valid_month(month):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")

    # 所有按月统计共用的两个条件：没被软删除 + 消费日期落在该月。
    month_conditions = [Expense.deleted_at.is_(None), Expense.spent_on.like(f"{month}-%")]
    # coalesce(sum(...), 0)：这个月一笔账都没有时 SUM 返回 NULL，包一层变成 0，
    # 否则下面 int() 转换会因为 None 报错。
    total_cents = int(
        session.exec(
            select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(*month_conditions)
        ).one()
    )
    # count 是本月账单笔数，和总额用同一组条件，保证两个数字口径一致。
    count = int(
        session.exec(select(func.count()).select_from(Expense).where(*month_conditions)).one()
    )
    # 「今天花了多少」只对当前月有意义；查历史月份时返回 0，避免把今天的支出算进别的月份
    this_month = current_month()
    today_cents = 0
    if month == this_month:
        # 只有查当前月才真的去查今天：条件里用 spent_on == 今天的日期字符串。
        today_cents = int(
            session.exec(
                select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(
                    Expense.deleted_at.is_(None), Expense.spent_on == today_str()
                )
            ).one()
        )

    # 按一级分类分组求和；GROUP BY 会把同一个 category_l1 的多行先合并再 SUM。
    # 排序放在数据库里做，金额大的分类排在前面，前端直接按顺序画占比条。
    by_l1_rows = session.exec(
        select(Expense.category_l1, func.sum(Expense.amount_cents))
        .where(*month_conditions)
        .group_by(Expense.category_l1)
        .order_by(func.sum(Expense.amount_cents).desc())
    ).all()

    # 分类字典先加载好，循环里按 id 取名字，避免每行都查一次数据库。
    # load_categories 返回的是「分类 id -> 分类对象」的字典，键是整数 id。
    # 下面 by_l1 是要放进响应的列表，每一项对应一个一级分类的汇总。
    categories = load_categories(session)
    by_l1: list[CategoryStat] = []
    for category_id, amount in by_l1_rows:
        # 分类被删掉后账单已迁走，理论上不会走到 None 分支；真遇到时用占位名兜底，
        # 保证统计页面不会因为一条脏数据整页报错。
        category = categories.get(int(category_id))
        amount_int = int(amount)
        by_l1.append(
            CategoryStat(
                id=int(category_id),
                name=category.name if category else "未知分类",
                icon=category.icon if category else "❓",
                total_cents=amount_int,
                total_yuan=cents_to_yuan(amount_int),
                # 占比 = 该分类金额 / 本月总额 * 100。先判断 total_cents 不为 0，
                # 否则这个月没花钱时会触发「除以零」错误。
                percent=round(amount_int / total_cents * 100, 1) if total_cents else 0.0,
            )
        )

    # 二级分类同样分组求和，前端用它画「餐饮」展开后的细项。
    by_l2_rows = session.exec(
        select(Expense.category_l2, func.sum(Expense.amount_cents))
        .where(*month_conditions)
        .group_by(Expense.category_l2)
        .order_by(func.sum(Expense.amount_cents).desc())
    ).all()
    by_l2: list[CategoryStat] = []
    for category_id, amount in by_l2_rows:
        # 逻辑和上面一级分类完全一致：取名字、算占比、算元。
        category = categories.get(int(category_id))
        amount_int = int(amount)
        by_l2.append(
            CategoryStat(
                id=int(category_id),
                name=category.name if category else "未知分类",
                icon=category.icon if category else "❓",
                total_cents=amount_int,
                total_yuan=cents_to_yuan(amount_int),
                percent=round(amount_int / total_cents * 100, 1) if total_cents else 0.0,
            )
        )

    # 「最近 5 笔」不限定月份，这样月初也能看到上个月的记录，页面不会一片空白。
    recent_rows = session.exec(
        select(Expense)
        .where(Expense.deleted_at.is_(None))
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
        .limit(5)
    ).all()

    # 组装最终响应：分（整数）和元（两位小数字符串）都返回，前端不用自己换算。
    # 这里用关键字参数逐个赋值，字段顺序和 schemas.py 里的 StatsSummary 保持一致，
    # 以后加字段时也容易看出哪里漏了。
    return StatsSummary(
        month=month,
        total_cents=total_cents,
        total_yuan=cents_to_yuan(total_cents),
        today_cents=today_cents,
        today_yuan=cents_to_yuan(today_cents),
        count=count,
        by_l1=by_l1,
        by_l2=by_l2,
        recent=[to_expense_out(row, categories) for row in recent_rows],
    )


@router.get("/trend", response_model=list[TrendPoint])
def trend(
    months: int = Query(default=6, ge=1, le=24),
    session: Session = Depends(get_session),
) -> list[TrendPoint]:
    """返回最近 N 个月的支出趋势（用于画折线图）。

    做什么：从当前月开始往前倒推 N 个月，生成一串 YYYY-MM 的月份键，
    再按月份分组求和，最后把没有数据的月份补成 0。
    参数 months：要看最近几个月，默认 6，范围 1~24（限制上限是为了别一次画太多点）。
    参数 session：数据库会话，由框架注入。
    返回：TrendPoint 列表，按时间从早到晚排列；每个点包含月份、金额（分）和金额（元）。
    """
    # 以「今天」为基准往前推，而不是以数据里最大的月份为准——没有记账的月份也该显示 0。
    today = date.today()
    keys: list[str] = []
    year, month = today.year, today.month
    for _ in range(months):
        # {year:04d} 表示年份至少 4 位、不足补零；{month:02d} 表示月份补足 2 位。
        # 月份补零很关键：数据库里存的是 "2026-01"，写成 "2026-1" 就对不上了。
        keys.append(f"{year:04d}-{month:02d}")
        # 往前推一个月；推到 0 就回退到上一年的 12 月。
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    # 上面是从晚到早生成的，reverse 之后变成从早到晚，折线图才是从左往右画。
    keys.reverse()

    # 最早那个月的 1 号。用 >= 比较字符串即可，因为日期格式固定是 YYYY-MM-DD，
    # 字典序和时间先后顺序一致。
    # 只查这个起点之后的数据，等于让数据库帮忙挡掉更早的账单，少传很多行回来。
    start = keys[0] + "-01"
    # substr(spent_on, 1, 7) 取日期字符串的前 7 位，也就是 "YYYY-MM" 作为分组键；
    # 这里不用 LIKE 是因为要按月份分组，必须有一个可 GROUP BY 的表达式。
    rows = session.exec(
        select(func.substr(Expense.spent_on, 1, 7), func.sum(Expense.amount_cents))
        .where(Expense.deleted_at.is_(None), Expense.spent_on >= start)
        .group_by(func.substr(Expense.spent_on, 1, 7))
    ).all()
    # 转成「月份 -> 金额（分）」的字典，方便下面按 keys 逐一取值。
    # 数据库只返回「有账单的月份」，没出现的月份要在后面补 0。
    totals = {str(key): int(amount) for key, amount in rows}

    # 遍历自己生成的月份键而不是数据库结果，这样中间没记账的月份会得到默认值 0，
    # 折线图不会因为缺一个月而错位。
    # totals.get(key, 0) 的第二个参数就是「取不到时用 0」，省掉一次 if 判断。
    return [
        TrendPoint(month=key, total_cents=totals.get(key, 0), total_yuan=cents_to_yuan(totals.get(key, 0)))
        for key in keys
    ]
