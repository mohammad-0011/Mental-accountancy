"""آزمون سیستم لایسنس، اکانت و دسترسی‌ها.

پوشش:
  * رمزنگاری Ed25519 روی بردارهای رسمی RFC 8032 (TESt 1..3)
  * قالب لایسنس، تشخیص دست‌کاری، انقضا، قید دستگاه و نگهبان عقب‌بردن ساعت
  * جریان کامل HTTP: دروازهٔ نسخهٔ کاربری، صدور لایسنس در نسخهٔ مدیر، فعال‌سازی
  * حساب‌کاربری: نقش مدیر، سهم کاربران، قفل ورود، دسترسی‌های واگذارشده
  * قابلیت‌های پرمیوم (402) در نسخهٔ پایه و باز بودن آن‌ها در نسخهٔ مدیر

اجرا:  python tests/test_license.py
"""
import binascii
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import licensing  # noqa: E402
from app import jdate  # noqa: E402
from app.server import create_app, MODE_ADMIN, MODE_USER  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (("  -> " + str(extra)) if extra else ""))


# ------------------------------------------------------ بردارهای رسمی RFC 8032
# منبع: RFC 8032 بخش ۷.۱
RFC8032 = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


def test_rfc8032():
    print("\n[۱] رمزنگاری Ed25519 — بردارهای رسمی RFC 8032")
    for i, (sk, pk, msg, sig) in enumerate(RFC8032, 1):
        skb, pkb = binascii.unhexlify(sk), binascii.unhexlify(pk)
        mb, sb = binascii.unhexlify(msg), binascii.unhexlify(sig)
        check("بردار {}: امضا دقیقاً مطابق استاندارد است".format(i),
              licensing.sign_bytes(mb, skb) == sb)
        check("بردار {}: امضای استاندارد تأیید می‌شود".format(i),
              licensing.verify_bytes(mb, sb, pkb))
        bad = bytearray(sb)
        bad[0] ^= 0x01
        check("بردار {}: امضای دست‌کاری‌شده رد می‌شود".format(i),
              not licensing.verify_bytes(mb, bytes(bad), pkb))


def test_keypair_and_license():
    print("\n[۲] جفت‌کلید، قالب لایسنس و تشخیص دست‌کاری")
    priv, pub = licensing.generate_keypair()
    check("طول کلید خصوصی/عمومی ۳۲ بایت است", len(priv) == 32 and len(pub) == 32)
    pt, qt = licensing.keypair_to_text(priv, pub)
    check("کلیدها به متن و برگشت تبدیل می‌شوند",
          licensing.keypair_from_text(pt, qt) == (priv, pub))

    lic = licensing.issue_license(priv, customer="فروشگاه باتری رضایی",
                                  edition="premium", seats=3, months=12)
    check("صدور لایسنس متن کلید می‌دهد", lic["key"].startswith(licensing.KEY_PREFIX + "."))
    info = licensing.verify_license(lic["key"], pub, "any-machine")
    check("لایسنس بدون قید دستگاه روی هر رایانه‌ای معتبر است", info["valid"], info["message"])
    check("نام مشتری درست خوانده می‌شود", info["customer"] == "فروشگاه باتری رضایی")
    check("همهٔ قابلیت‌های پرمیوم در لایسنس است",
          set(info["features"]) == set(licensing.ALL_FEATURES))
    check("سقف کاربران درست خوانده می‌شود", info["seats"] == 3)

    # دست‌کاری بدنه: یک قابلیت اضافه می‌شود
    payload, sig = licensing.decode_license(lic["key"])
    payload["seats"] = 999
    forged = licensing.encode_license(payload, sig)
    bad = licensing.verify_license(forged, pub, "any-machine")
    check("تغییر بدنه لایسنس امضا را باطل می‌کند",
          not bad["valid"] and bad["reason"] == "signature")

    # امضای جعلی با کلید دیگر
    other_priv, other_pub = licensing.generate_keypair()
    fake = licensing.issue_license(other_priv, customer="جعلی")
    bad = licensing.verify_license(fake["key"], pub, "any-machine")
    check("لایسنس امضاشده با کلید دیگر پذیرفته نمی‌شود",
          not bad["valid"] and bad["reason"] == "signature")

    # فایل .key
    file_text = licensing.license_file_text(payload, sig, customer="تست")
    p2, s2 = licensing.decode_license_file(file_text)
    check("فایل .key با محتوای JSON خوانده می‌شود", s2 == sig and isinstance(p2, dict))
    check("متن خام لایسنس هم خوانده می‌شود",
          licensing.decode_license_file(lic["key"])[1] == sig)
    for junk in ("", "   ", "سلام", "SABA1.abc", '{"a":1}'):
        try:
            licensing.decode_license_file(junk)
            ok = False
        except licensing.LicenseError:
            ok = True
        check("ورودی نامعتبر رد می‌شود: {!r}".format(junk[:12]), ok)


