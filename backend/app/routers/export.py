"""CSV 导出（C+5）。"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..db import get_session
from ..models import Expense
from ..services import load_categories
from ..utils import cents_to_yuan, is_valid_month, normalize_month

router = APIRouter(prefix="/api/export", tags=["export"])

# CSV（逗号分隔值）是一种纯文本表格格式，Excel、WPS、Numbers 都能直接打开。
# 本文件导出的表头格式和 importer.py 读取的表头是对应的，导出的文件可以再导回来。
# 「流式响应」指不把整个文件先拼成一个字符串再返回，而是边生成边发；这里数据量小，
# 所以实际上只有一块内容，但用流式接口能让浏览器按「下载文件」而不是「显示文本」处理。


@router.get("/csv")
def export_csv(
    month: str | None = Query(default=None, description="YYYY-MM，不传则导出全部"),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """把账单导出成 CSV 文件，供用户下载或用 Excel 打开。

    做什么：按可选月份筛选未删除的账单，把分类 id 换成中文名，
    拼成「日期, 一级分类, 二级分类, 金额(元), 备注」的表，再以文件流的形式返回。
    参数 month：要导出的月份 YYYY-MM；不传表示导出全部账单（可能很大，谨慎使用）。
    参数 session：数据库会话，由框架注入。
    返回：StreamingResponse，响应头里带 Content-Disposition，浏览器看到它就会弹出下载框。
    """
    # 所有导出都排除软删除的记录：回收站里的账单不该出现在给用户的对账单里。
    conditions = [Expense.deleted_at.is_(None)]
    # month 是可选的：不传就是「导出全部」，所以这里用 if month 而不是判断 is None。
    if month:
        # 补零后再校验，"2026-1" 这种写法也能正确导出。
        month = normalize_month(month)
        if not is_valid_month(month):
            # 这里的 import 写在函数内部是沿用现有写法（避免顶部再多一个导入），
            # HTTPException 表示一个会直接变成 HTTP 错误响应的异常。
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM")
        # 和列表接口同一套前缀匹配：spent_on 是 "YYYY-MM-DD"，用 "YYYY-MM-%" 圈出整月。
        conditions.append(Expense.spent_on.like(f"{month}-%"))

    # 导出按日期正序（从早到晚），和界面上「新的在上」相反，这样打印出来更像流水账。
    rows = session.exec(
        select(Expense).where(*conditions).order_by(Expense.spent_on, Expense.id)
    ).all()
    # 账单表里只存分类 id，导出给人看要换成中文名，所以要先把分类读进字典。
    categories = load_categories(session)

    # StringIO 是「内存里的文本文件」，用法和 open() 打开的文件一样，但不会真的落盘。
    buffer = io.StringIO()
    buffer.write("\ufeff")  # BOM：让 Excel 正确识别 UTF-8 中文
    # BOM（字节顺序标记）是文件开头的一个隐藏字符。没有它，Excel 在中文 Windows 上
    # 常会把 UTF-8 当成 GBK 解码，中文分类名就会变成乱码。
    writer = csv.writer(buffer)
    # 表头文字必须和 importer.py 的别名表对得上，否则导出的文件再导入会报「缺少列」。
    writer.writerow(["日期", "一级分类", "二级分类", "金额(元)", "备注"])
    for row in rows:
        # 分类被删后账单已迁到兜底分类，正常不会取不到；取不到时写空串而不是报错。
        l1 = categories.get(row.category_l1)
        l2 = categories.get(row.category_l2)
        # csv.writer 会自动处理转义：备注里含逗号、引号、换行时会给整个字段加引号，
        # 所以这里不用手动处理，直接按列顺序传值即可。
        writer.writerow(
            [
                row.spent_on,
                l1.name if l1 else "",
                l2.name if l2 else "",
                # 金额导出成 "28.00" 这种两位小数的字符串，Excel 会识别成数字。
                cents_to_yuan(row.amount_cents),
                row.note,
            ]
        )

    # 文件名带月份便于区分；没传月份时用 all 表示全量导出。
    filename = f"tiantian-{month or 'all'}.csv"
    # encode("utf-8") 把内存里的字符串变成字节流，StreamingResponse 只接受字节。
    # media_type 声明内容类型；charset=utf-8 让浏览器知道按 UTF-8 解码。
    # Content-Disposition 的 attachment 就是「作为附件下载」的意思，filename 是默认文件名。
    return StreamingResponse(
        iter([buffer.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
