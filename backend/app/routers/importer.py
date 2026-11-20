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

# 单次导入的行数上限。这既是性能保护（几万行逐条解析会很慢），
# 也防止有人误把超大文件拖进来把内存吃满；超过就直接报错，不做截断。
MAX_ROWS = 20000
# 错误 / 警告明细也各自最多回传 50 条：前端只需要给用户看前几条示例，
# 几千条错误一次性塞进响应既卡界面也没人看。50 这个数字只影响提示条数，不影响导入结果统计。


def _normalize_header(value: str | None) -> str:
    """把表头文字标准化，方便后面做「名字对名字」的比较。

    做什么：把全角括号（）换成半角 ()，去掉所有空格和首尾空白。
    Excel 里手打的表头经常带全角括号或多余空格，不统一就匹配不上。
    参数 value：原始表头文字，可能是 None（空列）。
    返回：标准化后的文字；传入 None 时返回空串。
    """
    # 替换顺序不影响结果；连续调用 replace 比写正则更容易看懂。
    return (value or "").replace("（", "(").replace("）", ")").replace(" ", "").strip()


def _pick_columns(fieldnames: list[str]) -> dict[str, str]:
    """把实际表头映射到标准字段，容忍全角括号和少量别名。"""
    # 先建一张「标准化表头 -> 原始表头」的字典。后面按别名查表时，
    # 拿到的是原始表头，因为读每一行数据要用原始表头去做 key。
    normalized = {_normalize_header(name): name for name in fieldnames if name}
    # 每个标准字段允许的别名。用户可能用别的记账软件导出的表再导入，
    # 列名不完全一样（「金额」和「支出」），这里尽量兼容。
    aliases = {
        "date": ("日期", "时间", "日 期"),
        "l1": ("一级分类", "大类"),
        "l2": ("二级分类", "小类"),
        "amount": ("金额(元)", "金额", "支出(元)", "支出"),
        "note": ("备注", "说明"),
    }
    found: dict[str, str] = {}
    # 逐个标准字段去别名列表里找，找到第一个就停（所以别名列表的先后顺序就是优先级）。
    for key, names in aliases.items():
        for name in names:
            if _normalize_header(name) in normalized:
                found[key] = normalized[_normalize_header(name)]
                break
    # 日期、一级分类、二级分类、金额缺一不可；备注可以没有，所以不在必填列表里。
    # missing 里存的是给人看的中文列名，用来拼错误提示。
    missing = [label for key, label in (("date", "日期"), ("l1", "一级分类"), ("l2", "二级分类"), ("amount", "金额(元)")) if key not in found]
    if missing:
        raise HTTPException(status_code=400, detail="CSV 缺少列：" + "、".join(missing))
    # 返回的字典形如 {"date": "日期", "amount": "金额(元)", ...}，
    # 调用方拿它当「标准字段 -> 实际表头」的对照表。
    return found


def _parse_date(raw: str) -> str | None:
    """把各种写法的日期统一成 YYYY-MM-DD。

    做什么：依次尝试「横杠 / 斜杠 / 点」三种常见分隔符，谁先解析成功就用谁，
    这样其它软件导出的表也能认。
    参数 raw：CSV 单元格里的原始文本，可能为空、可能带多余空格。
    返回：形如 "2026-11-16" 的字符串；格式不认识时返回 None，由调用方记一条错误。
    """
    text = (raw or "").strip()
    # strptime 负责按格式解析；解析失败会抛 ValueError，这里直接 continue 试下一种格式。
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            # 解析成功后再 strftime 回写成统一格式，等于顺手完成了「补零」：
            # "2026/1/5" 会变成 "2026-01-05"，和数据库里的格式一致。
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # 三种都失败，说明这一格不是可识别的日期。
    return None


def _parse_cents(raw: str) -> int | None:
    """把金额文本解析成整数「分」，并校验上下限。

    做什么：去掉千分位逗号和货币符号，用 Decimal 精确解析，然后检查
    「大于 0」「不超过 9999999.99」「最多两位小数」三条规则。
    参数 raw：CSV 单元格里的原始文本，例如 "1,280.50" 或 "¥28"。
    返回：整数分（如 2800）；不合法时返回 None，由调用方记一条错误。
    """
    # 先清掉常见干扰字符：千分位逗号、人民币符号（半角和全角两种）。
    text = (raw or "").strip().replace(",", "").replace("¥", "").replace("￥", "")
    # 空单元格直接判失败，不用再往下解析。
    if not text:
        return None
    try:
        # 用 Decimal 而不是 float：float 存 0.1 会变成 0.1000000000000000055…，
        # 金额必须精确到分，所以这里选十进制类型。
        value = Decimal(text)
    except InvalidOperation:
        # 文本不是数字（如 "abc"）时 Decimal 抛 InvalidOperation，转成 None 交给调用方。
        return None
    # 三条边界一次判断完：必须为正数（0 元账单没有意义）、
    # 不能超过 9999999.99（和 schemas.py 里的 MAX_AMOUNT 保持一致，防止脏数据绕过接口校验）、
    # exponent 小于 -2 表示小数超过两位（如 1.234），分已经是最小单位，存不下。
    if value <= 0 or value > Decimal("9999999.99") or value.as_tuple().exponent < -2:
        return None
    # 走到这里说明金额合法，换算成整数分。
    return yuan_to_cents(value)