def test_machine_and_dates():
    print("\n[۳] قید دستگاه، انقضا و نگهبان ساعت")
    priv, pub = licensing.generate_keypair()
    fp = "a" * 64
    code = licensing.machine_code(fp)
    check("کد دستگاه ۲۰ نویسه در ۴ گروه است", len(code) == 24 and code.count("-") == 4, code)
    check("مقایسهٔ کد دستگاه با حروف بزرگ/کوچک و خط تیره کار می‌کند",
          licensing.machine_matches(code, fp)
          and licensing.machine_matches(code.replace("-", "").lower(), fp))
    check("کد دستگاه رایانهٔ دیگر نمی‌خواند",
          not licensing.machine_matches(licensing.machine_code("b" * 64), fp))

    bound = licensing.issue_license(priv, customer="مقید به دستگاه", machine=code)
    check("لایسنس مقید روی همان دستگاه معتبر است",
          licensing.verify_license(bound["key"], pub, fp)["valid"])
    r = licensing.verify_license(bound["key"], pub, "b" * 64)
    check("لایسنس مقید روی دستگاه دیگر معتبر نیست",
          not r["valid"] and r["reason"] == "machine")
    check("لایسنس مقید با اثر انگشت کامل هم پذیرفته می‌شود",
          licensing.verify_license(bound["key"], pub, fp)["valid"])

    today = jdate.today_str()
    expired = licensing.issue_license(priv, customer="منقضی", months=1)
    later = licensing._add_months(*[int(x) for x in today.split("/")], 2)
    r = licensing.verify_license(expired["key"], pub, "*", today=later)
    check("لایسنس منقضی‌شده رد می‌شود", not r["valid"] and r["reason"] == "expired")

    future = licensing.issue_license(priv, customer="آینده",
                                     months=12, today=licensing._add_months(
                                         *[int(x) for x in today.split("/")], 1))
    r = licensing.verify_license(future["key"], pub, "*", today=today)
    check("لایسنس با تاریخ صدور آینده رد می‌شود",
          not r["valid"] and r["reason"] == "not_yet")

    # این موارد با کلید خصوصی ریشه «امضای درست» می‌گیرند تا بررسی شوند؛
    # بدون امضای معتبر، پیش از هر چیزی درِ تشخیص دست‌کاری بسته می‌شود.
    real_priv = root_private_bytes()
    real_pub = licensing.public_key_from_private(real_priv)
    stored_pub = licensing.read_key(os.path.join(
        ROOT, "app", "license_keys", "root_public.key"))
    check("کلید عمومی همراه برنامه با کلید خصوصی می‌خواند",
          stored_pub == real_pub)

    def signed(payload):
        return licensing.encode_license(
            payload, licensing.sign_payload(payload, real_priv))

    payload, _ = licensing.decode_license(expired["key"])
    payload["expires"] = "خودمانی"
    r = licensing.verify_license(signed(payload), real_pub, "*")
    check("تاریخ انقضای نامعتبر رد می‌شود",
          not r["valid"] and r["reason"] == "expired", r["reason"])

    payload, _ = licensing.decode_license(expired["key"])
    payload["app"] = "برنامه-دیگر"
    r = licensing.verify_license(signed(payload), real_pub, "*")
    check("لایسنس برنامهٔ دیگر رد می‌شود",
          not r["valid"] and r["reason"] == "app", r["reason"])

    payload, _ = licensing.decode_license(expired["key"])
    payload["v"] = licensing.LICENSE_VERSION + 5
    r = licensing.verify_license(signed(payload), real_pub, "*")
    check("لایسنس نسخهٔ جدیدتر رد می‌شود",
          not r["valid"] and r["reason"] == "version", r["reason"])

    payload, _ = licensing.decode_license(expired["key"])
    payload["machine"] = "d" * 64
    r = licensing.verify_license(signed(payload), real_pub, "e" * 64)
    check("قید دستگاه در لایسنس امضاشده اعمال می‌شود",
          not r["valid"] and r["reason"] == "machine", r["reason"])


