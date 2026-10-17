"""سرور لایسنس آنلاین سیستم حسابداری Mental + بات بله.

این یک سرویس است که دو کار می‌کند:

۱) **API برای برنامهٔ مشتری**: درخواست فعال‌سازی، دریافت لایسنس امضاشده و
   بررسی دوره‌ای (برای تشخیص لغو از راه دور).
۲) **بات بله**: فروشنده درخواست‌ها را می‌بیند، با دکمه‌ها تأیید می‌کند و
   لایسنس صادر/لغو می‌شود. مشتری هم می‌تواند درخواست بدهد و وضعیت را ببیند.

اجرای محلی:  python app.py            (پیش‌فرض روی پورت 5000)
اجرای سرور:  سرویس میزبانی فایل `app` را با gunicorn اجرا می‌کند.
"""
import os
import secrets
import threading
import traceback
import uuid

from flask import Flask, jsonify, request

import bale
import botlogic
import store as store_mod
from config import get_config
from sabalic import jdate, licensing

VERSION = "1.0.0"
SERVER_ID = "saba-license-server"
POLL_LEASE = "bale-poll"
POLL_OWNER = uuid.uuid4().hex

# سبک صفحهٔ وضعیت. جدا از قالب نگه داشته می‌شود تا آکولادهای CSS با
# جانگهدارهای `.format()` قالب قاطی نشوند و صفحهٔ اصلی خطای ۵۰۰ ندهد.
HOME_STYLE = """body{font-family:Tahoma,system-ui,sans-serif;background:#0f172a;color:#e2e8f0;
margin:0;padding:40px}main{max-width:640px;margin:auto;background:#1e293b;
border-radius:16px;padding:28px}h1{margin:0 0 6px;font-size:20px}
p{color:#94a3b8;line-height:1.9}table{width:100%;border-collapse:collapse;
margin-top:14px}td{padding:8px 6px;border-bottom:1px solid #334155}
b{color:#f8fafc}"""

_cfg = get_config()
_store = store_mod.Store(_cfg.db_path)
_thread_started = False
_thread_lock = threading.Lock()


def _log(msg):
    print("[saba-license] {}".format(msg), flush=True)


def log(msg):
    _log(msg)


_bot = botlogic.Bot(bale.Bale(_cfg.bot_token, _cfg.api_base), _store, _cfg,
                    log=_log)


# --------------------------------------------------------------------- مشتری
def _client_ip():
    """نشانی IP برای محدودیت نرخ؛ پشت پروکسی از X-Forwarded-For استفاده می‌کند."""
    addr = (request.remote_addr or "").strip()
    if addr in ("", "127.0.0.1", "::1") or addr.startswith(("10.", "192.168.", "172.")):
        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if xff:
            addr = xff
    return addr or "unknown"


def _ok(data=None, **extra):
    payload = {"ok": True}
    if data is not None:
        payload.update({"data": data} if not isinstance(data, dict) else data)
    payload.update(extra)
    return jsonify(payload)


def _err(message, code=400, **extra):
    payload = {"ok": False, "error": str(message)}
    payload.update(extra)
    return jsonify(payload), code


def _client_allowed(cfg):
    """دروازهٔ نرم: اگر سرور کلید اتصال داشته باشد، برنامه باید همان را بفرستد."""
    expected = (getattr(cfg, "client_token", "") or "").strip()
    if not expected:
        return True
    given = (request.headers.get("X-Saba-Client") or request.args.get("client")
             or "").strip()
    return given == expected


def _admin_allowed(cfg):
    """دروازهٔ API مدیریت (برنامهٔ فروشنده): توکن مدیر با مقایسهٔ زمان‌ثابت.

    اگر روی سرور `SABA_ADMIN_TOKEN` تنظیم نشده باشد، این درا از برنامه بسته
    است؛ تأیید درخواست‌ها از بات بله همیشه کار می‌کند.
    """
    expected = (getattr(cfg, "admin_token", "") or "").strip()
    if not expected:
        return False
    given = (request.headers.get("X-Saba-Admin") or "").strip()
    return secrets.compare_digest(given, expected)


def _clean_code(raw, allow_short=True):
    """اعتبارسنجی اثر انگشت دستگاه (۶۴ نویسهٔ هگز) یا کد کوتاه (۲۰ نویسه)."""
    norm = licensing.normalize_machine(raw)
    lengths = (20, 64) if allow_short else (64,)
    if len(norm) not in lengths or not norm.isalnum():
        return ""
    return norm


