# 二十四节气日期表（基于天文近似计算，日序从年初算起）
# 每个节气用 (月份, 约日, 名称) 表示
# 实际日期每年可能有1-2天浮动，这里取近似值用于日常推荐

SOLAR_TERMS = [
    (1, 5, "小寒"), (1, 20, "大寒"),
    (2, 4, "立春"), (2, 19, "雨水"),
    (3, 5, "惊蛰"), (3, 20, "春分"),
    (4, 4, "清明"), (4, 19, "谷雨"),
    (5, 5, "立夏"), (5, 21, "小满"),
    (6, 5, "芒种"), (6, 21, "夏至"),
    (7, 7, "小暑"), (7, 22, "大暑"),
    (8, 7, "立秋"), (8, 23, "处暑"),
    (9, 7, "白露"), (9, 22, "秋分"),
    (10, 8, "寒露"), (10, 23, "霜降"),
    (11, 7, "立冬"), (11, 22, "小雪"),
    (12, 7, "大雪"), (12, 21, "冬至"),
]

# 节气养生要点
TERM_HEALTH_TIPS = {
    "小寒": "温补阳气，适当进补，注意保暖防寒，宜食羊肉、核桃、韭菜",
    "大寒": "温补脾胃，养精蓄锐，为春季生发储备能量，宜食牛肉、山药、桂圆",
    "立春": "助阳生发，疏肝理气，少酸多甘，宜食韭菜、豆芽、春笋、荠菜",
    "雨水": "健脾祛湿，养护脾胃，防春寒，宜食薏米、山药、红枣、小米",
    "惊蛰": "养肝健脾，清温平淡，多吃蔬菜，宜食菠菜、芹菜、梨、蜂蜜",
    "春分": "阴阳平衡，调养肝脾，清淡饮食，宜食荠菜、香椿、鸡蛋、枸杞",
    "清明": "疏肝理气，清补为主，多吃柔肝养肺之物，宜食菊花、桑葚、银耳",
    "谷雨": "健脾祛湿，养肝明目，防春火，宜食薏米、赤小豆、冬瓜、绿茶",
    "立夏": "养心安神，清热解暑，增酸减苦，宜食莲子、百合、绿豆、西瓜",
    "小满": "清热利湿，养心健脾，防湿热，宜食苦瓜、黄瓜、薏米、鸭肉",
    "芒种": "清热祛暑，健脾益气，清淡补钾，宜食绿豆、冬瓜、荷叶、鲫鱼",
    "夏至": "清心泻火，滋阴养心，少食生冷，宜食莲子心、苦瓜、番茄、酸梅",
    "小暑": "清热解暑，养心安神，健脾利湿，宜食绿豆、荷叶、西瓜、薄荷",
    "大暑": "清热解暑，益气养阴，防暑降温，宜食冬瓜、苦瓜、菊花、金银花",
    "立秋": "养阴润燥，健脾祛湿，少辛增酸，宜食百合、银耳、梨、莲藕",
    "处暑": "养阴清热，润燥生津，防秋燥，宜食鸭肉、百合、蜂蜜、雪梨",
    "白露": "滋阴润肺，防燥护阴，温补为主，宜食银耳、山药、杏仁、芝麻",
    "秋分": "阴阳平衡，润肺健脾，养阴防燥，宜食梨、百合、莲藕、荸荠",
    "寒露": "养阴润肺，温中散寒，防寒防燥，宜食芝麻、核桃、红枣、枸杞",
    "霜降": "温补脾胃，养肺润燥，为过冬做准备，宜食牛肉、山药、柿子、板栗",
    "立冬": "温补肾阳，滋阴潜阳，增苦减咸，宜食羊肉、核桃、黑豆、当归",
    "小雪": "温补肾阳，养心安神，防寒保暖，宜食羊肉、牛肉、红枣、黑芝麻",
    "大雪": "温补脾肾，养阴益精，御寒进补，宜食羊肉、鸡肉、枸杞、黄芪",
    "冬至": "温补阳气，养肾防寒，一阳初生宜静养，宜食饺子、羊肉、当归、生姜",
}

import time
from datetime import date


def get_current_term(d: date = None) -> tuple[str, int, str]:
    """返回 (节气名, 月, 日, 养生要点)"""
    if d is None:
        d = date.today()
    month, day = d.month, d.day

    # 找到当前日期对应的节气
    current_term = None
    for i, (m, approx_day, name) in enumerate(SOLAR_TERMS):
        if (month > m) or (month == m and day >= approx_day):
            current_term = (name, m, approx_day)
        else:
            break

    if current_term is None:
        # 1月1日到小寒前，取冬至
        current_term = ("冬至", 12, 21)

    tip = TERM_HEALTH_TIPS.get(current_term[0], "")
    return current_term[0], current_term[1], current_term[2], tip


def get_season_from_term(term_name: str) -> str:
    spring_terms = {"立春", "雨水", "惊蛰", "春分", "清明", "谷雨"}
    summer_terms = {"立夏", "小满", "芒种", "夏至", "小暑", "大暑"}
    autumn_terms = {"立秋", "处暑", "白露", "秋分", "寒露", "霜降"}
    winter_terms = {"立冬", "小雪", "大雪", "冬至", "小寒", "大寒"}

    if term_name in spring_terms: return "春"
    if term_name in summer_terms: return "夏"
    if term_name in autumn_terms: return "秋"
    if term_name in winter_terms: return "冬"
    return "春"


def get_weekday_name(d: date = None) -> str:
    if d is None:
        d = date.today()
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return names[d.weekday()]


def format_daily_context(d: date = None) -> str:
    if d is None:
        d = date.today()
    term, m, day_of_term, tip = get_current_term(d)
    season = get_season_from_term(term)
    weekday = get_weekday_name(d)
    return {
        "date": d.strftime("%Y年%m月%d日"),
        "weekday": weekday,
        "solar_term": term,
        "season": season,
        "term_health_tip": tip,
        "month": d.month,
        "day": d.day,
    }