def test_clock_guard(tmp):
    print("\n[۴] نگهبان عقب‌بردن ساعت و دست‌کاری وضعیت")
    folder = os.path.join(tmp, "clock")
    os.makedirs(folder, exist_ok=True)
    fp = "c" * 64
    today = jdate.today_str()
    licensing.write_state(folder, fp, today)
    check("وضعیت سالم، دست‌کاری‌شده تشخیص داده نمی‌شود",
          not licensing.clock_rolled_back(folder, fp, today))
    yesterday = licensing._add_months(*[int(x) for x in today.split("/")], -1)
    check("عقب بردن ساعت تشخیص داده می‌شود",
          licensing.clock_rolled_back(folder, fp, yesterday))

    future = licensing._add_months(*[int(x) for x in today.split("/")], 3)
    licensing.write_state(folder, fp, future)
    check("اجرای بعدی با تاریخ جلوتر مجاز است",
          not licensing.clock_rolled_back(folder, fp, future))

    with open(os.path.join(folder, "license_state.json"), encoding="utf-8") as f:
        data = json.load(f)
    data["last_seen"] = yesterday
    with open(os.path.join(folder, "license_state.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    check("وضعیت دست‌کاری‌شده (بدون امضای معتبر) شناسایی می‌شود",
          licensing.clock_rolled_back(folder, fp, yesterday))


# ------------------------------------------------------------------ HTTP
def root_private_bytes():
    """بایت خام کلید خصوصی ریشه (نزد فروشنده، در app/license_keys)."""
    path = os.path.join(ROOT, "app", "license_keys", "root_private.key")
    raw = licensing.read_key(path)
    if not raw:
        raise SystemExit(
            "کلید خصوصی ریشه پیدا نشد: {}\n"
            "این آزمون زنجیرهٔ امضای واقعی را می‌سنجد. در نسخهٔ تازه‌ساخته‌شده "
            "با «python tools/make_license_keys.py» یک جفت‌کلید بسازید "
            "(یا کلید خصوصی فروشنده را همان‌جا بگذارید).".format(path))
    return raw



def make(mode, folder):
    os.makedirs(folder, exist_ok=True)
    app = create_app(os.path.join(folder, "hesabdari.db"), mode=mode, folder=folder)
    app.config["TESTING"] = True
    return app, app.test_client()


def test_http_flow(tmp):
    print("\n[۵] جریان کامل: دروازهٔ نسخهٔ کاربری ← صدور در نسخهٔ مدیر ← فعال‌سازی")
    ufolder = os.path.join(tmp, "user")
    afolder = os.path.join(tmp, "admin")
    user, cu = make(MODE_USER, ufolder)
    admin, ca = make(MODE_ADMIN, afolder)

    r = cu.get("/api/dashboard")
    check("در نسخهٔ کاربری، API داده بدون لایسنس بسته است",
          r.status_code == 403 and r.get_json().get("license_required") is True)
    r = cu.get("/api/license")
    info = r.get_json()["data"]
    check("وضعیت لایسنس بدون ورود هم خوانده می‌شود", r.status_code == 200)
    check("دلیل، «نصب‌نشده» است", info["reason"] == "missing", info.get("message"))
    check("کد دستگاه نمایش داده می‌شود", len(info["machine_code"]) == 24, info["machine_code"])
    check("نسخهٔ کاربری لایسنس را «لازم» می‌داند", info["required"] is True)
    check("نسخهٔ کاربری کلید صدور ندارد", info["can_issue"] is False)

    r = cu.post("/api/login", json={"username": "admin", "password": "admin"})
    check("ورود در حالت فعال‌نشده هم ممکن است (برای دیدن صفحهٔ فعال‌سازی)",
          r.status_code == 200)
    r = cu.get("/api/parties")
    check("پس از ورود ولی بدون لایسنس، داده‌ها هنوز بسته است", r.status_code == 403)
    r = cu.post("/api/license/issue", json={"customer": "نفوذی"})
    check("نسخهٔ کاربری نمی‌تواند لایسنس صادر کند",
          r.status_code in (403, 404) or not r.get_json().get("ok"))

    # صدور در نسخهٔ مدیر
    r = ca.post("/api/login", json={"username": "admin", "password": "admin"})
    check("ورود در نسخهٔ مدیر", r.status_code == 200)
    r = ca.get("/api/dashboard")
    check("نسخهٔ مدیر بدون لایسنس کار می‌کند", r.status_code == 200)
    r = ca.post("/api/license/issue", json={
        "customer": "باتری رضایی", "edition": "premium", "seats": 3, "months": 12})
    issued = r.get_json()["data"]
    check("صدور لایسنس موفق است", r.status_code == 200 and "SABA1." in issued["key"])
    check("رکورد لایسنس ذخیره شده است",
          len(ca.get("/api/license/manage").get_json()["data"]["issued"]) == 1)
    r = ca.get("/api/license/issued/{}".format(issued["id"]))
    check("دانلود فایل .key کار می‌کند",
          r.status_code == 200 and b"payload" in r.data)

    # فعال‌سازی در نسخهٔ کاربری
    r = cu.post("/api/license/activate", json={"key": issued["key"]})
    check("فعال‌سازی با لایسنس معتبر موفق است", r.status_code == 200, r.get_json())
    check("پس از فعال‌سازی، داده‌ها باز می‌شود",
          cu.get("/api/parties").status_code == 200)
    check("نسخهٔ پرمیوم گزارش‌های پیشرفته را باز می‌کند",
          cu.get("/api/reports/trial-balance").status_code == 200)
    check("وضعیت لایسنس «معتبر» است",
          cu.get("/api/license").get_json()["data"]["valid"] is True)

    # متن دست‌کاری‌شده
    payload, sig = licensing.decode_license(issued["key"])
    payload["seats"] = 99
    r = cu.post("/api/license/activate",
                json={"key": licensing.encode_license(payload, sig)})
    check("فعال‌سازی با متن دست‌کاری‌شده رد می‌شود", r.status_code == 400)
    check("لایسنس معتبر قبلی پس از تلاش ناموفق پاک نمی‌شود",
          cu.get("/api/parties").status_code == 200)

    # لایسنس مقید به رایانهٔ دیگر
    priv = root_private_bytes()
    check("کلید خصوصی ریشه در دسترس است (نسخهٔ مدیر)", len(priv) == 32)
    other = licensing.issue_license(priv, customer="رایانهٔ دیگر", machine="b" * 64)
    r = cu.post("/api/license/activate", json={"key": other["key"]})
    check("فعال‌سازی لایسنس رایانهٔ دیگر رد می‌شود",
          r.status_code == 400 and "رایانه" in r.get_json()["error"])

    # نسخهٔ پایه: قابلیت‌های پرمیوم قفل است
    base = ca.post("/api/license/issue", json={"customer": "نسخهٔ پایه",
                                               "edition": "base", "seats": 1}).get_json()["data"]
    bfolder = os.path.join(tmp, "base")
    _base_app, cb = make(MODE_USER, bfolder)
    check("فعال‌سازی لایسنس پایه", cb.post("/api/license/activate",
                                        json={"key": base["key"]}).status_code == 200)
    cb.post("/api/login", json={"username": "admin", "password": "admin"})
    check("در نسخهٔ پایه، تراز آزمایشی قفل است",
          cb.get("/api/reports/trial-balance").status_code == 402)
    check("در نسخهٔ پایه، انبارها قفل است",
          cb.post("/api/warehouses", json={"name": "انبار سوم"}).status_code == 402)
    check("در نسخهٔ پایه، پشتیبان‌گیری قفل است",
          cb.get("/api/backup").status_code == 402)
    check("در نسخهٔ پایه، گردش فعالیت قفل است",
          cb.get("/api/activity").status_code == 402)
    check("بخش‌های پایه در نسخهٔ پایه باز است",
          cb.get("/api/parties").status_code == 200)
    r = cb.post("/api/users", json={"username": "u2", "password": "1234"})
    check("افزودن کاربر دوم در نسخهٔ پایه رد می‌شود (سهم کاربران)",
          r.status_code == 402, r.get_json().get("error"))


def test_accounts(tmp):
    print("\n[۶] حساب‌کاربری، نقش‌ها، قفل ورود و دسترسی‌ها")
    folder = os.path.join(tmp, "accounts")
    app, c = make(MODE_ADMIN, folder)
    c.post("/api/login", json={"username": "admin", "password": "admin"})

    r = c.post("/api/users", json={"username": "reza", "password": "reza1234",
                                   "full_name": "رضا", "role": "user",
                                   "perms": ["invoices", "reports"]})
    check("ایجاد کاربر با دسترسی مشخص", r.status_code == 200, r.get_json())
    uid = r.get_json()["data"]["id"]

    rows = c.get("/api/users").get_json()["data"]
    reza = [x for x in rows if x["username"] == "reza"][0]
    check("دسترسی‌های کاربر ذخیره و بازگردانده می‌شود",
          sorted(reza["perms"]) == ["invoices", "reports"], reza["perms"])
    check("فهرست کاربران رمز عبور را برنمی‌گرداند", "password" not in reza)
    check("سقف کاربران در پاسخ آمده است",
          c.get("/api/users").get_json().get("seats") == 100)

    r = c.post("/api/users", json={"username": "reza", "password": "x"})
    check("نام کاربری تکراری رد می‌شود", r.status_code == 400 and "قبلاً" in r.get_json()["error"])

    # ورود کاربر عادی و محدودیت‌ها
    uc = app.test_client()
    r = uc.post("/api/login", json={"username": "reza", "password": "reza1234"})
    check("کاربر عادی وارد می‌شود", r.status_code == 200)
    check("دسترسی‌های کاربر در پاسخ ورود هست",
          r.get_json()["data"]["perms"] == reza["perms"])
    check("کاربر عادی به بخش کاربران دسترسی ندارد",
          uc.get("/api/users").status_code == 403)
    check("کاربر عادی به تنظیمات دسترسی ندارد",
          uc.post("/api/settings", json={"currency": "تومان"}).status_code == 403)
    check("کاربر عادی نمی‌تواند لایسنس صادر کند",
          uc.post("/api/license/issue", json={"customer": "x"}).status_code == 403)
    check("کاربر عادی داده‌های مجاز را می‌بیند", uc.get("/api/parties").status_code == 200)

    # ویرایش: غیرفعال‌کردن و قفل
    check("غیرفعال‌کردن کاربر", c.put("/api/users/{}".format(uid),
                                    json={"active": False}).status_code == 200)
    check("کاربر غیرفعال نمی‌تواند وارد شود",
          app.test_client().post("/api/login",
                                 json={"username": "reza",
                                       "password": "reza1234"}).status_code == 401)
    c.put("/api/users/{}".format(uid), json={"active": True})

    # قفل پس از ۵ تلاش ناموفق
    for _ in range(5):
        app.test_client().post("/api/login",
                               json={"username": "reza", "password": "bad"})
    r = app.test_client().post("/api/login",
                               json={"username": "reza", "password": "reza1234"})
    check("پس از ۵ تلاش ناموفق، ورود قفل می‌شود", r.status_code == 423, r.get_json())
    locked = [x for x in c.get("/api/users").get_json()["data"]
              if x["username"] == "reza"][0]
    check("وضعیت قفل در فهرست کاربران دیده می‌شود", locked["locked"] is True)
    check("مدیر می‌تواند قفل را باز کند",
          c.put("/api/users/{}".format(uid), json={"unlock": True}).status_code == 200)
    check("پس از بازکردن قفل، ورود کار می‌کند",
          app.test_client().post("/api/login",
                                 json={"username": "reza",
                                       "password": "reza1234"}).status_code == 200)

    # محافظت از حساب مدیر اصلی
    check("حذف حساب مدیر اصلی رد می‌شود",
          c.delete("/api/users/1").status_code == 400)
    check("غیرفعال‌کردن حساب مدیر اصلی رد می‌شود",
          c.put("/api/users/1", json={"active": False}).status_code == 400)
    r = c.post("/api/users", json={"username": "boss", "password": "boss1234",
                                    "role": "admin", "perms": []})
    boss_id = r.get_json()["data"]["id"]
    bc = app.test_client()
    bc.post("/api/login", json={"username": "boss", "password": "boss1234"})
    check("مدیر دوم هم به بخش کاربران دسترسی دارد",
          bc.get("/api/users").status_code == 200)
    check("هیچ‌کس نمی‌تواند حساب خودش را حذف کند",
          bc.delete("/api/users/{}".format(boss_id)).status_code == 400)
    check("گذرواژهٔ کوتاه رد می‌شود",
          c.put("/api/users/{}".format(uid), json={"password": "12"}).status_code == 400)
    check("حذف کاربر توسط مدیر انجام می‌شود",
          c.delete("/api/users/{}".format(uid)).status_code == 200)


def main():
    tmp = tempfile.mkdtemp(prefix="saba_lic_")
    print("پوشهٔ آزمون:", tmp)
    try:
        test_rfc8032()
        test_keypair_and_license()
        test_machine_and_dates()
        test_clock_guard(tmp)
        test_http_flow(tmp)
        test_accounts(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 56)
    print("موفق: {}   ناموفق: {}".format(len(PASS), len(FAIL)))
    if FAIL:
        print("آزمون‌های ناموفق:")
        for f in FAIL:
            print("   - " + f)
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