def _expired(lic):
    expires = (lic or {}).get("expires") or ""
    if not expires:
        return False
    return jdate.today_str() > expires


def _device_state(device, lic):
    """وضعیت قابل‌ارائهٔ یک دستگاه در قالب دیکشنری کوچک."""
    if not device:
        return {"status": "none", "message": "این رایانه در سرور ثبت نشده است."}
    if lic and lic.get("revoked"):
        return {"status": "revoked",
                "message": "لایسنس این رایانه لغو شده است."}
    if device.get("status") == "denied":
        return {"status": "denied", "message": "درخواست فعال‌سازی تأیید نشد."}
    if device.get("status") == "revoked":
        return {"status": "revoked", "message": "لایسنس این رایانه لغو شده است."}
    if not lic:
        return {"status": "pending",
                "message": "درخواست شما در انتظار تأیید فروشنده است."}
    if _expired(lic):
        return {"status": "expired",
                "message": "اشتراک این لایسنس در تاریخ {} به پایان رسیده است."
                           .format(lic.get("expires"))}
    return {"status": "active", "message": "لایسنس فعال است."}


def _license_public(lic):
    if not lic:
        return None
    return {
        "lic_id": lic.get("lic_id") or "",
        "edition": lic.get("edition") or "premium",
        "seats": lic.get("seats") or 1,
        "issued": lic.get("issued") or "",
        "expires": lic.get("expires") or "",
        "revoked": bool(lic.get("revoked")),
        "key": lic.get("key_text") or "",
        "customer": "",
    }


def _find_device(store, fingerprint, machine_code=""):
    """یافتن دستگاه با اثر انگشت کامل یا کد کوتاه (در همان انبار دادهٔ سرور)."""
    device = None
    if fingerprint:
        device = store.device_lookup_any(fingerprint)
    if not device and machine_code:
        device = store.device_lookup_any(machine_code)
    return device


def _license_of(store, device):
    if not device:
        return None
    lid = device.get("license_id") or 0
    if not lid:
        return None
    return store.license_get(lid)


