"""金额、日期等小工具。"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal


def iso_now() -> str:
    """本地时区的 ISO 时间戳，例如 2026-11-16T20:15:00+08:00。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_str() -> str:
    return date.today().isoformat()


def current_month() -> str:
    return date.today().strftime("%Y-%m")


def yuan_to_cents(value: Decimal) -> int:
    """把“元”转成整数“分”。输入已由接口校验最多两位小数。"""
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents_to_yuan(cents: int) -> str:
    """把“分”转成两位小数的字符串，例如 2800 -> '28.00'。"""
    return str((Decimal(cents) / Decimal(100)).quantize(Decimal("0.01")))


def is_valid_month(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m")
        return True
    except ValueError:
        return False


def normalize_month(value: str) -> str:
    """把 "2026-1" 这种没补零的月份统一成 "YYYY-MM"。

    只接受“4 位年 + 1~2 位月”的形状，其余原样返回，交给 is_valid_month 判定；
    避免 "26-1" 被补成 "0026-01" 这种看似合法、实际毫无意义的值。
    """
    match = re.fullmatch(r"(\d{4})-(\d{1,2})", value)
    if match is None:
        return value
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return value
    return f"{year:04d}-{month:02d}"
