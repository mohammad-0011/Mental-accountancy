"""تبدیل تاریخ شمسی (جلالی) و میلادی.

الگوریتم چرخه ۳۳ ساله؛ برای بازه ۱۳۰۰ تا ۱۵۰۰ شمسی دقیق است.
"""
from datetime import date, datetime, timedelta

MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

_G_DAYS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def gregorian_to_jalali(gy, gm, gd):
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
            + ((gy2 + 399) // 400) + gd + _G_DAYS[gm - 1])
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy, jm, jd):
    jy += 1595
    days = (-355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4)
            + jd + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186))
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    month_days = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    for gm in range(1, 13):
        if gd <= month_days[gm]:
            break
        gd -= month_days[gm]
    return gy, gm, gd


def is_jalali_leap(jy):
    # طول سال را از تبدیل خود تقویم می‌گیریم تا با الگوریتم هم‌خوان باشد
    g1 = jalali_to_gregorian(jy, 1, 1)
    g2 = jalali_to_gregorian(jy + 1, 1, 1)
    return (date(g2[0], g2[1], g2[2]) - date(g1[0], g1[1], g1[2])).days == 366


def days_in_jalali_month(jy, jm):
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_jalali_leap(jy) else 29


def today_jalali():
    t = date.today()
    return gregorian_to_jalali(t.year, t.month, t.day)


def fmt(jy, jm, jd, sep="/"):
    return "{}{}{:02d}{}{:02d}".format(jy, sep, jm, sep, jd)


def today_str():
    return fmt(*today_jalali())


def parse_jalali(s):
    """رشته ۱۴۰۵/۰۷/۲۲ را به (jy, jm, jd) تبدیل می‌کند."""
    if not s:
        return today_jalali()
    s = str(s).strip().replace("-", "/").replace(".", "/")
    parts = [p for p in s.split("/") if p != ""]
    if len(parts) != 3:
        return today_jalali()
    try:
        jy, jm, jd = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return today_jalali()
    if jy < 1000:
        jy += 1300
    return jy, jm, jd


def jalali_to_iso(s):
    return "%04d-%02d-%02d" % jalali_to_gregorian(*parse_jalali(s))


def iso_to_jalali_str(iso):
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return today_str()
    return fmt(*gregorian_to_jalali(d.year, d.month, d.day))


def weekday_name(s):
    g = jalali_to_gregorian(*parse_jalali(s))
    d = date(g[0], g[1], g[2])
    # در ایران هفته از شنبه شروع می‌شود؛ date.weekday() دوشنبه=۰
    return WEEKDAYS[(d.weekday() + 2) % 7]


def add_months(s, months):
    jy, jm, jd = parse_jalali(s)
    total = (jy * 12 + (jm - 1)) + months
    jy2, jm2 = total // 12, (total % 12) + 1
    jd2 = min(jd, days_in_jalali_month(jy2, jm2))
    return fmt(jy2, jm2, jd2)


def add_days(s, days):
    """تاریخ شمسی پس از افزودن چند روز (منفی هم مجاز است)."""
    gy, gm, gd = jalali_to_gregorian(*parse_jalali(s))
    target = date(gy, gm, gd) + timedelta(days=int(days))
    return fmt(*gregorian_to_jalali(target.year, target.month, target.day))


def diff_days(a, b):
    """تعداد روز از تاریخ a تا b (b - a)."""
    ga = jalali_to_gregorian(*parse_jalali(a))
    gb = jalali_to_gregorian(*parse_jalali(b))
    return (date(*gb) - date(*ga)).days


def month_range(s):
    jy, jm, _ = parse_jalali(s)
    return fmt(jy, jm, 1), fmt(jy, jm, days_in_jalali_month(jy, jm))


def year_range(s):
    jy, _, _ = parse_jalali(s)
    return fmt(jy, 1, 1), fmt(jy, 12, days_in_jalali_month(jy, 12))


def jalali_year(s):
    return parse_jalali(s)[0]
