"""接口的请求 / 响应数据结构（Pydantic）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

# 单笔金额上限 9999999.99 元（约一千万元）：既挡住误输入多打几个 0，
# 也保证“元→分”之后仍能放进 32 位整数（9.99 亿分 < 21 亿分）。
MAX_AMOUNT = Decimal("9999999.99")


def _normalize_date(value: str) -> str:
    """校验并统一成 YYYY-MM-DD。

    strptime 会接受 "2026-1-5" 这种没补零的写法，但数据库里存进去后
    按月前缀查询（LIKE '2026-01-%'）就再也查不到这笔账，所以这里必须
    严格按补零格式回写。
    """
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("日期格式应为 YYYY-MM-DD") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError("日期格式应为 YYYY-MM-DD（月和日要补零）")
    return value


class CategoryNode(BaseModel):
    """分类树的一个节点，给前端渲染下拉框、树形列表用。

    children 是递归嵌套的：一级分类的 children 是它的二级分类，
    二级分类的 children 为空列表；默认空列表是为了前端不用先判 None。
    """
    id: int
    name: str
    icon: str = ""
    children: list["CategoryNode"] = Field(default_factory=list)


class CategoryCreate(BaseModel):
    """新建分类的请求体。

    parent_id 为空表示建一级分类；不为空时要填所属一级分类的 id。
    """
    parent_id: int | None = None
    name: str
    icon: str = ""


class CategoryUpdate(BaseModel):
    """修改分类的请求体。

    两个字段都可选：只传要改的字段，没传的（None）保持原值不变。
    """
    name: str | None = None
    icon: str | None = None


class CategoryManageNode(BaseModel):
    """分类管理页用的节点，比 CategoryNode 多出删除/停用时要参考的信息。

    expense_count 是该分类（含子分类）下还挂着的账目数，用来提示用户：
    删除前要先把这些账目迁移走。
    """
    id: int
    name: str
    icon: str
    is_system: bool
    expense_count: int = 0
    children: list["CategoryManageNode"] = Field(default_factory=list)


class CategoryDeleteResult(BaseModel):
    """删除分类的结果。

    migrated 是被迁移到“未分类”的账目条数，并非删除的账目数——
    账目本身不会被删掉，只是换了分类。
    """
    migrated: int = 0


class ExpenseIn(BaseModel):
    """记一笔账的请求体，也就是前端提交的原始输入。

    金额用 Decimal 接收而不是 float：Decimal 按十进制精确表示，
    能把 "0.1" 原样保留，之后转“分”时才不会出现 0.1 × 100 = 10.000000000000002。
    """
    amount: Decimal
    category_l2: int
    spent_on: str
    note: str = ""

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, value: Decimal) -> Decimal:
        """校验单笔金额的边界。

        参数 value：用户输入的金额，单位是元，类型为 Decimal。
        返回：原样返回 value；不合法时抛 ValueError，FastAPI 会把它转成 422 响应。
        """
        if value <= 0:
            raise ValueError("金额必须大于 0")
        # as_tuple().exponent 是小数位数：0.123 的 exponent 为 -3，说明超过两位小数。
        if value.as_tuple().exponent < -2:
            raise ValueError("金额最多两位小数")
        if value > MAX_AMOUNT:
            raise ValueError("金额过大")
        return value

    @field_validator("spent_on")
    @classmethod
    def _check_date(cls, value: str) -> str:
        """校验并规范化记账日期。

        参数 value：形如 "2026-11-20" 的日期文本。
        返回：补零后的同一字符串；格式不对时抛 ValueError。
        """
        return _normalize_date(value)

    @field_validator("note")
    @classmethod
    def _trim_note(cls, value: str) -> str:
        """清洗备注：去掉首尾空白并截断到 200 个字符，防止超长文本撑坏界面。

        参数 value：用户填的原始备注。
        返回：清洗后的备注字符串。
        """
        return value.strip()[:200]


class ExpensePatch(BaseModel):
    """修改一笔账的请求体，字段全部可选（PATCH 语义：只改传了的字段）。

    None 在这里表示“这次不改这个字段”，而不是“把它清空”；
    想清空备注请显式传空字符串 ""。
    """
    amount: Decimal | None = None
    category_l2: int | None = None
    spent_on: str | None = None
    note: str | None = None

    @field_validator("amount")
    @classmethod
    def _check_amount(cls, value: Decimal | None) -> Decimal | None:
        """PATCH 版本的金额校验，规则与 ExpenseIn 完全一致。

        参数 value：新金额；None 表示这次不改金额，直接放行。
        返回：原金额或 None。
        """
        if value is None:
            return None
        if value <= 0:
            raise ValueError("金额必须大于 0")
        if value.as_tuple().exponent < -2:
            raise ValueError("金额最多两位小数")
        if value > MAX_AMOUNT:
            raise ValueError("金额过大")
        return value

    @field_validator("spent_on")
    @classmethod
    def _check_date(cls, value: str | None) -> str | None:
        """PATCH 版本的日期校验。

        参数 value：新日期；None 表示这次不改日期。
        返回：规范化后的日期字符串或 None。
        """
        if value is None:
            return None
        return _normalize_date(value)

    @field_validator("note")
    @classmethod
    def _trim_note(cls, value: str | None) -> str | None:
        """PATCH 版本的备注清洗。

        参数 value：新备注；None 表示这次不改备注。
        返回：清洗后的备注字符串或 None。
        """
        return value.strip()[:200] if value is not None else None


class ExpenseOut(BaseModel):
    """返回给前端的一笔账，分类 id 已经被翻译成名字和图标。

    金额同时给 amount_cents（分，整数）和 amount_yuan（元，字符串）：
    前者方便程序继续计算，后者可以直接显示，不用前端自己做除法。
    """
    id: int
    # 金额按“分”存成整数：数据库里没有精度误差，展示时再换成元。
    amount_cents: int
    amount_yuan: str
    category_l1: int
    category_l1_name: str
    category_l1_icon: str
    category_l2: int
    category_l2_name: str
    spent_on: str
    note: str
    created_at: str
    deleted_at: str | None = None


class ExpenseListOut(BaseModel):
    """分页后的账目列表。

    total 是满足筛选条件的总条数（用来算总页数），items 只是当前这一页；
    sum_cents / sum_yuan 是这一页金额的合计。
    """
    items: list[ExpenseOut]
    total: int
    sum_cents: int
    sum_yuan: str


class CategoryStat(BaseModel):
    """按分类汇总的一行统计。

    total_cents 是该分类的合计金额，单位是分；percent 是它占当月总支出的百分比，
    取值 0~100（例如 12.5 表示 12.5%），不是 0~1 的小数。
    """
    id: int
    name: str
    icon: str
    total_cents: int
    total_yuan: str
    percent: float


class StatsSummary(BaseModel):
    """月度统计总览，首页的汇总卡片和分类占比图都用它。

    today_cents 只统计“今天”的支出，其余金额字段统计的是 month 这整个月；
    by_l1 是一级分类汇总，by_l2 是二级分类汇总（默认空列表，前端不传就没有）。
    """
    month: str
    total_cents: int
    total_yuan: str
    today_cents: int
    today_yuan: str
    count: int
    by_l1: list[CategoryStat]
    by_l2: list[CategoryStat] = Field(default_factory=list)
    recent: list[ExpenseOut]


class TrendPoint(BaseModel):
    """趋势图上的一个点：一个月份 + 该月支出合计。

    month 形如 "2026-11"，按它排序就是时间顺序。
    """
    month: str
    total_cents: int
    total_yuan: str


class ImportRequest(BaseModel):
    """导入请求：content 是用户上传的 CSV 文件全文，不是文件路径。"""

    content: str


class ImportIssue(BaseModel):
    """导入时的一条问题记录。

    line 是 CSV 里的行号（从 1 开始，含表头），reason 是给用户看的中文原因。
    """
    line: int
    reason: str


class ImportResult(BaseModel):
    """导入结果汇总。

    imported 是成功写入的条数，duplicates 是因重复被跳过的条数，
    invalid 是格式不合法被跳过的条数；
    fallback 是分类没识别出来、被放进“未分类”兜底分类的条数。
    errors / warnings 分别放“这一行没导入”和“导入了但需要留意”的明细。
    """
    imported: int
    duplicates: int
    invalid: int
    fallback: int
    errors: list[ImportIssue] = Field(default_factory=list)
    warnings: list[ImportIssue] = Field(default_factory=list)