@router.post("/csv", response_model=ImportResult)
def import_csv(payload: ImportRequest, session: Session = Depends(get_session)) -> ImportResult:
    """导入 CSV 账单，返回「成功多少、重复多少、失败多少」的统计。

    做什么：按顺序做四件事——读表头并映射列名、准备分类对照表和兜底分类、
    逐行解析并去重、最后一次性写库；单行出错只记录不中断，整批成功才提交。
    参数 payload：请求体，content 字段是浏览器读出来的 CSV 全文（不是文件上传）。
    参数 session：数据库会话，由框架注入。
    返回：ImportResult，含 imported / duplicates / invalid / fallback 四个计数，
    以及最多 50 条 errors（解析失败的行）和 warnings（分类落到兜底的行）。
    """
    # 有些导出工具会在文件最前面加 BOM（一个看不见的字符），不去掉的话
    # 第一个表头会变成 "\ufeff日期"，怎么也对不上别名表。lstrip 只从左边删。
    content = payload.content.lstrip("\ufeff")
    # 空文件直接拒绝，避免后面读到空表头再报一个更难懂的错。
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件是空的")

    # DictReader 会把每一行变成「表头 -> 单元格」的字典，按列名取值比按序号更稳。
    # StringIO 把字符串包装成「像文件一样可读」的对象，csv 模块只认这种接口。
    reader = csv.DictReader(io.StringIO(content))
    # fieldnames 是表头列表；完全空白的文件读出来是 None。
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="没有读到表头，请确认是天天记账导出的 CSV")
    # columns 把标准字段映射到实际表头，后面每行都用 columns["date"] 这样的方式取值。
    columns = _pick_columns(list(reader.fieldnames))

    # 分类表是导入的关键：CSV 里写的是分类名字，数据库里要存分类 id。
    # 先一次性读出全部分类，再建两张「名字 -> id」的查找表。
    nodes = load_categories(session)
    # 一级分类按名字查 id；parent_id 为空表示一级。
    l1_by_name = {node.name: node.id for node in nodes.values() if node.parent_id is None}
    # 二级分类可能重名（不同一级下面都有「其他」），所以键要用「父 id + 名字」的组合。
    l2_by_name: dict[tuple[int, str], int] = {}
    for node in nodes.values():
        # 父分类也要存在于 nodes 里，否则这个二级分类是孤儿数据，跳过更安全。
        if node.parent_id is not None and node.parent_id in nodes:
            l2_by_name[(node.parent_id, node.name)] = node.id

    # 兜底分类「其他 / 未分类」：CSV 里的分类名对不上时，账单往这里放，保证不丢数据。
    other_l1 = l1_by_name.get("其他")
    other_l2: int | None = None
    if other_l1 is not None:
        # 依次尝试几个常见名字，谁先命中就用谁；「手续费」是早期版本留下的默认小类。
        for name in ("未分类", "手续费", "其他"):
            other_l2 = l2_by_name.get((other_l1, name))
            if other_l2 is not None:
                break
        # 三个名字都没有（用户改过名）时，退而求其次：拿「其他」下的任意一个子分类。
        # next(生成器, None) 的意思是「取第一个，没有就返回 None」。
        if other_l2 is None:
            other_l2 = next(
                (child for (parent, _name), child in l2_by_name.items() if parent == other_l1),
                None,
            )
    # 兜底分类都不存在说明种子数据被破坏了，这时导入会丢账单，宁可整批失败。
    if other_l1 is None or other_l2 is None:
        raise HTTPException(status_code=500, detail="分类数据不完整，缺少「其他」兜底分类")

    # 「去重键」= 日期 + 金额 + 一级分类 + 二级分类 + 备注，五项完全相同就认为是同一笔。
    # 这里故意不把数据库 id 算进去：同一个文件导两次，第二次应该全部判为重复。
    # 一次读出全部已有账单，在内存里做集合比较，比每行都查一次数据库快得多。
    existing = {
        (row.spent_on, row.amount_cents, row.category_l1, row.category_l2, row.note)
        for row in session.exec(select(Expense)).all()
    }
    # seen 是「库里已有的 + 本文件已经处理过的」，所以同一个文件里出现两行一样的内容
    # 也只导入第一条，第二条算重复。
    seen = set(existing)

    # 整批导入共用同一个时间戳，方便事后按批次排查问题。
    now = iso_now()
    imported = duplicates = invalid = fallback = 0
    # 两个列表分别收集「无法导入」和「导入了但需要提醒」的行，最多各 50 条。
    errors: list[ImportIssue] = []
    warnings: list[ImportIssue] = []

    # 枚举行号时从 2 开始，是因为第 1 行是表头，这样报错的行号才能和用户在 Excel 里看到的一致。
    for index, raw_row in enumerate(reader, start=2):
        # +1 是给表头留的位置：超过 20000 行数据就整批拒绝，避免半截导入。
        if index > MAX_ROWS + 1:
            raise HTTPException(status_code=400, detail=f"一次最多导入 {MAX_ROWS} 行")

        # 先用 columns 把「日期」这一列取出来解析；解析不了就计一次 invalid 并跳过本行。
        spent_on = _parse_date(raw_row.get(columns["date"], ""))
        if spent_on is None:
            invalid += 1
            # 只保留前 50 条明细，后面的错误只计数不记录，防止响应过大。
            if len(errors) < 50:
                errors.append(ImportIssue(line=index, reason="日期无法识别（应为 2026-11-16 这种格式）"))
            continue

        # 金额同理：拿不到合法的「分」就跳过这行。
        amount_cents = _parse_cents(raw_row.get(columns["amount"], ""))
        if amount_cents is None:
            invalid += 1
            if len(errors) < 50:
                errors.append(ImportIssue(line=index, reason="金额无法识别（应为大于 0、最多两位小数的数字）"))
            continue

        # 分类名先按文本匹配。CSV 里没有 id，只能靠名字找；
        # 注意去掉首尾空格，否则「餐饮 」和「餐饮」会被当成两个分类。
        l1_name = (raw_row.get(columns["l1"], "") or "").strip()
        l2_name = (raw_row.get(columns["l2"], "") or "").strip()
        l1_id = l1_by_name.get(l1_name)
        # 二级分类必须同时匹配「父 id + 名字」，否则「其他」会串到别的分类下面。
        # l1_id 可能是 None，这时不能拿去当字典键查二级。
        l2_id = l2_by_name.get((l1_id, l2_name)) if l1_id is not None else None
        # 只要有一级或二级对不上，就整行落到兜底分类；不丢账单是这里的最高优先级。
        used_fallback = l1_id is None or l2_id is None
        if used_fallback:
            l1_id, l2_id = other_l1, other_l2

        # 备注截断到 200 字，和接口层 note 字段的上限保持一致；
        # columns.get("note", "") 兼容「表里根本没有备注列」的情况。
        note = (raw_row.get(columns.get("note", ""), "") or "").strip()[:200]
        # 组装去重键。注意这里用的是「落库后」的分类 id：如果某行走了兜底，
        # 它的键就是兜底分类的 id，这样和之前已经落到兜底的同一笔也能正确判重。
        key = (spent_on, amount_cents, l1_id, l2_id, note)
        if key in seen:
            duplicates += 1
            continue
        # 立刻加进 seen，防止本文件内部重复的行被导入两次。
        seen.add(key)

        # 分类对不上属于「导入了但有疑点」，单独计数并记警告，让用户知道有账单被归类到了「其他」。
        if used_fallback:
            fallback += 1
            if len(warnings) < 50:
                warnings.append(
                    ImportIssue(line=index, reason=f"分类「{l1_name} / {l2_name}」不存在，已归入「其他 / 未分类」")
                )

        # session.add 只是把对象放进待提交队列，还没有真正写库。
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

    # 循环结束后一次性提交：整批要么全成功，要么全回滚，不会留下「导入了一半」的状态。
    try:
        session.commit()
    except Exception as exc:  # pragma: no cover - 兜底回滚
        # 任何数据库异常（比如磁盘满了、约束冲突）都回滚，并把原因告诉调用方。
        session.rollback()
        raise HTTPException(status_code=500, detail=f"写入数据库失败：{exc}") from exc

    # 四个计数分开返回，前端可以分别提示「导入 N 条 / 重复 N 条 / 失败 N 条 / 归类 N 条」。
    return ImportResult(
        imported=imported,
        duplicates=duplicates,
        invalid=invalid,
        fallback=fallback,
        errors=errors,
        warnings=warnings,
    )
