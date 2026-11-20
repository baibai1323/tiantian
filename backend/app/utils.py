"""金额、日期等小工具。"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal


def iso_now() -> str:
    """本地时区的 ISO 时间戳，例如 2026-11-16T20:15:00+08:00。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_str() -> str:
    """返回本地“今天”的日期字符串。

    返回：str，格式 YYYY-MM-DD（如 "2026-11-20"），可直接和库里的 spent_on 比较。
    """
    return date.today().isoformat()


def current_month() -> str:
    """返回当前月份前缀，用于按月筛选账目。

    返回：str，格式 YYYY-MM（如 "2026-11"）；月份一定补零，补零逻辑见 normalize_month。
    """
    return date.today().strftime("%Y-%m")


def yuan_to_cents(value: Decimal) -> int:
    """把“元”转成整数“分”。输入已由接口校验最多两位小数。"""
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents_to_yuan(cents: int) -> str:
    """把“分”转成两位小数的字符串，例如 2800 -> '28.00'。"""
    return str((Decimal(cents) / Decimal(100)).quantize(Decimal("0.01")))


def is_valid_month(value: str) -> bool:
    """判断字符串是不是合法的 "YYYY-MM" 月份。

    参数 value：待校验的月份文本，例如 "2026-11"。
    返回：bool；能按 %Y-%m 解析成真实日期才为 True，"2026-13" 会解析失败。
    """
    # strptime 会检查月份范围，越界（如 13 月）抛 ValueError，正好用来做校验。
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
    # fullmatch 要求整串完全匹配，避免 "2026-1abc" 这种半对的值被误改。
    match = re.fullmatch(r"(\d{4})-(\d{1,2})", value)
    if match is None:
        return value
    year, month = int(match.group(1)), int(match.group(2))
    # 月份只允许 1~12；越界时原样返回，交给 is_valid_month 去报“格式不对”。
    if not 1 <= month <= 12:
        return value
    # :04d / :02d 是格式化占位：年份补到 4 位、月份补到 2 位（1 变成 01）。
    return f"{year:04d}-{month:02d}"
