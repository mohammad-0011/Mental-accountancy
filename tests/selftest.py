"""آزمون خودکار سرتاسری برنامه از طریق API واقعی (بدون رابط گرافیکی)."""
import os
import sys
import tempfile
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.server import create_app, MODE_ADMIN  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (("  -> " + str(extra)) if extra else ""))


def main():
    tmp = tempfile.mkdtemp(prefix="hesabtest_")
    db_path = os.path.join(tmp, "test.db")
    # نسخهٔ مدیر: همهٔ بخش‌ها و قابلیت‌های پرمیوم باز است و دروازهٔ لایسنس
    # نمی‌بندد؛ آزمون دروازه و فعال‌سازی در tests/test_license.py است.
    app = create_app(db_path, mode=MODE_ADMIN, folder=tmp)
    c = app.test_client()

    # ---------------------------------------------------------------- ورود
    print("\n[۱] ورود به سامانه")
    r = c.post("/api/login", json={"username": "admin", "password": "admin"})
    check("ورود با کاربر پیش‌فرض", r.get_json().get("ok") is True)
    r = c.post("/api/login", json={"username": "admin", "password": "bad"})
    check("رد گذرواژه نادرست", r.status_code == 401)

    meta = c.get("/api/meta").get_json()["data"]
    wh = meta["warehouses"][0]["id"]
    check("بارگذاری اطلاعات پایه", len(meta["warehouses"]) >= 2)

    # ------------------------------------------------------------- تعاریف
    print("\n[۲] تعاریف پایه (شخص، کالا، انبار)")
    r = c.post("/api/parties", json={"name": "آقای رضایی", "party_type": "customer",
                                     "mobile": "09120000000", "opening_balance": 0})
    party = r.get_json()["data"]["id"]
    check("ثبت مشتری", party > 0)

    r = c.post("/api/parties", json={"name": "شرکت بازیافت سبز",
                                     "party_type": "supplier"})
    recycler = r.get_json()["data"]["id"]
    check("ثبت خریدار ضایعات", recycler > 0)

    gid = c.get("/api/groups").get_json()["data"][0]["id"]
    uid = c.get("/api/units").get_json()["data"][0]["id"]
    r = c.post("/api/products", json={
        "name": "باتری وارتا ۶۶ آمپر", "code": "B-66", "barcode": "6260001",
        "group_id": gid, "unit_id": uid, "brand": "وارتا", "amperage": "66",
        "battery_type": "خودرو", "warranty_months": 12,
        "purchase_price": 2000000, "sale_price": 2600000, "reorder_level": 2,
        "is_battery": 1, "opening_stock": 10, "opening_date": "1405/07/01"})
    prod = r.get_json()["data"]["id"]
    check("ثبت کالا با موجودی اولیه", prod > 0)

    inv = c.get("/api/reports/inventory").get_json()["data"]
    row = [x for x in inv if x["id"] == prod][0]
    check("موجودی اولیه ۱۰ عدد ثبت شد", abs(row["stock"] - 10) < 1e-6, row["stock"])
    check("ارزش موجودی محاسبه شد", abs(row["value"] - 20_000_000) < 1,
          row["value"])

    # ------------------------------------------------------------- فاکتور فروش
    print("\n[۳] فاکتور فروش با سریال و گارانتی")
    r = c.post("/api/invoices", json={
        "kind": "sale", "date": "1405/07/22", "party_id": party,
        "warehouse_id": wh, "discount": 100000, "tax_rate": 9,
        "paid_cash": 1000000, "items": [
            {"product_id": prod, "qty": 2, "unit_price": 2600000, "discount": 0,
             "tax_rate": 9, "serial": "SN-AAA-001", "warranty_months": 12,
             "cost_price": 2000000}]})
    check("ثبت فاکتور فروش", r.get_json().get("ok") is True, r.get_json().get("error"))
    sale_id = r.get_json()["data"]["id"]

    det = c.get("/api/invoices/%d" % sale_id).get_json()["data"]
    total = det["invoice"]["total"]
    expected_total = (2 * 2_600_000) - 100_000
    expected_tax = expected_total * 0.09
    check("مبلغ فاکتور صحیح است",
          abs(total - (expected_total + expected_tax)) < 1,
          "{} vs {}".format(total, expected_total + expected_tax))

    st = c.get("/api/reports/inventory").get_json()["data"]
    left = [x for x in st if x["id"] == prod][0]["stock"]
    check("کسر ۲ عدد از انبار", abs(left - 8) < 1e-6, left)

    led = c.get("/api/parties/%d/ledger" % party).get_json()["data"]
    bal = led["balance"]
    check("مانده حساب مشتری = مبلغ نسیه",
          abs(bal - (total - 1_000_000)) < 1, "{} vs {}".format(bal, total - 1_000_000))

    ser = c.get("/api/serials?q=SN-AAA-001").get_json()["data"]
    check("ثبت سریال باتری", len(ser) == 1 and ser[0]["warranty_end"] == "1406/07/22",
          ser[0]["warranty_end"] if ser else None)

    tb = c.get("/api/reports/trial-balance").get_json()["data"]
    td = sum(x["debit"] for x in tb)
    tc = sum(x["credit"] for x in tb)
    check("تراز آزمایشی متوازن است", abs(td - tc) < 1, "{} / {}".format(td, tc))

    # ------------------------------------------------------- برگشت از فروش
    print("\n[۴] برگشت از فروش")
    r = c.post("/api/invoices", json={
        "kind": "sale_return", "date": "1405/07/23", "party_id": party,
        "warehouse_id": wh, "paid_cash": 0, "items": [
            {"product_id": prod, "qty": 1, "unit_price": 2600000, "discount": 0,
             "tax_rate": 9, "cost_price": 2000000}]})
    check("ثبت برگشت از فروش", r.get_json().get("ok") is True, r.get_json().get("error"))
    st = c.get("/api/reports/inventory").get_json()["data"]
    back = [x for x in st if x["id"] == prod][0]["stock"]
    check("برگشت ۱ عدد به انبار", abs(back - 9) < 1e-6, back)

    # ------------------------------------------------------------- فاکتور خرید
    print("\n[۵] فاکتور خرید")
    r = c.post("/api/invoices", json={
        "kind": "purchase", "date": "1405/07/24", "party_id": recycler,
        "warehouse_id": wh, "tax_rate": 9, "paid_cash": 5000000, "items": [
            {"product_id": prod, "qty": 5, "unit_price": 2000000, "discount": 0,
             "tax_rate": 9, "cost_price": 2000000}]})
    check("ثبت فاکتور خرید", r.get_json().get("ok") is True, r.get_json().get("error"))
    st = c.get("/api/reports/inventory").get_json()["data"]
    after = [x for x in st if x["id"] == prod][0]["stock"]
    check("افزایش ۵ عدد به انبار", abs(after - 14) < 1e-6, after)

    # --------------------------------------------------------- دریافت و پرداخت
    print("\n[۶] دریافت و پرداخت وجه")
    bal_before = c.get("/api/parties/%d/ledger" % party).get_json()["data"]["balance"]
    r = c.post("/api/receipts", json={"kind": "receive", "party_id": party,
                                      "amount": 2000000, "method": "cash",
                                      "date": "1405/07/25"})
    check("ثبت دریافت وجه", r.get_json().get("ok") is True, r.get_json().get("error"))
    bal2 = c.get("/api/parties/%d/ledger" % party).get_json()["data"]["balance"]
    check("کاهش مانده مشتری پس از دریافت", abs(bal2 - (bal_before - 2_000_000)) < 1,
          "{} -> {}".format(bal_before, bal2))

    # ---------------------------------------------------------------- چک
    print("\n[۷] چک دریافتنی")
    r = c.post("/api/cheques", json={"number": "123456", "ctype": "receivable",
                                     "party_id": party, "bank": "ملت",
                                     "amount": 3000000, "issue_date": "1405/07/25",
                                     "due_date": "1405/08/05", "status": "in_hand"})
    cid = r.get_json()["data"]["id"]
    check("ثبت چک دریافتنی", cid > 0)
    due = c.get("/api/reports/cheque-due?days=30").get_json()["data"]
    check("چک در گزارش سررسید دیده می‌شود", any(x["id"] == cid for x in due))

    # ---------------------------------------------------- باتری فرسوده / ضایعات
    print("\n[۸] باتری فرسوده و فروش ضایعات")
    r = c.post("/api/scrap", json={"date": "1405/07/26", "party_id": party,
                                   "brand": "سپاهان", "amperage": "۶۶",
                                   "qty": 10, "weight_kg": 100, "price_per_kg": 300000,
                                   "amount": 100 * 300000, "method": "cash"})
    check("ثبت خرید باتری فرسوده", r.get_json().get("ok") is True, r.get_json().get("error"))
    sstock = c.get("/api/scrap/stock").get_json()["data"]
    check("موجودی ضایعات = ۱۰۰ کیلوگرم", abs(sstock["weight"] - 100) < 1e-6,
          sstock["weight"])
    check("ارزش ضایعات = ۳۰٬۰۰۰٬۰۰۰", abs(sstock["value"] - 30_000_000) < 1,
          sstock["value"])

    r = c.post("/api/scrap/sales", json={"date": "1405/07/27", "party_id": recycler,
                                         "weight_kg": 60, "qty": 6,
                                         "price_per_kg": 350000, "method": "cash"})
    check("ثبت فروش ضایعات", r.get_json().get("ok") is True, r.get_json().get("error"))
    sstock = c.get("/api/scrap/stock").get_json()["data"]
    check("کاهش موجودی ضایعات به ۴۰ کیلوگرم", abs(sstock["weight"] - 40) < 1e-6,
          sstock["weight"])

    r = c.post("/api/scrap/sales", json={"weight_kg": 999, "price_per_kg": 1})
    check("جلوگیری از فروش بیش از موجودی ضایعات", r.status_code == 400)

    # ------------------------------------------------------------- گارانتی
    print("\n[۹] مرجوعی گارانتی و تبدیل به ضایعات")
    sid = ser[0]["id"]
    r = c.post("/api/serials/claim", json={"serial_id": sid, "note": "خرابی"})
    check("ثبت مرجوعی گارانتی", r.get_json().get("ok") is True)
    r = c.post("/api/serials/scrap", json={"serial_id": sid, "weight_kg": 12,
                                           "price_per_kg": 300000, "qty": 1,
                                           "method": "cash"})
    check("تبدیل باتری مرجوعی به ضایعات", r.get_json().get("ok") is True,
          r.get_json().get("error"))
    row = [x for x in c.get("/api/serials").get_json()["data"] if x["id"] == sid][0]
    check("وضعیت سریال به ضایعات تغییر کرد", row["status"] == "scrap", row["status"])

    # -------------------------------------------------------------- سند دستی
    print("\n[۱۰] سند حسابداری دستی")
    r = c.post("/api/journal", json={"date": "1405/07/28", "description": "آزمون",
        "lines": [{"account": "هزینه‌های عملیاتی", "debit": 500000, "credit": 0},
                  {"account": "صندوق", "debit": 0, "credit": 500000}]})
    check("ثبت سند دستی تراز", r.get_json().get("ok") is True, r.get_json().get("error"))
    r = c.post("/api/journal", json={"date": "1405/07/28", "description": "ناتراز",
        "lines": [{"account": "صندوق", "debit": 100, "credit": 0},
                  {"account": "بانک", "debit": 0, "credit": 50}]})
    check("رد سند ناتراز", r.status_code == 400)

    # -------------------------------------------------------------- گزارش‌ها
    print("\n[۱۱] گزارش‌های مالی")
    pl = c.get("/api/reports/profit-loss").get_json()["data"]
    # فروش کالا: ۲ عدد ۲.۶م - ۱۰۰هزار تخفیف = ۵.۱م ؛ برگشت: ۱ عدد ۲.۶م => خالص ۲.۵م
    # به‌علاوهٔ فروش ضایعات: ۶۰ کیلوگرم × ۳۵۰٬۰۰۰ = ۲۱م
    check("درآمد خالص (فروش + ضایعات) = ۲۳٬۵۰۰٬۰۰۰",
          abs(pl["total_revenue"] - 23_500_000) < 1, pl["total_revenue"])
    bs = c.get("/api/reports/balance-sheet").get_json()["data"]
    check("ترازنامه متوازن است (دارایی = بدهی + سرمایه)",
          abs(bs["total_assets"] - (bs["total_liabilities"] + bs["equity"])) < 1)
    check("دارایی‌ها محاسبه شده", bs["total_assets"] > 0, bs["total_assets"])

    tb = c.get("/api/reports/trial-balance").get_json()["data"]
    check("تراز نهایی متوازن",
          abs(sum(x["debit"] for x in tb) - sum(x["credit"] for x in tb)) < 1)

    # --------------------------------------------------------------- حذف فاکتور
    print("\n[۱۲] حذف فاکتور و برگشت اثرات")
    before = [x for x in c.get("/api/reports/inventory").get_json()["data"]
              if x["id"] == prod][0]["stock"]
    r = c.delete("/api/invoices/%d" % sale_id)
    check("حذف فاکتور فروش", r.get_json().get("ok") is True)
    after = [x for x in c.get("/api/reports/inventory").get_json()["data"]
             if x["id"] == prod][0]["stock"]
    check("برگشت موجودی پس از حذف فاکتور", abs(after - (before + 2)) < 1e-6,
          "{} -> {}".format(before, after))
    tb = c.get("/api/reports/trial-balance").get_json()["data"]
    check("تراز پس از حذف همچنان متوازن",
          abs(sum(x["debit"] for x in tb) - sum(x["credit"] for x in tb)) < 1)

    # --------------------------------------------------------------- بقیه API
    print("\n[۱۳] سایر سرویس‌ها")
    pl2 = c.get("/api/reports/profit-loss?from=1405/07/01&to=1405/12/29")
    check("سود و زیان با بازهٔ تاریخی", pl2.status_code == 200, pl2.status_code)
    for path in ["dashboard", "activity", "audit", "notes", "users", "receipts",
                 "cheques", "scrap", "scrap/sales", "serials", "invoices",
                 "reports/debtors", "reports/journal", "reports/sales-summary",
                 "reports/product-sales", "stock/moves", "stock/levels",
                 "settings", "search?q=باتری"]:
        rr = c.get("/api/" + path)
        check("GET /api/" + path, rr.status_code == 200, rr.status_code)

    print("\n" + "=" * 56)
    print("نتیجه: {} موفق، {} ناموفق".format(len(PASS), len(FAIL)))
    if FAIL:
        print("ناموفق‌ها: " + "، ".join(FAIL))
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