# ----------------------------------------------------------------- آفرینش
def create_app(cfg=None, store=None, bot=None, start_bot=None):
    cfg = cfg or _cfg
    store = store or _store
    bot = bot or _bot

    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    # ------------------------------------------------------------------- عمومی
    @app.route("/")
    def home():
        s = store.stats()
        return app.response_class(
            """<!DOCTYPE html><html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><title>سرور لایسنس سیستم حسابداری Mental</title>
<style>{style}</style></head><body><main>
<h1>✅ سرور لایسنس سیستم حسابداری Mental</h1>
<p>این سرویس فعال است. مدیریت لایسنس‌ها فقط از طریق بات بله انجام می‌شود.</p>
<table>
<tr><td>نسخه</td><td><b>{version}</b></td></tr>
<tr><td>مشتریان</td><td><b>{customers}</b></td></tr>
<tr><td>دستگاه‌های فعال</td><td><b>{devices_active}</b></td></tr>
<tr><td>در انتظار تأیید</td><td><b>{requests_pending}</b></td></tr>
<tr><td>لایسنس‌های صادرشده</td><td><b>{licenses}</b></td></tr>
<tr><td>لغوشده</td><td><b>{licenses_revoked}</b></td></tr>
</table></main></body></html>""".format(style=HOME_STYLE, version=VERSION, **s),
            mimetype="text/html")

    @app.route("/health")
    def health():
        return jsonify({"ok": True, "server": SERVER_ID, "version": VERSION,
                        "time": store_mod.now()})

    # ------------------------------------------------- برنامهٔ مشتری (API)
    @app.route("/api/v1/info")
    def api_info():
        if not _client_allowed(cfg):
            return _err("کلید اتصال برنامه نادرست است", 401)
        return _ok({"server": SERVER_ID, "version": VERSION,
                    "grace_days": cfg.grace_days,
                    "server_date": jdate.today_str(),
                    "server_time": store_mod.now(),
                    "editions": list(licensing.EDITIONS.keys()),
                    "features": list(licensing.ALL_FEATURES)})

    @app.route("/api/v1/request", methods=["POST"])
    def api_request():
        if not _client_allowed(cfg):
            return _err("کلید اتصال برنامه نادرست است", 401)
        if not store.rate_allow(_client_ip(), cfg.rate_limit):
            return _err("درخواست‌های زیادی از این نشانی ثبت شد؛ کمی بعد تلاش کنید.",
                        429)
        data = request.get_json(silent=True) or {}
        fingerprint = _clean_code(data.get("fingerprint") or "", allow_short=True)
        machine_code = _clean_code(data.get("machine_code") or "")
        if not fingerprint:
            return _err("شناسهٔ دستگاه نامعتبر است")
        name = str(data.get("name") or "").strip()[:80]
        phone = str(data.get("phone") or "").strip()[:30]
        note = str(data.get("note") or "").strip()[:200]

        device = _find_device(store, fingerprint, machine_code)
        if device is None:
            device = store.device_get(store.device_add(
                fingerprint, machine_code or fingerprint[:20].upper(), None,
                label=name, note=note))
        else:
            fields = {"last_seen": store_mod.now(), "machine_code": machine_code or
                      device.get("machine_code") or ""}
            if name:
                fields["label"] = name
            store.device_update(device["id"], **fields)

        customer = None
        if device.get("customer_id"):
            customer = store.customer_get(device["customer_id"])
        if customer is None and (name or phone):
            customer = store.customer_find(name=name, phone=phone)
            if customer is None:
                cid = store.customer_add(name or "بدون نام", phone, note=note,
                                         max_devices=1)
                customer = store.customer_get(cid)
            store.device_update(device["id"], customer_id=customer["id"])
            # سقف دستگاه‌های مجاز مشتری
            active = [d for d in store.active_devices_of(customer["id"])
                      if d["id"] != device["id"]]
            limit = int(customer.get("max_devices") or 0)
            if limit and len(active) >= limit:
                store.audit(customer["id"], "device_limit",
                             "دستگاه {} بیش از سقف {}".format(device["id"], limit))
                bot._notify_admins(
                    "⚠️ مشتری #{} «{}» درخواست دستگاه جدید داد ولی سقف دستگاه‌های "
                    "مجاز ({}) پر است.\nکد دستگاه: {}".format(
                        customer["id"], customer["name"], limit,
                        machine_code or fingerprint[:20].upper()))

        lic = _license_of(store, device)
        state = _device_state(device, lic)
        if state["status"] == "active":
            return _ok({"status": "active", "request_id": 0,
                        "license": _license_public(lic),
                        "message": "این رایانه از قبل فعال است."})
        if state["status"] in ("revoked", "denied", "expired"):
            return _ok({"status": state["status"], "request_id": 0,
                        "message": state["message"]})

        req = store.request_add(device["id"], device["fingerprint"],
                                machine_code or device.get("machine_code") or "",
                                (customer or {}).get("id"), name or
                                (customer or {}).get("name") or "",
                                phone or (customer or {}).get("phone") or "", note)
        if req["status"] == "pending":
            text = ("🔔 درخواست فعال‌سازی #{}\nمشتری: {}\nتلفن: {}\nکد دستگاه: {}\n"
                    "تاریخ: {}").format(req["id"],
                                        (customer or {}).get("name") or name or "—",
                                        (customer or {}).get("phone") or phone or "—",
                                        (machine_code or "").upper()
                                        or fingerprint[:20].upper(), req["created_at"])
            bot._notify_admins(text, bale.keyboard(
                [[("✅ تأیید", "ap:{}".format(req["id"])),
                  ("❌ رد", "dn:{}".format(req["id"]))]]))
        return _ok({"status": "pending", "request_id": req["id"],
                    "message": "درخواست ثبت شد و برای فروشنده ارسال گردید."})

    @app.route("/api/v1/status")
    def api_status():
        if not _client_allowed(cfg):
            return _err("کلید اتصال برنامه نادرست است", 401)
        if not store.rate_allow(_client_ip(), max(cfg.rate_limit * 4, 240)):
            return _err("درخواست‌های زیادی از این نشانی ثبت شد؛ کمی بعد تلاش کنید.",
                        429)
        fingerprint = _clean_code(request.args.get("fingerprint") or "")
        machine_code = _clean_code(request.args.get("machine_code") or "")
        if not fingerprint and not machine_code:
            return _err("شناسهٔ دستگاه فرستاده نشده است")
        device = _find_device(store, fingerprint, machine_code)
        lic = _license_of(store, device)
        state = _device_state(device, lic)
        if device:
            store.device_update(device["id"], last_seen=store_mod.now())
        out = {"status": state["status"], "message": state["message"],
               "server_date": jdate.today_str(), "server_time": store_mod.now(),
               "grace_days": cfg.grace_days, "license": None}
        if state["status"] == "active":
            info = _license_public(lic)
            out["license"] = info
            if device.get("customer_id"):
                customer = store.customer_get(device["customer_id"])
                if customer:
                    info["customer"] = customer.get("name") or ""
        return _ok(out)

    @app.route("/api/v1/checkin", methods=["POST"])
    def api_checkin():
        """بررسی دوره‌ای: برنامه می‌گوید «من هنوز زنده‌ام» و پاسخ می‌گیرد.

        پاسخ `active` یعنی لایسنس سرور معتبر است؛ `revoked`/`expired`/`denied`
        یعنی برنامه باید قفل شود.
        """
        if not _client_allowed(cfg):
            return _err("کلید اتصال برنامه نادرست است", 401)
        if not store.rate_allow(_client_ip(), max(cfg.rate_limit * 4, 240)):
            return _err("درخواست‌های زیادی از این نشانی ثبت شد", 429)
        data = request.get_json(silent=True) or {}
        fingerprint = _clean_code(data.get("fingerprint") or "")
        machine_code = _clean_code(data.get("machine_code") or "")
        device = _find_device(store, fingerprint, machine_code)
        lic = _license_of(store, device)
        state = _device_state(device, lic)
        if device:
            store.device_update(device["id"], last_seen=store_mod.now())
        return _ok({"status": state["status"], "message": state["message"],
                    "server_date": jdate.today_str(), "server_time": store_mod.now(),
                    "grace_days": cfg.grace_days,
                    "license": _license_public(lic) if state["status"] == "active"
                    else None})

    # ------------------------------------- پنل فروشنده (برنامهٔ دسکتاپ)
    # برنامهٔ فروشنده با توکن مدیر همین دو نشانی را صدا می‌زند: فهرست
    # درخواست‌های در انتظار و تأیید/رد آن‌ها با «تعداد کاربر» و «روز».
    # ربات و برنامه از یک انبار داده و یک منطق صدور استفاده می‌کنند.
    @app.route("/api/v1/admin/requests")
    def api_admin_requests():
        if not _admin_allowed(cfg):
            return _err("توکن مدیر نامعتبر است یا روی سرور تنظیم نشده است", 403)
        rows = store.requests_pending(limit=100)
        out = []
        for req in rows:
            device = store.device_get(req["device_id"]) or {}
            customer = store.customer_get(req["customer_id"]) or {}
            cid = req.get("customer_id") or 0
            out.append({
                "id": req["id"],
                "customer": customer.get("name") or req.get("name") or "",
                "phone": customer.get("phone") or req.get("phone") or "",
                "machine_code": (req.get("machine_code")
                                 or device.get("machine_code") or "").upper(),
                "note": req.get("note") or "",
                "created_at": req.get("created_at") or "",
                "devices_active": len(store.active_devices_of(cid)) if cid else 0,
                "devices_max": int(customer.get("max_devices") or 0),
            })
        return _ok({
            "requests": out,
            "server_date": jdate.today_str(),
            "default_edition": cfg.default_edition,
            "default_seats": cfg.default_seats,
            "default_days": cfg.default_days,
            "days_choices": list(botlogic.DAYS_CHOICES),
            "seat_choices": list(botlogic.SEAT_CHOICES),
            "editions": [{"id": key, "label": value["label"],
                          "seats": licensing.EDITION_MAX_SEATS.get(key, 1)}
                         for key, value in licensing.EDITIONS.items()],
        })

    @app.route("/api/v1/admin/decide", methods=["POST"])
    def api_admin_decide():
        """تأیید یا رد یک درخواست از داخل برنامهٔ فروشنده."""
        if not _admin_allowed(cfg):
            return _err("توکن مدیر نامعتبر است یا روی سرور تنظیم نشده است", 403)
        data = request.get_json(silent=True) or {}
        try:
            rid = int(data.get("request_id") or 0)
        except (TypeError, ValueError):
            rid = 0
        if rid <= 0:
            return _err("شمارهٔ درخواست نامعتبر است")
        admin_note = str(data.get("note") or "").strip()[:200]
        action = str(data.get("action") or "").strip().lower()

        if action in ("approve", "approved", "ok"):
            edition = str(data.get("edition") or cfg.default_edition).strip().lower()
            if edition not in licensing.EDITIONS:
                edition = cfg.default_edition
            try:
                seats = int(data.get("seats"))
            except (TypeError, ValueError):
                seats = cfg.default_seats
            raw_days = data.get("days")
            try:
                days = int(raw_days) if raw_days not in (None, "") else cfg.default_days
            except (TypeError, ValueError):
                days = cfg.default_days
            days = max(0, days)
            seats = max(1, seats)
            summary, info = bot.issue_for_request(
                rid, edition, days, seats, 0, source="app",
                admin_note=admin_note)
            if not info:
                return _err(summary, 409)
            store.audit(0, "app_issue", "{} — درخواست #{}".format(
                info["lic_id"], rid))
            bot._notify_admins("🖥️ لایسنس {} از داخل برنامه تأیید شد "
                               "(درخواست #{}) — {} / {} / {} کاربر".format(
                                   info["lic_id"], rid,
                                   botlogic.edition_label(edition),
                                   botlogic.days_label(days), info["seats"]))
            return _ok({"request_id": rid, "lic_id": info["lic_id"],
                        "seats": info["seats"], "days": info["days"],
                        "edition": info["edition"], "expires": info["expires"],
                        "summary": summary},
                       message="لایسنس صادر شد")

        if action in ("deny", "denied", "reject"):
            done, text = bot.deny(rid, 0, source="app", admin_note=admin_note)
            if not done:
                return _err(text, 409)
            store.audit(0, "app_deny", "درخواست #{}".format(rid))
            bot._notify_admins("🖥️ درخواست #{} از داخل برنامه رد شد".format(rid))
            return _ok({"request_id": rid}, message=text)

        return _err("عملیات نامعتبر است (approve یا deny)")

    @app.errorhandler(404)
    def not_found(_exc):
        return _err("نشانی ناشناخته", 404)

    @app.errorhandler(500)
    def server_error(_exc):
        log("خطای داخلی سرور:\n" + traceback.format_exc())
        return _err("خطای داخلی سرور", 500)

    app.cfg = cfg
    app.store = store
    app.bot = bot
    return app


