"""آزمون سرتاسری سرور لایسنس و بات بله (بدون تماس واقعی با شبکه).

چه چیزی بررسی می‌شود:
  * یکسان‌بودن بایت‌به‌بایت هستهٔ لایسنس این پروژه با پروژهٔ برنامه.
  * سازگاری متقابل: لایسنسی که این سرور امضا می‌کند، هستهٔ *برنامه* تأیید می‌کند.
  * جریان کامل: درخواست مشتری → پیام به مدیر → دکمه‌های تأیید → صدور لایسنس →
    تحویل خودکار به برنامه → فعال‌سازی → بررسی دوره‌ای → لغو از راه دور.
  * محافظت: غیرمدیر نمی‌تواند لایسنس صادر/لغو کند؛ لایسنس دست‌کاری‌شده رد می‌شود.
  * محدودیت نرخ درخواست.

اجرا:  python tests/test_bot.py
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(HERE)
def _find_app_dir():
    """پوشهٔ برنامه: در ریپو ریشهٔ پروژه و کنار بات «accountancy/»."""
    env = (os.environ.get("SABA_APP_DIR") or "").strip()
    if env:
        return env
    base = os.path.dirname(BOT_DIR)
    for name in ("", "accountancy", "hesab-dari"):
        path = os.path.join(base, name) if name else base
        if os.path.isfile(os.path.join(path, "app", "licensing.py")):
            return path
    return base


APP_DIR = _find_app_dir()

sys.path.insert(0, BOT_DIR)

PASS = 0
FAIL = 0
FAILURES = []


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✅ " + label)
    else:
        FAIL += 1
        FAILURES.append(label)
        print("  ❌ " + label + ("  ← " + str(extra) if extra else ""))


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


# --------------------------------------------------------------- آماده‌سازی
TMP = tempfile.mkdtemp(prefix="saba-bot-test-")
os.environ["SABA_NO_AUTOSTART"] = "1"
os.environ["SABA_BOT_DISABLE"] = "1"
os.environ["BOT_DB_PATH"] = os.path.join(TMP, "bot.db")
os.environ["BALE_BOT_TOKEN"] = "TEST:TOKEN"
os.environ["SABA_ROOT_PRIVATE_KEY"] = ""
os.environ["SABA_ROOT_PUBLIC_KEY"] = ""

import bale                                       # noqa: E402
import botlogic                                   # noqa: E402
import store as store_mod                         # noqa: E402
from config import Config                         # noqa: E402
from sabalic import jdate                         # noqa: E402
from sabalic import licensing                     # noqa: E402


def load_app_licensing():
    """هستهٔ لایسنس پروژهٔ حسابداری را زیر نامی دیگر بارگذاری می‌کند."""
    app_pkg = os.path.join(APP_DIR, "app")
    name = "saba_app_pkg"
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(app_pkg, "__init__.py"),
        submodule_search_locations=[app_pkg])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return importlib.import_module(name + ".licensing")


class FakeTransport:
    """به‌جای شبکه: پاسخ‌های آماده می‌دهد و فراخوانی‌ها را ثبت می‌کند."""

    def __init__(self):
        self.calls = []
        self.sent = []            # (chat_id, text)
        self.updates = []
        self.responses = {}

    def __call__(self, url, payload, timeout):
        method = url.rsplit("/", 1)[-1]
        self.calls.append((method, payload))
        if method == "getUpdates":
            out = self.updates
            self.updates = []
            return 200, json.dumps({"ok": True, "result": out}).encode()
        if method == "sendMessage":
            self.sent.append((payload.get("chat_id"), payload.get("text")))
        if method == "getMe":
            return 200, json.dumps({"ok": True, "result": {"username": "saba_test_bot"}}).encode()
        if method in self.responses:
            return 200, json.dumps(self.responses[method]).encode()
        return 200, json.dumps({"ok": True, "result": {"message_id": 1}}).encode()


def make_cfg(**kw):
    cfg = Config(load_env=False)
    cfg.bot_token = kw.get("token", "TEST:TOKEN")
    cfg.admin_ids = set(kw.get("admins", [555]))
    key_path = os.path.join(BOT_DIR, "keys", "root_private.key")
    if not os.path.isfile(key_path):
        raise SystemExit(
            "کلید خصوصی ریشه پیدا نشد: {}\n"
            "برای اجرا: python tools/make_license_keys.py".format(key_path))
    cfg.private_key = licensing._b64d(
        open(key_path, encoding="utf-8").read().strip())
    cfg.public_key = licensing._b64d(
        open(os.path.join(BOT_DIR, "keys", "root_public.key"), encoding="utf-8").read().strip())
    cfg.rate_limit = kw.get("rate_limit", 10000)
    cfg.default_seats = 3
    cfg.grace_days = kw.get("grace_days", 15)
    cfg.client_token = kw.get("client_token", "")
    cfg.admin_token = kw.get("admin_token", "ADMIN-SECRET-1")
    cfg.default_days = kw.get("default_days", 365)
    cfg.db_path = os.path.join(TMP, "bot.db")
    return cfg


def build():
    cfg = make_cfg()
    st = store_mod.Store(os.path.join(TMP, "bot-%d.db" % len(os.listdir(TMP))))
    transport = FakeTransport()
    api = bale.Bale(cfg.bot_token, transport=transport)
    bot = botlogic.Bot(api, st, cfg, log=lambda *a: None)
    import app as server
    flask_app = server.create_app(cfg, st, bot)
    client = flask_app.test_client()
    return cfg, st, bot, transport, client


FP = hashlib.sha256(b"machine-1").hexdigest()
FP2 = hashlib.sha256(b"machine-2").hexdigest()
CODE = licensing.machine_code(FP)


def main():
    section("۱) هستهٔ لایسنس مشترک با برنامه")
    ours = open(os.path.join(BOT_DIR, "sabalic", "licensing.py"), "rb").read()
    theirs_path = os.path.join(APP_DIR, "app", "licensing.py")
    if os.path.exists(theirs_path):
        theirs = open(theirs_path, "rb").read()
        check("licensing.py این سرور با نسخهٔ برنامه یکسان است",
              hashlib.sha256(ours).hexdigest() == hashlib.sha256(theirs).hexdigest())
    else:
        check("پروژهٔ برنامه برای بررسی یکسانی هسته پیدا شد", False, theirs_path)
    app_lic = load_app_licensing()
    cfg = make_cfg()

    # امضا در سرور، بررسی در برنامه
    out = licensing.issue_license(cfg.private_key, customer="آزمون", edition="premium",
                                  seats=3, machine=FP, months=12, lic_id="SB-TEST-0001")
    v = app_lic.verify_license(out["file"], cfg.public_key, FP, data_dir=TMP)
    check("لایسنس صادرشدهٔ سرور در هستهٔ برنامه معتبر است", v["valid"], v["message"])
    check("نسخهٔ پرمیوم و قابلیت‌ها درست منتقل می‌شود",
          v["edition"] == "premium" and "multi_warehouse" in v["features"])
    check("تعداد کاربران از لایسنس خوانده می‌شود", v["seats"] == 3)
    v2 = app_lic.verify_license(out["file"], cfg.public_key, FP2, data_dir=TMP)
    check("همان لایسنس روی دستگاه دیگر رد می‌شود",
          not v2["valid"] and v2["reason"] == "machine")
    tampered = out["key"][:-6] + ("aaaaaa" if out["key"][-6:] != "aaaaaa" else "bbbbbb")
    v3 = app_lic.verify_license(tampered, cfg.public_key, FP, data_dir=TMP)
    check("لایسنس دست‌کاری‌شده بی‌اعتبار می‌شود",
          not v3["valid"] and v3["reason"] == "signature")

    section("۲) جریان کامل فعال‌سازی از بات")
    cfg, st, bot, transport, client = build()

    r = client.post("/api/v1/request", json={
        "fingerprint": FP, "machine_code": CODE, "name": "فروشگاه باتری رضایی",
        "phone": "09120000000", "note": "دو شعبه داریم؛ روز چهارشنبه تماس بگیرید"})
    body = r.get_json()
    check("درخواست فعال‌سازی پذیرفته می‌شود", r.status_code == 200 and body["ok"],
          body)
    check("وضعیت اولیه «در انتظار» است", body.get("status") == "pending")
    req_id = body.get("request_id") or 0
    check("شمارهٔ درخواست برگردانده می‌شود", bool(req_id))
    check("توضیح (نوت) مشتری همراه درخواست ذخیره می‌شود",
          (st.request_get(req_id) or {}).get("note", "").startswith("دو شعبه"),
          (st.request_get(req_id) or {}).get("note"))
    admin_msgs = [t for (c, t) in transport.sent if c == 555]
    check("به مدیر پیام تأیید با دکمه فرستاده می‌شود",
          any("درخواست" in t for t in admin_msgs), admin_msgs)
    keys = [p.get("reply_markup") for (m, p) in transport.calls if m == "sendMessage"]
    check("دکمه‌های تأیید/رد همراه پیام مدیر هستند",
          any(isinstance(k, dict) and "inline_keyboard" in k for k in keys if k))

    st2 = client.get("/api/v1/status?fingerprint=%s" % FP).get_json()
    check("برنامه در حالت انتظار «pending» می‌گیرد", st2.get("status") == "pending", st2)

    section("۳) تأیید مدیر و صدور لایسنس")
    bot.on_callback({"id": "cb1", "from": {"id": 555}, "data": "ap:%d" % req_id,
                     "message": {"message_id": 10, "chat": {"id": 555}}})
    edits = [p for (m, p) in transport.calls if m == "editMessageText"]
    check("منوی انتخاب نسخه باز می‌شود", any("premium" in json.dumps(
        p.get("reply_markup", {}), ensure_ascii=False) or "پرمیوم" in str(p.get("text"))
        for p in edits), edits[-1] if edits else None)

    bot.on_callback({"id": "cb2", "from": {"id": 555}, "data": "ape:%d:premium" % req_id,
                     "message": {"message_id": 10, "chat": {"id": 555}}})
    edits = [p for (m, p) in transport.calls if m == "editMessageText"]
    check("انتخاب نسخهٔ پرمیوم پذیرفته می‌شود و مدت به «روز» پرسیده می‌شود",
          "apd:%d:premium:365" % req_id in json.dumps(edits[-1]["reply_markup"])
          and "روز" in str(edits[-1].get("text")))
    check("گزینه‌های مدت، روز هستند و ماه نیستند",
          all("apm:" not in str(d) for d in
              [json.dumps(edits[-1]["reply_markup"])]))

    bot.on_callback({"id": "cb3", "from": {"id": 555},
                     "data": "apd:%d:premium:365" % req_id,
                     "message": {"message_id": 10, "chat": {"id": 555}}})
    edits = [p for (m, p) in transport.calls if m == "editMessageText"]
    check("انتخاب مدت ۳۶۵ روز پذیرفته می‌شود و تعداد کاربر پرسیده می‌شود",
          "aps:%d:premium:365:3" % req_id in json.dumps(edits[-1]["reply_markup"]))

    bot.on_callback({"id": "cb4", "from": {"id": 555},
                     "data": "aps:%d:premium:365:3" % req_id,
                     "message": {"message_id": 10, "chat": {"id": 555}}})
    edits = [p for (m, p) in transport.calls if m == "editMessageText"]
    check("صدور لایسنس انجام و خلاصه به مدیر نشان داده می‌شود",
          "لایسنس صادر شد" in str(edits[-1].get("text")), edits[-1].get("text"))
    lic_rows = st.licenses()
    check("لایسنس در سرور ثبت شد", len(lic_rows) == 1)
    lic = lic_rows[0] if lic_rows else {}
    check("لایسنس به اثر انگشت همین دستگاه قید شده", lic.get("fingerprint") == FP)
    check("مدت لایسنس به روز ثبت می‌شود", int(lic.get("days") or 0) == 365,
          lic.get("days"))
    check("تعداد کاربر انتخاب‌شده در لایسنس هست", lic.get("seats") == 3)
    decided = st.request_get(req_id) or {}
    check("درخواست تأییدشده از بات مشخص می‌شود",
          decided.get("status") == "approved" and decided.get("decided_via") == "bot",
          decided)
    v = app_lic.verify_license(lic.get("key_text", ""), cfg.public_key, FP, data_dir=TMP)
    check("لایسنس صادرشده در هستهٔ برنامه هم معتبر است", v["valid"], v["message"])
    check("لایسنس با کلید عمومی ریشه همان برنامه امضا شده",
          v.get("customer") == "فروشگاه باتری رضایی")

    section("۴) تحویل خودکار به برنامه و بررسی دوره‌ای")
    res = client.get("/api/v1/status?fingerprint=%s&machine_code=%s" % (FP, CODE)).get_json()
    check("برنامه لایسنس را خودکار دریافت می‌کند", res.get("status") == "active", res)
    check("متن لایسنس تحویلی همان نسخهٔ امضاشده است",
          res.get("license", {}).get("key") == lic.get("key_text"))
    check("نام مشتری در پاسخ هست", res.get("license", {}).get("customer") ==
          "فروشگاه باتری رضایی")
    ci = client.post("/api/v1/checkin", json={"fingerprint": FP,
                                              "machine_code": CODE}).get_json()
    check("بررسی دوره‌ای «فعال» پاسخ می‌دهد", ci.get("status") == "active", ci)
    check("مهلت بی‌اتصال به برنامه اعلام می‌شود", ci.get("grace_days") == 15)

    section("۵) لغو از راه دور")
    bot.on_callback({"id": "cb5", "from": {"id": 555},
                     "data": "rv:%d" % lic["id"],
                     "message": {"message_id": 11, "chat": {"id": 555}}})
    ci = client.post("/api/v1/checkin", json={"fingerprint": FP}).get_json()
    check("پس از لغو، بررسی دوره‌ای «لغوشده» می‌دهد", ci.get("status") == "revoked", ci)
    st_res = client.get("/api/v1/status?fingerprint=%s" % FP).get_json()
    check("وضعیت برنامه هم لغو را نشان می‌دهد", st_res.get("status") == "revoked")
    check("لغو در دفتر رخدادها ثبت می‌شود",
          any(a["action"] == "revoke" for a in st.audits()))

    section("۶) نقش‌ها و محافظت‌ها")
    cfg, st, bot, transport, client = build()
    bot.on_callback({"id": "x", "from": {"id": 999}, "data": "ap:1",
                     "message": {"message_id": 1, "chat": {"id": 999}}})
    check("کاربر غیرمدیر نمی‌تواند لایسنس صادر کند",
          st.license_count() == 0 and
          any("فقط" in str(t) for (c, t) in transport.sent))
    check("امضا با کلید خصوصی جعلی/نادرست ناموفق است",
          not licensing.verify_signature({"a": 1}, "zzz", cfg.public_key))
    bad = client.post("/api/v1/request", json={"fingerprint": "کد غلط"}).get_json()
    check("اثر انگشت نامعتبر رد می‌شود", bad.get("ok") is False, bad)
    cfg2 = make_cfg(rate_limit=3)
    st2 = store_mod.Store(os.path.join(TMP, "rate.db"))
    import app as server2
    client2 = server2.create_app(cfg2, st2, bot).test_client()
    codes = [client2.post("/api/v1/request", json={"fingerprint": FP}).status_code
             for _ in range(5)]
    check("محدودیت نرخ درخواست کار می‌کند", 429 in codes, codes)
    tok_cfg = make_cfg(client_token="SECRET123")
    client3 = server2.create_app(tok_cfg, st2, bot).test_client()
    opened = client3.get("/api/v1/info").get_json()
    check("کلید اتصال برنامه بررسی می‌شود",
          opened.get("ok") is False and
          client3.get("/api/v1/info", headers={"X-Saba-Client": "SECRET123"}
                      ).get_json().get("ok") is True)

    section("۷) تأیید و رد از داخل برنامهٔ فروشنده (API مدیریت)")
    cfg, st, bot, transport, client = build()
    req = client.post("/api/v1/request", json={
        "fingerprint": FP2, "machine_code": licensing.machine_code(FP2),
        "name": "باتری‌سازی کریمی", "phone": "09121111111",
        "note": "درخواست از حساب کاربری؛ سه شعبه داریم"})
    rid = (req.get_json() or {}).get("request_id") or 0
    adm = {"X-Saba-Admin": cfg.admin_token}

    check("بدون توکن مدیر، فهرست درخواست‌ها بسته است",
          client.get("/api/v1/admin/requests").status_code == 403)
    check("با توکن نادرست هم بسته می‌ماند",
          client.get("/api/v1/admin/requests",
                     headers={"X-Saba-Admin": "WRONG"}).status_code == 403)
    listed = client.get("/api/v1/admin/requests", headers=adm).get_json()
    check("برنامهٔ فروشنده درخواست‌های در انتظار را می‌بیند",
          listed.get("ok") and any(r["id"] == rid for r in listed["requests"]),
          listed)
    mine = [r for r in listed["requests"] if r["id"] == rid][0]
    check("نوت مشتری به برنامهٔ فروشنده می‌رسد", "سه شعبه" in mine["note"], mine)
    check("گزینه‌های مدت به روز اعلام می‌شوند",
          listed.get("default_days") == 365 and 30 in listed.get("days_choices", []),
          listed.get("days_choices"))
    check("گزینه‌های تعداد کاربر اعلام می‌شوند",
          10 in listed.get("seat_choices", []), listed.get("seat_choices"))

    bad = client.post("/api/v1/admin/decide", json={"request_id": rid,
                                                    "action": "approve"})
    check("تأیید بدون توکن مدیر رد می‌شود", bad.status_code == 403, bad.get_json())
    okr = client.post("/api/v1/admin/decide", headers=adm, json={
        "request_id": rid, "action": "approve", "edition": "premium",
        "seats": 5, "days": 180, "note": "تخفیف داده شد"}).get_json()
    check("تأیید از برنامه با تعداد کاربر و روز انجام می‌شود", okr.get("ok"), okr)
    check("شناسهٔ لایسنس صادرشده برگردانده می‌شود", bool(okr.get("lic_id")))
    check("تعداد کاربر خواسته‌شده در لایسنس هست", okr.get("seats") == 5, okr)
    check("مدت به روز ثبت می‌شود", okr.get("days") == 180, okr)
    row = st.license_by_lic_id(okr.get("lic_id") or "") or {}
    v = app_lic.verify_license(row.get("key_text", ""), cfg.public_key, FP2,
                               data_dir=TMP)
    check("لایسنس صادرشده از برنامه هم در هستهٔ برنامه معتبر است",
          v["valid"], v["message"])
    check("مدت ۱۸۰ روز در بدنهٔ لایسنس درست نشسته",
          v["payload"]["expires"] == jdate.add_days(v["payload"]["issued"], 180),
          v["payload"]["expires"])
    decided = st.request_get(rid) or {}
    check("ثبت می‌شود که تأیید از برنامه بوده",
          decided.get("decided_via") == "app", decided)
    check("توضیح مدیر کنار درخواست ذخیره می‌شود",
          decided.get("decided_note") == "تخفیف داده شد", decided)
    again = client.post("/api/v1/admin/decide", headers=adm, json={
        "request_id": rid, "action": "approve"})
    check("تأیید دوبارهٔ همان درخواست پذیرفته نمی‌شود", again.status_code == 409,
          again.get_json())

    req2 = client.post("/api/v1/request", json={
        "fingerprint": hashlib.sha256(b"machine-3").hexdigest(),
        "name": "باتری مرکزی"})
    rid2 = (req2.get_json() or {}).get("request_id") or 0
    deny = client.post("/api/v1/admin/decide", headers=adm, json={
        "request_id": rid2, "action": "deny", "note": "اطلاعات ناقص"}).get_json()
    check("رد درخواست از برنامه انجام می‌شود", deny.get("ok"), deny)
    check("وضعیت درخواست رد‌شده ثبت می‌شود",
          (st.request_get(rid2) or {}).get("status") == "denied")
    check("درخواست رد‌شده در فهرست انتظار نمی‌ماند",
          not any(r["id"] == rid2 for r in
                  client.get("/api/v1/admin/requests", headers=adm
                             ).get_json()["requests"]))
    off = make_cfg(admin_token="")
    client_off = server2.create_app(off, st, bot).test_client()
    check("اگر توکن مدیر روی سرور تنظیم نشده باشد، پنل برنامه بسته است",
          client_off.get("/api/v1/admin/requests",
                         headers={"X-Saba-Admin": "ANY"}).status_code == 403)

    section("۸) پیام‌های بات و گفت‌وگوی مشتری")
    check("متن بلند به تکه‌های مجاز تقسیم می‌شود",
          all(len(p) <= 3500 for p in bale.chunks("x" * 9000)) and
          len(bale.chunks("x" * 9000)) == 3)
    cfg, st, bot, transport, client = build()
    bot.handle({"update_id": 1, "message": {"message_id": 1, "chat": {"id": 777},
                                            "text": "/activate"}})
    check("دستور فعال‌سازی مشتری، درخواست کد می‌کند",
          any("کد رایانه" in t for (c, t) in transport.sent))
    bot.handle({"update_id": 2, "message": {"message_id": 2, "chat": {"id": 777},
                                            "text": CODE.upper()}})
    check("کد دستگاه شناسایی و نام پرسیده می‌شود",
          any("نام مشتری" in t for (c, t) in transport.sent))
    bot.handle({"update_id": 3, "message": {"message_id": 3, "chat": {"id": 777},
                                            "text": "باتری‌فروشی علی"}})
    bot.handle({"update_id": 4, "message": {"message_id": 4, "chat": {"id": 777},
                                            "text": "09127770000"}})
    reqs = st.requests_pending()
    check("درخواست مشتری از راه بات ساخته می‌شود", len(reqs) == 1, reqs)
    check("دستگاه به کد کوتاه مشتری مقید می‌شود",
          reqs and reqs[0]["fingerprint"] == licensing.normalize_machine(CODE))
    check("به مدیر هم اطلاع داده می‌شود",
          any(c == 555 and "درخواست" in t for (c, t) in transport.sent))
    ac = client.get("/api/v1/status?fingerprint=%s&machine_code=%s" % (FP, CODE)
                    ).get_json()
    check("برنامه با کد کوتاه هم وضعیت درخواست خود را می‌بیند",
          ac.get("status") == "pending", ac)
    bot.handle({"update_id": 5, "message": {"message_id": 5, "chat": {"id": 777},
                                            "text": "/status"}})
    check("مشتری وضعیت درخواست خود را می‌بیند",
          any("در انتظار تأیید" in t for (c, t) in transport.sent))
    before = len(transport.sent)
    bot.handle({"update_id": 6, "message": {"message_id": 6, "chat": {"id": 777},
                                            "text": "/licenses"}})
    new_msgs = [t for (c, t) in transport.sent[before:] if c == 777]
    check("کاربر غیرمدیر دستور مدیریتی اجرا نمی‌کند",
          len(new_msgs) == 1 and "فقط برای مدیر" in new_msgs[0], new_msgs)
    before = len(transport.sent)
    bot.handle({"update_id": 7, "message": {"message_id": 7, "chat": {"id": 8888},
                                            "text": "/revoke SB-X"}})
    check("کاربر غریبه نمی‌تواند لایسنس لغو کند",
          all("فقط برای مدیر" in t or "فقط فروشنده" in t
              for (c, t) in transport.sent[before:] if c == 8888) and
          not st.licenses())

    section("۹) پیکربندی سرور")
    cfg = make_cfg()
    check("تنظیمات کامل، ایرادی ندارد", cfg.missing() == [], cfg.missing())
    bad_cfg = Config(load_env=False)
    bad_cfg.bot_token = ""
    bad_cfg.private_key = None
    bad_cfg.public_key = None
    bad_cfg.admin_ids = set()
    problems = bad_cfg.missing()
    check("نبود توکن، کلید و شناسهٔ مدیر گزارش می‌شود", len(problems) == 4, problems)
    wrong = make_cfg()
    wrong.public_key = bytes(range(32))
    check("نخواندن کلید خصوصی و عمومی گرفته می‌شود",
          any("نمی‌خوانند" in p for p in wrong.missing()), wrong.missing())

    section("۱۰) صفحهٔ وضعیت سرور")
    cfg, st, bot, transport, client = build()
    home = client.get("/")
    body = home.get_data(as_text=True)
    check("صفحهٔ اصلی سرور بدون خطای ۵۰۰ باز می‌شود",
          home.status_code == 200, home.status_code)
    check("نام محصول در صفحهٔ وضعیت دیده می‌شود",
          "<title>سرور لایسنس سیستم حسابداری Mental</title>" in body)
    check("جانگهدارهای قالب باقی نمانده و آمار واقعی پر شده است",
          "{style}" not in body and "{version}" not in body
          and "<b>1.0.0</b>" in body, body[:200])
    check("سبک صفحه سالم به مرورگر می‌رسد (درصد اضافه/جانگهدار خراب نشده)",
          "<style>" in body and "font-family:Tahoma" in body
          and "width:100%" in body and "%%" not in body)

    print("\n" + "=" * 60)
    print("موفق: {}   ناموفق: {}".format(PASS, FAIL))
    print("=" * 60)
    if FAILURES:
        print("موارد ناموفق:")
        for f in FAILURES:
            print("  - " + f)
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
