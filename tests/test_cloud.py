"""آزمون لایسنس آنلاین و مدیریت پشتیبان‌ها (سرتاسری، روی HTTP واقعی).

سرور لایسنس (پروژهٔ bot-hesab-dari) در همین پروسه بالا می‌آید و برنامهٔ
حسابداری واقعاً از راه HTTP با آن گفت‌وگو می‌کند؛ اما پیام‌های بات بله به
یک «لایهٔ انتقال ساختگی» می‌رود تا هیچ تماسی با شبکهٔ بیرون نباشد.

اجرا:  python tests/test_cloud.py
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
def _find_bot_dir():
    """پوشهٔ سرور لایسنس/بات: در ریپو «bot/» و کنار پروژه «accountancybot/»."""
    env = (os.environ.get("SABA_BOT_DIR") or "").strip()
    if env:
        return env
    base = os.path.dirname(APP_ROOT)
    for name in ("bot", "accountancybot", "bot-hesab-dari"):
        path = os.path.join(base, name)
        if os.path.isfile(os.path.join(path, "app.py")):
            return path
    return os.path.join(base, "bot")


BOT_DIR = _find_bot_dir()

sys.path.insert(0, APP_ROOT)

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


TMP = tempfile.mkdtemp(prefix="saba-cloud-test-")
DATA = os.path.join(TMP, "data")
INSTALL = os.path.join(TMP, "install")
os.makedirs(DATA, exist_ok=True)
os.makedirs(INSTALL, exist_ok=True)

os.environ["SABA_DATA_DIR"] = DATA
os.environ["SABA_BACKUP_DIR"] = os.path.join(TMP, "backups")
os.environ["SABA_NO_CHECKIN"] = "1"
os.environ["SABA_BOT_DISABLE"] = "1"
os.environ["SABA_NO_AUTOSTART"] = "1"
os.environ["BOT_DB_PATH"] = os.path.join(TMP, "bot.db")
os.environ["BALE_BOT_TOKEN"] = "TEST:TOKEN"
os.environ["ADMIN_CHAT_IDS"] = "555"
os.environ.pop("BALE_BOT_TOKEN_REAL", None)

from app import install                       # noqa: E402
from app import jdate                         # noqa: E402
from app import licensing                     # noqa: E402
from app.server import create_app             # noqa: E402


# ------------------------------------------------------------ سرور لایسنس
class FakeTransport:
    """به‌جای شبکهٔ بله: فراخوانی‌ها را ثبت می‌کند."""

    def __init__(self):
        self.sent = []
        self.calls = []

    def __call__(self, url, payload, timeout):
        self.calls.append((url.rsplit("/", 1)[-1], payload))
        if url.rsplit("/", 1)[-1] == "sendMessage":
            self.sent.append((payload.get("chat_id"), payload.get("text")))
        return 200, json.dumps({"ok": True, "result": {"message_id": 1}}).encode()


def load_bot_server():
    sys.path.insert(0, BOT_DIR)
    spec = importlib.util.spec_from_file_location(
        "saba_bot_server", os.path.join(BOT_DIR, "app.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["saba_bot_server"] = module
    spec.loader.exec_module(module)
    return module


def start_http(flask_app):
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "http://127.0.0.1:{}".format(server.server_port)


def main():
    section("۱) مسیرهای نصب/داده/پشتیبان (منطق اینستالر)")
    install.install_dir = lambda: INSTALL
    install.clear_cache()
    with open(os.path.join(INSTALL, "data-dir.txt"), "w", encoding="utf-8") as f:
        f.write(os.path.join(TMP, "data-from-installer"))
    with open(os.path.join(INSTALL, "backup-dir.txt"), "w", encoding="utf-8") as f:
        f.write(os.path.join(TMP, "backups-from-installer"))
    with open(os.path.join(INSTALL, "license-server.txt"), "w",
              encoding="utf-8") as f:
        f.write("https://license.example.com/")
    os.environ.pop("SABA_DATA_DIR", None)
    os.environ.pop("SABA_BACKUP_DIR", None)
    install.clear_cache()
    check("پوشهٔ داده از فایل اینستالر خوانده می‌شود",
          install.data_dir() == os.path.join(TMP, "data-from-installer"),
          install.data_dir())
    check("پوشهٔ پشتیبان از فایل اینستالر خوانده می‌شود",
          install.backup_dir() == os.path.join(TMP, "backups-from-installer"))
    check("تنظیم کاربر بر فایل اینستالر اولویت دارد",
          install.backup_dir(os.path.join(TMP, "from-user")) ==
          os.path.join(TMP, "from-user"))
    check("نشانی سرور از فایل اینستالر خوانده و «/» انتهایی حذف می‌شود",
          install.license_server() == "https://license.example.com",
          install.license_server())
    os.environ["SABA_LICENSE_SERVER"] = "http://127.0.0.1:1"
    install.clear_cache()
    check("متغیر محیطی بر همه اولویت دارد",
          install.license_server() == "http://127.0.0.1:1")
    os.environ.pop("SABA_LICENSE_SERVER")

    section("۲) بالا آوردن سرور لایسنس و بات")
    os.environ["BALE_BOT_TOKEN"] = "TEST:TOKEN"
    os.environ["ADMIN_CHAT_IDS"] = "555"
    os.environ["SABA_DATA_DIR"] = DATA
    os.environ["SABA_BACKUP_DIR"] = os.path.join(TMP, "backups")
    install.clear_cache()
    bot_module = load_bot_server()
    transport = FakeTransport()
    sys.path.insert(0, BOT_DIR)
    import bale as bale_module                     # noqa: E402
    bot_module.app.bot.api = bale_module.Bale("TEST:TOKEN", transport=transport)
    server, base_url = start_http(bot_module.app)
    bot = bot_module.app.bot
    store = bot_module.app.store
    check("سرور لایسنس بالا آمد", base_url.startswith("http://127.0.0.1:"))
    import urllib.request
    with urllib.request.urlopen(base_url + "/health", timeout=5) as resp:
        health = json.loads(resp.read().decode())
    check("نشانی /health پاسخ ok می‌دهد", health.get("ok") is True, health)

    section("۳) فعال‌سازی آنلاین: درخواست مشتری")
    os.environ["SABA_LICENSE_SERVER"] = base_url
    install.clear_cache()
    app = create_app(db_path=os.path.join(DATA, "hesabdari.db"), mode="user",
                     folder=DATA)
    client = app.test_client()
    lic = app.license

    cloud = client.get("/api/license/cloud").get_json()["data"]
    check("برنامه سرور لایسنس را می‌بیند", cloud["cloud"]["configured"] is True,
          cloud["cloud"])
    before = client.get("/api/license").get_json()["data"]
    check("بدون لایسنس، برنامه «فعال‌نشده» است",
          before["valid"] is False and before["reason"] == "missing")

    r = client.post("/api/license/cloud/request",
                    json={"name": "باتری‌فروشی نمونه", "phone": "09121112233",
                          "note": "دو شعبه داریم"})
    body = r.get_json()
    check("درخواست فعال‌سازی آنلاین ثبت می‌شود", r.status_code == 200 and body["ok"],
          body)
    check("وضعیت برگشتی «در انتظار» است", body["data"]["status"] == "pending",
          body["data"])
    check("فروشنده در بات بله پیام تأیید می‌گیرد",
          any(c == 555 and "درخواست" in str(t) for (c, t) in transport.sent))
    reqs = store.requests_pending()
    check("درخواست در سرور ثبت شده است", len(reqs) == 1, reqs)
    check("لایسنس با اثر انگشت همین رایانه قید می‌شود",
          reqs and reqs[0]["fingerprint"] == lic.fingerprint)
    check("توضیح مشتری در درخواست سرور ذخیره می‌شود",
          reqs and reqs[0]["note"] == "دو شعبه داریم",
          reqs[0]["note"] if reqs else None)

    section("۴) تأیید فروشنده و دریافت خودکار لایسنس")
    rid = reqs[0]["id"]
    bot.on_callback({"id": "c1", "from": {"id": 555}, "data": "ap:%d" % rid,
                     "message": {"message_id": 1, "chat": {"id": 555}}})
    bot.on_callback({"id": "c2", "from": {"id": 555},
                     "data": "ape:%d:premium" % rid,
                     "message": {"message_id": 1, "chat": {"id": 555}}})
    bot.on_callback({"id": "c3", "from": {"id": 555},
                     "data": "apd:%d:premium:365" % rid,
                     "message": {"message_id": 1, "chat": {"id": 555}}})
    bot.on_callback({"id": "c4", "from": {"id": 555},
                     "data": "aps:%d:premium:365:3" % rid,
                     "message": {"message_id": 1, "chat": {"id": 555}}})
    check("لایسنس در سرور صادر شد", store.license_count() == 1)
    check("مدت تأییدشده به روز ثبت شد",
          int(store.licenses()[0].get("days") or 0) == 365)

    poll = client.post("/api/license/cloud/poll").get_json()["data"]
    check("برنامه لایسنس را خودکار دریافت می‌کند", poll["status"] == "active", poll)
    check("فایل لایسنس روی همین رایانه نوشته شد",
          os.path.exists(os.path.join(DATA, "license.key")))
    now = client.get("/api/license").get_json()["data"]
    check("لایسنس محلی معتبر است", now["valid"] is True, now["message"])
    check("لایسنس آنلاین علامت‌دار است", now["online"] is True)
    check("قابلیت‌های پرمیوم باز است", "multi_warehouse" in now["features"])
    check("سقف کاربران از لایسنس می‌آید", now["seats"] == 3)
    gate = client.get("/api/dashboard")
    check("دروازهٔ لایسنس دیگر جلوی API را نمی‌گیرد", gate.status_code == 401, gate.status_code)
    check("وضعیت بررسی آنلاین تازه است",
          app.license.cloud_enforcement()["ok"] is True)

    section("۴-۲) تأیید و رد درخواست از داخل برنامهٔ فروشنده")
    # پنل فروشنده: با توکن مدیر (که فقط اینستالر نسخهٔ فروشنده می‌نویسد).
    os.environ["SABA_ADMIN_TOKEN"] = "ADMIN-TOKEN-1"
    bot_module.app.cfg.admin_token = "ADMIN-TOKEN-1"
    install.clear_cache()
    # روی یک رایانه، اثر انگشت سیستمی همهٔ نصب‌ها یکسان است؛ برای آزمودن چند
    # مشتری جدا، شناسه را از پوشهٔ داده می‌گیریم (همان مسیر fallback خودِ کد).
    real_fp = licensing._windows_fingerprint
    licensing._windows_fingerprint = lambda: ()
    seller_dir = os.path.join(TMP, "seller")
    os.makedirs(seller_dir, exist_ok=True)
    seller = create_app(db_path=os.path.join(DATA, "seller.db"), mode="admin",
                        folder=seller_dir)
    seller_client = seller.test_client()
    login = seller_client.post("/api/login",
                               json={"username": "admin", "password": "admin"})
    check("ورود مدیر به برنامهٔ فروشنده", login.status_code == 200, login.get_json())
    sc = seller_client.get("/api/license/cloud").get_json()["data"]
    check("پنل مدیریت درخواست‌ها در نسخهٔ فروشنده باز است",
          sc.get("admin_panel") is True, sc)
    check("توکن مدیر به رابط کاربری نمی‌رود",
          "admin" not in (sc.get("settings") or {}) and
          sc.get("has_admin_token") is True, sc.get("settings"))

    cust_dir = os.path.join(TMP, "customer2")
    os.makedirs(cust_dir, exist_ok=True)
    cust = create_app(db_path=os.path.join(DATA, "cust2.db"), mode="user",
                      folder=cust_dir)
    cust_client = cust.test_client()
    asked = cust_client.post("/api/license/cloud/request", json={
        "name": "باتری‌سازی کریمی", "phone": "09120000000",
        "note": "لطفاً پنج کاربر"}).get_json()
    check("درخواست مشتری دوم ثبت می‌شود", asked.get("ok"), asked)
    rid2 = asked["data"]["request_id"]

    check("نسخهٔ مشتری به فهرست درخواست‌ها دسترسی ندارد",
          cust_client.get("/api/license/requests").status_code in (401, 403))
    listed = seller_client.get("/api/license/requests").get_json()["data"]
    mine = [r for r in listed.get("requests", []) if r["id"] == rid2]
    check("درخواست تازه در برنامهٔ فروشنده دیده می‌شود", len(mine) == 1, listed)
    check("توضیح مشتری به فروشنده می‌رسد",
          mine and mine[0]["note"] == "لطفاً پنج کاربر",
          mine[0] if mine else None)
    check("گزینه‌های تعداد کاربر و روز اعلام می‌شوند",
          5 in (listed.get("seat_choices") or []) and
          30 in (listed.get("days_choices") or []), listed.get("days_choices"))

    dec = seller_client.post("/api/license/requests/%d/decide" % rid2, json={
        "action": "approve", "edition": "premium", "seats": 4, "days": 90,
        "note": "تخفیف داده شد"}).get_json()
    check("تأیید از داخل برنامه انجام می‌شود", dec.get("ok"), dec)
    check("تعداد کاربر و روز در لایسنس می‌نشیند",
          dec["data"].get("seats") == 4 and dec["data"].get("days") == 90,
          dec.get("data"))
    poll = cust_client.post("/api/license/cloud/poll").get_json()["data"]
    check("برنامهٔ مشتری خودکار فعال می‌شود", poll.get("status") == "active", poll)
    now2 = cust_client.get("/api/license").get_json()["data"]
    check("لایسنس نصب‌شده همان تعداد کاربر را دارد", now2.get("seats") == 4, now2)
    check("مدت ۹۰ روز در انقضای لایسنس دیده می‌شود",
          now2.get("expires") == jdate.add_days(now2.get("issued"), 90),
          (now2.get("issued"), now2.get("expires")))
    check("ثبت می‌شود که تأیید از برنامه بوده",
          (store.request_get(rid2) or {}).get("decided_via") == "app")
    check("توضیح فروشنده کنار درخواست ذخیره می‌شود",
          (store.request_get(rid2) or {}).get("decided_note") == "تخفیف داده شد")
    check("درخواست تأییدشده از فهرست انتظار می‌رود",
          not any(r["id"] == rid2 for r in seller_client.get(
              "/api/license/requests").get_json()["data"]["requests"]))

    third_dir = os.path.join(TMP, "customer3")
    os.makedirs(third_dir, exist_ok=True)
    third = create_app(db_path=os.path.join(DATA, "cust3.db"), mode="user",
                       folder=third_dir)
    third_client = third.test_client()
    asked3 = third_client.post("/api/license/cloud/request",
                               json={"name": "باتری مرکزی"}).get_json()
    rid3 = asked3["data"]["request_id"]
    deny = seller_client.post("/api/license/requests/%d/decide" % rid3,
                              json={"action": "deny",
                                    "note": "اطلاعات ناقص"}).get_json()
    check("رد درخواست از داخل برنامه انجام می‌شود", deny.get("ok"), deny)
    denied = third_client.post("/api/license/cloud/poll").get_json()["data"]
    check("مشتری رد‌شدن درخواست را می‌بیند", denied.get("status") == "denied",
          denied)
    check("درخواست رد‌شده وضعیت درست دارد",
          (store.request_get(rid3) or {}).get("status") == "denied")
    licensing._windows_fingerprint = real_fp

    section("۵) لغو از راه دور و مهلت بی‌اتصال")
    # لایسنس همین مشتری (نه تازه‌ترین رکورد سرور؛ در بخش ۴-۲ چند تا صادر شد)
    lic_row = store.licenses_of_fingerprint(lic.fingerprint)[0]
    bot.on_callback({"id": "c5", "from": {"id": 555},
                     "data": "rv:%d" % lic_row["id"],
                     "message": {"message_id": 2, "chat": {"id": 555}}})
    client.post("/api/license/cloud/poll")
    revoked = client.get("/api/license").get_json()["data"]
    check("پس از لغو، برنامه قفل می‌شود",
          revoked["valid"] is False and revoked["reason"] == "revoked",
          revoked["reason"])
    blocked = client.get("/api/dashboard")
    check("دروازهٔ API هم قفل می‌شود", blocked.status_code == 403, blocked.status_code)

    # لغو را برمی‌گردانیم (صدور لایسنس تازه) تا مهلت را بیازماییم
    store._exec("UPDATE licenses SET revoked=0 WHERE id=?", (lic_row["id"],))
    # همان دستگاهی که لغو شد باید آزاد شود (نه اولین دستگاه سرور)
    store.device_set_status(lic_row["device_id"], "active")
    client.post("/api/license/cloud/poll")
    check("پس از رفع لغو، لایسنس باز معتبر می‌شود",
          client.get("/api/license").get_json()["data"]["valid"] is True)

    lic.cloud_write(at="2020-01-01 00:00:00", source="cloud")
    stale = client.get("/api/license").get_json()["data"]
    check("لایسنس آنلاین که مدت‌ها بررسی نشده قفل می‌شود",
          stale["valid"] is False and stale["reason"] == "stale", stale["reason"])
    client.post("/api/license/cloud/poll")
    check("بررسی دوباره مشکل را رفع می‌کند",
          client.get("/api/license").get_json()["data"]["valid"] is True)

    # دست‌کاری فایل وضعیت باید گرفته شود
    state_path = os.path.join(DATA, "cloud_state.json")
    with open(state_path, encoding="utf-8") as f:
        raw = json.load(f)
    raw["at"] = "2020-01-01 00:00:00"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False)
    tampered = client.get("/api/license").get_json()["data"]
    check("دست‌کاری فایل وضعیت آنلاین گرفته می‌شود",
          tampered["valid"] is False and tampered["reason"] == "cloud_state",
          tampered["reason"])
    client.post("/api/license/cloud/poll")
    check("پس از بررسی تازه، دست‌کاری پاک می‌شود",
          client.get("/api/license").get_json()["data"]["valid"] is True)

    section("۶) لایسنس دستی (آفلاین) به اینترنت نیاز ندارد")
    key_path = os.path.join(APP_ROOT, "app", "license_keys", "root_private.key")
    if not os.path.isfile(key_path):
        raise SystemExit(
            "کلید خصوصی ریشه پیدا نشد: {}\n"
            "برای اجرا: python tools/make_license_keys.py".format(key_path))
    ROOT_PRIVATE = licensing._b64d(
        open(key_path, encoding="utf-8").read().strip())

    def key_generator(app_obj, customer="مشتری آفلاین", lic_id="SB-OFF-0001"):
        """لایسنس دستی مقید به همان رایانه (برای آزمون‌های مستقل)."""
        return licensing.issue_license(
            ROOT_PRIVATE, customer=customer, edition="premium", seats=2,
            machine=app_obj.license.fingerprint, months=12, lic_id=lic_id)["key"]

    key = key_generator(app, customer="مشتری آفلاین")
    offline_dir = os.path.join(TMP, "offline")
    os.makedirs(offline_dir, exist_ok=True)
    app2 = create_app(db_path=os.path.join(offline_dir, "h.db"), mode="user",
                      folder=offline_dir)
    c2 = app2.test_client()
    res = c2.post("/api/license/activate", json={"key": key}).get_json()
    check("لایسنس دستی فعال می‌شود", res["ok"] is True, res)
    off = c2.get("/api/license").get_json()["data"]
    check("لایسنس دستی معتبر است", off["valid"] is True, off["message"])
    check("لایسنس دستی به بررسی اینترنتی گره نمی‌خورد", off["online"] is False)
    os.environ["SABA_LICENSE_SERVER"] = "http://127.0.0.1:9"
    install.clear_cache()
    check("حتی با سرور در دسترس‌نبودن، لایسنس دستی کار می‌کند",
          c2.get("/api/license").get_json()["data"]["valid"] is True)
    os.environ["SABA_LICENSE_SERVER"] = base_url
    install.clear_cache()

    section("۷) مدیریت پشتیبان‌ها")
    # متغیر محیطی بالاترین اولویت را دارد؛ برای آزمون مسیر عادی خاموشش می‌کنیم
    os.environ.pop("SABA_BACKUP_DIR", None)
    install.clear_cache()
    login = client.post("/api/login", json={"username": "admin", "password": "admin"})
    check("ورود مدیر انجام می‌شود", login.status_code == 200, login.get_json())

    info = client.get("/api/backups").get_json()["data"]
    check("پوشهٔ پشتیبان از فایل اینستالر می‌آید",
          info["dir"] == os.path.join(TMP, "backups-from-installer"), info["dir"])
    made = client.post("/api/backups", json={"create": True}).get_json()["data"]
    check("پشتیبان دستی ساخته می‌شود", bool(made["created"]), made)
    check("فایل پشتیبان روی دیسک هست",
          os.path.isfile(os.path.join(info["dir"], made["created"])))
    check("فهرست پشتیبان‌ها آن را نشان می‌دهد",
          any(f["name"] == made["created"] for f in made["files"]))
    dl = client.get("/api/backups/" + made["created"])
    check("دانلود پشتیبان کار می‌کند",
          dl.status_code == 200 and dl.data[:16].startswith(b"SQLite format 3"))
    dl.close()                       # در ویندوز فایل باز‌مانده قابل حذف نیست
    auto = app.auto_backup()
    check("پشتیبان خودکار (هنگام بالا آمدن برنامه) ساخته می‌شود", bool(auto), auto)
    check("پشتیبان خودکار در فهرست با نوع auto می‌آید",
          any(f["kind"] == "auto" for f in client.get("/api/backups")
              .get_json()["data"]["files"]))

    new_dir = os.path.join(TMP, "new-backups")
    moved = client.post("/api/backups", json={"dir": new_dir, "create": True}
                        ).get_json()["data"]
    check("پوشهٔ پشتیبان از رابط کاربری تغییر می‌کند",
          moved["dir"] == new_dir and os.path.isdir(new_dir), moved["dir"])
    check("پشتیبان تازه در پوشهٔ نو ساخته شد",
          os.path.isfile(os.path.join(new_dir, moved["created"])))
    client.post("/api/backups", json={"dir": info["dir"], "keep": 2, "auto": False})
    for _ in range(3):
        client.post("/api/backups", json={"create": True})
    listed = client.get("/api/backups").get_json()["data"]
    check("تعداد نسخه‌های نگه‌داشته‌شده رعایت می‌شود", len(listed["files"]) <= 2,
          listed["files"])
    check("خاموش‌کردن پشتیبان خودکار ذخیره می‌شود", listed["auto"] in ("0", False),
          listed["auto"])

    victim = listed["files"][0]["name"]
    trav = client.delete("/api/backups/..%2F..%2Fevil.db").status_code
    check("نام نامعتبر (حملهٔ مسیر) رد می‌شود", trav in (400, 404, 405), trav)
    dele = client.delete("/api/backups/" + victim)
    check("حذف پشتیبان کار می‌کند", dele.status_code == 200,
          (dele.status_code, dele.get_json()))
    check("پس از حذف، در فهرست نیست",
          all(f["name"] != victim for f in client.get("/api/backups")
              .get_json()["data"]["files"]))
    check("پس از حذف، فایل از دیسک رفته است",
          not os.path.isfile(os.path.join(listed["dir"], victim)))

    section("۸) خطاهای سرور لایسنس")
    os.environ["SABA_LICENSE_SERVER"] = "http://127.0.0.1:9"
    install.clear_cache()
    bad = client.post("/api/license/cloud/poll").get_json()
    check("نبود دسترسی به سرور، خطای روشن می‌دهد",
          bad["ok"] is True and bad["data"]["checked"] is False and
          "برقرار نشد" in bad["data"]["message"], bad)
    check("پیام خطا در وضعیت ذخیره می‌شود", bool(lic.cloud_info()["error"]))
    check("در نبود شبکه، لایسنس فعلی باطل نمی‌شود", lic.info()["valid"] is True)
    os.environ["SABA_LICENSE_SERVER"] = base_url
    install.clear_cache()

    section("۹) بازگرداندن پشتیبان")
    guest_dir = os.path.join(TMP, "guest")
    guest = create_app(db_path=os.path.join(guest_dir, "h.db"), mode="user",
                       folder=guest_dir)
    gc = guest.test_client()
    check("بازگرداندن بدون ورود ممکن نیست",
          gc.post("/api/backups/restore", json={"name": "x.db"}).status_code
          in (401, 403))
    gc.post("/api/license/activate", json={"key": key_generator(guest)})
    gc.post("/api/login", json={"username": "admin", "password": "admin"})
    fresh = gc.post("/api/backups", json={"create": True}).get_json()["data"]
    restore = gc.post("/api/backups/restore", json={"name": fresh["created"]})
    body = restore.get_json()
    check("بازگرداندن پشتیبان انجام می‌شود",
          restore.status_code == 200 and body["ok"], body)
    check("پیش از بازگرداندن، نسخهٔ امن گرفته می‌شود",
          "before-restore" in (body.get("data") or {}).get("safety", ""))
    check("فایل بازیابی‌شده همان پایگاه‌داده است",
          os.path.getsize(os.path.join(guest_dir, "h.db")) ==
          os.path.getsize(os.path.join(fresh["dir"], fresh["created"])))

    section("۱۰) خطای سرور نامعتبر")
    os.environ["SABA_LICENSE_SERVER"] = "not-a-url"
    install.clear_cache()
    wrong = client.post("/api/license/cloud/request",
                        json={"name": "x", "phone": "1"}).get_json()
    check("نشانی نامعتبر سرور، خطای روشن می‌دهد",
          wrong["ok"] is False and "http://" in str(wrong.get("error")), wrong)
    os.environ["SABA_LICENSE_SERVER"] = base_url
    install.clear_cache()

    section("۱۱) تنظیم نشانی سرور از داخل برنامه (نسخهٔ فروشنده)")
    # پیش‌تر نشانی فقط از فایل اینستالر/متغیر محیطی می‌آمد؛ اگر فروشنده نشانی
    # را عوض می‌کرد باید دوباره نصب می‌شد. حالا از داخل برنامه هم ذخیره می‌شود.
    server_file = os.path.join(INSTALL, "license-server.txt")
    os.environ.pop("SABA_LICENSE_SERVER", None)
    if os.path.exists(server_file):
        os.remove(server_file)
    install.clear_cache()
    check("بدون نشانی، برنامه «بدون سرور» است", lic.cloud_configured() is False,
          lic.cloud_info())
    missing = client.post("/api/license/cloud/request",
                          json={"name": "x", "phone": "1"})
    check("درخواست بدون نشانی، خطای روشن می‌دهد",
          missing.status_code == 400 and
          "تنظیم نشده" in str(missing.get_json().get("error")),
          missing.get_json())

    anonymous = cust_client.post("/api/license/cloud/settings",
                                 json={"license_server": base_url})
    check("بدون ورود نمی‌شود نشانی سرور را عوض کرد",
          anonymous.status_code in (401, 403), anonymous.status_code)

    saved = seller_client.post("/api/license/cloud/settings",
                               json={"license_server": base_url + "/"}).get_json()
    check("فروشنده نشانی را از داخل برنامه ذخیره می‌کند", saved.get("ok"), saved)
    check("نشانی ذخیره‌شده «/» انتهایی ندارد",
          seller.license.cloud_settings()["server"] == base_url,
          seller.license.cloud_settings()["server"])
    again = create_app(db_path=os.path.join(DATA, "seller.db"), mode="admin",
                       folder=seller_dir)
    check("نشانی در پایگاه‌داده می‌ماند (پس از باز شدن دوبارهٔ برنامه)",
          again.license.cloud_settings()["server"] == base_url,
          again.license.cloud_settings()["server"])
    check("برنامه پس از ذخیره «متصل» گزارش می‌شود",
          seller.license.cloud_info()["configured"] is True,
          seller.license.cloud_info())

    seller_client.post("/api/license/cloud/settings",
                       json={"license_client_token": "T-1"})
    check("ذخیرهٔ کلید اتصال، نشانی سرور را پاک نمی‌کند",
          seller.license.cloud_settings()["server"] == base_url and
          seller.license.cloud_settings()["token"] == "T-1",
          seller.license.cloud_settings())

    os.environ["SABA_LICENSE_SERVER"] = base_url
    install.clear_cache()
    fixed = client.post("/api/license/cloud/request",
                        json={"name": "باتری نو", "phone": "09120000009"})
    check("پس از تنظیم نشانی، درخواست دوباره کار می‌کند",
          fixed.status_code == 200 and fixed.get_json().get("ok"), fixed.get_json())
    with open(server_file, "w", encoding="utf-8") as f:
        f.write(base_url + "\n")
    install.clear_cache()

    server.shutdown()
    print("\n" + "=" * 60)
    print("موفق: {}   ناموفق: {}".format(PASS, FAIL))
    print("=" * 60)
    if FAILURES:
        print("موارد ناموفق:")
        for item in FAILURES:
            print("  - " + item)
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