# --------------------------------------------------------- نخِ نظرسنجی بات
def start_bot_thread(cfg=None, store=None, bot=None, disable=None):
    """شروع نظرسنجی طولانی بات در نخ پس‌زمینه (idempotent)."""
    global _thread_started
    cfg = cfg or _cfg
    store = store or _store
    bot = bot or _bot
    if disable is None:
        disable = os.environ.get("SABA_BOT_DISABLE") == "1"
    if disable:
        log("نظرسنجی بات خاموش است (SABA_BOT_DISABLE=1).")
        return None
    with _thread_lock:
        if _thread_started:
            return None
        _thread_started = True

    def loop():
        import time
        # اگر نمونهٔ دیگری از سرویس در حال نظرسنجی باشد، این نخ بیکار می‌ماند.
        while not store.lease_acquire(POLL_LEASE, POLL_OWNER, ttl=60):
            time.sleep(5)
        log("نظرسنجی بات آغاز شد.")
        try:
            me = bot.api.get_me()
            log("بات شناسایی شد: {}".format((me or {}).get("username") or "?"))
        except bale.BaleError as exc:
            log("⚠️ getMe ناموفق بود: {}".format(exc))
        problems = cfg.missing()
        if problems:
            log("⚠️ تنظیمات ناقص: " + "؛ ".join(problems))
        if cfg.startup_ping:
            bot._notify_admins("🚀 سرور لایسنس بالا آمد.\n/help برای راهنما")
        running = {"v": True}

        def stop():
            if not running["v"]:
                return True
            # تمدید قفل در هر دور؛ اگر پروسهٔ دیگری قفل را گرفت، متوقف شو.
            if not store.lease_acquire(POLL_LEASE, POLL_OWNER, ttl=60):
                log("نمونهٔ دیگری نظرسنجی را در دست گرفت؛ این نخ متوقف شد.")
                running["v"] = False
                return True
            return False

        bale.poll_forever(bot.api, bot.handle, log=log, stop=stop)

    thread = threading.Thread(target=loop, daemon=True, name="bale-poll")
    thread.start()
    return thread


app = create_app()
if os.environ.get("SABA_NO_AUTOSTART") != "1":
    try:
        start_bot_thread()
    except Exception:                            # noqa: BLE001 - سرویس باید بالا بیاید
        log("راه‌اندازی نخ بات ناموفق بود:\n" + traceback.format_exc())


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or 5000)
    log("سرور روی 0.0.0.0:{} اجرا می‌شود.".format(port))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True,
            use_reloader=False)
