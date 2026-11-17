"""预置分类：10 个一级分类 + 约 70 个二级分类。"""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Category

# (图标, 一级分类名, [二级分类名, ...])
SEED_CATEGORIES: list[tuple[str, str, list[str]]] = [
    ("🍜", "餐饮", ["早餐", "午餐", "晚餐", "夜宵外卖", "饮品咖啡", "零食水果", "买菜食材", "聚餐请客"]),
    ("🚇", "交通", ["公交地铁", "打车网约车", "火车高铁", "飞机", "加油充电", "停车过路", "共享单车", "车辆养护"]),
    ("🛍️", "购物", ["日用百货", "服饰鞋包", "数码电器", "美妆护肤", "家居家具", "母婴用品", "宠物用品", "其他购物"]),
    ("🏠", "居住", ["房租", "房贷", "物业费", "水费", "电费", "燃气费", "取暖费", "宽带话费", "家政维修"]),
    ("🎮", "娱乐", ["电影演出", "游戏", "会员订阅", "运动健身", "休闲玩乐", "烟酒"]),
    ("🏥", "医疗健康", ["门诊挂号", "药品", "体检", "牙科", "住院", "保健品", "心理咨询"]),
    ("📚", "教育", ["学费", "培训课程", "书籍资料", "考试报名", "文具", "软件工具"]),
    ("🎁", "人情往来", ["红包礼金", "礼物", "请客招待", "孝敬长辈", "慈善捐赠"]),
    ("✈️", "旅行", ["交通", "住宿", "门票", "餐饮", "购物", "其他旅行"]),
    ("📦", "其他", ["手续费", "罚款", "丢失", "未分类"]),
]


def seed_categories(session: Session, now: str) -> int:
    """只在分类表为空时写入预置数据，返回写入的一级分类数量。"""
    existing = session.exec(select(Category.id).limit(1)).first()
    if existing is not None:
        return 0

    for l1_index, (icon, l1_name, children) in enumerate(SEED_CATEGORIES):
        l1 = Category(
            parent_id=None,
            name=l1_name,
            icon=icon,
            sort_order=(l1_index + 1) * 100,
            created_at=now,
        )
        session.add(l1)
        session.flush()  # 拿到自增 id
        for l2_index, l2_name in enumerate(children):
            session.add(
                Category(
                    parent_id=l1.id,
                    name=l2_name,
                    icon=icon,
                    sort_order=(l2_index + 1) * 10,
                    created_at=now,
                )
            )
    session.commit()
    return len(SEED_CATEGORIES)
