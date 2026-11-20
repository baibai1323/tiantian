"""预置分类：10 个一级分类 + 约 70 个二级分类。"""

from __future__ import annotations

from sqlmodel import Session, select

from .models import Category

# 数据结构是 (一级分类图标, 一级分类名, [二级分类名, ...]) 的元组；
# 二级分类沿用一级的图标，前端只显示文字时也不会缺图。
# 列表顺序就是界面上的默认顺序，sort_order 会按下标自动算出来。
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
    # 用“表里有没有任意一行分类”判断是否首次启动：只要用户动过分类表就不再灌，
    # 避免用户删掉某个预置分类后，下次启动又被塞回来。
    existing = session.exec(select(Category.id).limit(1)).first()
    if existing is not None:
        # 已经不是空表，返回 0 表示“这次没有写入任何一级分类”。
        return 0

    # enumerate 同时拿到下标和元素；下标从 0 开始，所以算排序值时要先 +1。
    for l1_index, (icon, l1_name, children) in enumerate(SEED_CATEGORIES):
        # parent_id 传 None 表示这是一级分类；created_at 用调用方传进来的同一个时间。
        l1 = Category(
            parent_id=None,
            name=l1_name,
            icon=icon,
            # 一级分类排序值按 100 递增（100、200……），给以后手工插入留出空隙。
            sort_order=(l1_index + 1) * 100,
            created_at=now,
        )
        # 先加一级分类，它必须先入库拿到 id，二级分类才能引用它。
        session.add(l1)
        # flush 把 INSERT 发给数据库但先不提交，目的是拿到数据库生成的自增 id，
        # 下面二级分类的 parent_id 要用它。
        session.flush()  # 拿到自增 id
        for l2_index, l2_name in enumerate(children):
            # 二级分类排序值按 10 递增（10、20……），同一父分类下顺序稳定。
            session.add(
                Category(
                    parent_id=l1.id,
                    name=l2_name,
                    # 二级分类复用一级分类的图标，这样只显示二级时也有图标可用。
                    icon=icon,
                    sort_order=(l2_index + 1) * 10,
                    created_at=now,
                )
            )
    # 全部加完后一次提交：要么全成功，要么全失败，不会只灌一半分类。
    session.commit()
    # 返回写入的一级分类个数，调用方可用于日志或测试断言。
    return len(SEED_CATEGORIES)
