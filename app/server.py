"""سرور محلی: API برنامه حسابداری به‌همراه ارائهٔ رابط کاربری فارسی."""
import os
import io
import json
import secrets
import shutil
import sqlite3
import sys
import threading
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, jsonify, request, send_from_directory, session,
                   send_file, abort)

from . import install
from . import jdate
from . import licensing
from .cloudlicense import CloudClient, CloudError
from .db import DB, hash_password, verify_password
from .logic import Logic, KINDS, KIND_PREFIX

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# شناسهٔ برنامه؛ برای تشخیص «سرویس خودمان» از سرویس بیگانه روی یک پورت
APP_ID = "hesabdari-saba"

# هیچ‌کدام از دارایی‌های رابط کاربری نباید کش شوند؛ وگرنه مرورگر
# ممکن است صفحهٔ کهنه را نشان دهد در حالی که سرویس محلی دیگر بالا نیست.
NO_STORE_TYPES = ("text/html", "text/css", "application/javascript",
                  "application/json", "image/svg+xml", "font/woff2", "font/woff")


def resource_path(rel):
    import sys
    base = getattr(sys, "_MEIPASS", BASE_DIR)
    return os.path.join(base, rel)


def data_dir():
    """پوشهٔ داده‌ها (پایگاه‌داده، لایسنس، پشتیبان‌ها پیش‌فرض).

    مسیر از `app/install.py` می‌آید: می‌تواند انتخابی باشد که کاربر هنگام نصب
    کرده است (فایل `data-dir.txt` کنار فایل اجرایی) یا پوشهٔ پیش‌فرض کنار
    برنامه؛ در هر حالت باید نوشتنی باشد.
    """
    return install.data_dir()


def backup_dir(db=None):
    """پوشهٔ فایل‌های پشتیبان (انتخاب کاربر یا زیرپوشهٔ داده)."""
    value = ""
    try:
        if db is not None:
            value = db.get_setting("backup_dir", "") or ""
    except Exception:                           # noqa: BLE001 - پایگاه‌داده آماده نیست
        value = ""
    return install.backup_dir(value)


def backup_keep(db):
    """چند نسخهٔ پشتیبان نگه داشته شود (پیش‌فرض ۲۰)."""
    try:
        return max(1, int(db.get_setting("backup_keep", "20") or 20))
    except (TypeError, ValueError):
        return 20


_background_started = False


def start_background(target):
    """نخ پس‌زمینه را فقط یک‌بار در هر پروسه اجرا می‌کند.

    دلیل یک‌بار بودن: آزمون‌ها و راه‌اندازی‌های چندگانهٔ Flask نباید چند نخ
    بررسی/پشتیبان‌گیری بسازند. با SABA_NO_CHECKIN=1 خاموش می‌شود.
    """
    global _background_started
    if os.environ.get("SABA_NO_CHECKIN") == "1":
        return None
    if _background_started:
        return None
    _background_started = True
    thread = threading.Thread(target=target, daemon=True, name="saba-background")
    thread.start()
    return thread


def log_line(msg):
    """ثبت رخداد در فایل گزارش کنار داده‌ها (برای عیب‌یابی نصب مشتری)."""
    line = "{}  {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(os.path.join(data_dir(), "app.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    return line


# --------------------------------------------------------------- نسخهٔ برنامه
# دو فایل اجرایی از همین کد ساخته می‌شود:
#   * حالت «user»  — نسخه‌ای که به مشتری داده می‌شود؛ کلید خصوصی را ندارد و
#                    بدون لایسنس معتبر هیچ داده‌ای باز نمی‌شود.
#   * حالت «admin» — نسخهٔ خود شما برای پشتیبانی و صدور لایسنس.
MODE_ADMIN = "admin"
MODE_USER = "user"
# نسخه از واژهٔ «admin» در نام فایل اجرایی تشخیص داده می‌شود، بی‌اعتنا به
# جداکننده‌ها؛ بنابراین هر دو نام قدیمی «HesabDari-Saba-Admin.exe» و نام تازهٔ
# «Mental admin accounting.exe» درست شناسایی می‌شوند.
ADMIN_EXE_HINT = "admin"


def _name_words(name):
    """واژه‌های نام فایل اجرایی (بدون پسوند، حروف کوچک).

    «Mental admin accounting.exe» ← {"mental", "admin", "accounting", "exe"}
    «HesabDari-Saba-Admin.exe»     ← {"hesabdari", "saba", "admin", "exe"}
    """
    clean = "".join(ch if ch.isalnum() else " " for ch in (name or "").lower())
    return set(clean.split())


# مهلت پیش‌فرض بی‌اتصال بودن لایسنس آنلاین (روز). سرور می‌تواند عدد دیگری
# اعلام کند و همان ذخیره می‌شود.
DEFAULT_GRACE_DAYS = 15

# پیام وضعیت‌هایی که سرور لایسنس برمی‌گرداند.
CLOUD_STATUS_MESSAGES = {
    "none": "این رایانه در سرور لایسنس ثبت نشده است.",
    "pending": "درخواست فعال‌سازی در انتظار تأیید فروشنده است.",
    "active": "لایسنس فعال است.",
    "denied": "درخواست فعال‌سازی تأیید نشد.",
    "revoked": "لایسنس این رایانه لغو شده است.",
    "expired": "اشتراک لایسنس به پایان رسیده است.",
}


def app_mode():
    """حالت اجرا: از متغیر محیطی SABA_MODE یا از نام فایل اجرایی."""
    env = (os.environ.get("SABA_MODE") or "").strip().lower()
    if env in (MODE_ADMIN, MODE_USER):
        return env
    if getattr(sys, "frozen", False):
        if ADMIN_EXE_HINT in _name_words(os.path.basename(sys.executable)):
            return MODE_ADMIN
    return MODE_USER


KEY_FILES = ("license_keys/root_public.key", "app/license_keys/root_public.key")
PRIVATE_KEY_FILES = ("license_keys/root_private.key",
                     "app/license_keys/root_private.key")


def load_root_public():
    """کلید عمومی ریشهٔ لایسنس (در هر دو نسخه بسته‌بندی می‌شود)."""
    paths = [resource_path(p) for p in KEY_FILES]
    paths += [os.path.join(BASE_DIR, p) for p in KEY_FILES]
    return licensing.find_public_key(paths)


def load_root_private():
    """کلید خصوصی ریشه؛ **فقط** در نسخهٔ مدیر موجود است."""
    paths = [resource_path(p) for p in PRIVATE_KEY_FILES]
    paths += [os.path.join(BASE_DIR, p) for p in PRIVATE_KEY_FILES]
    return licensing.find_public_key(paths)


def install_secret():
    """کلید امضای نشست، یک‌بار برای هر نصب و تصادفی ساخته می‌شود.

    دیگر هیچ کلید ثابتی در کد نیست؛ پس با دانستن سورس نمی‌شود کوکی جعل کرد.
    """
    path = os.path.join(data_dir(), ".session-key")
    try:
        with open(path, encoding="utf-8") as f:
            val = f.read().strip()
        if len(val) >= 32:
            return val
    except OSError:
        pass
    val = secrets.token_hex(32)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(val)
    except OSError:
        pass
    return val


class LicenseManager:
    """وضعیت لایسنس این نصب: فعال‌سازی، بررسی و صدور (فقط نسخهٔ مدیر)."""

    def __init__(self, db, mode, folder=None):
        self.db = db
        self.mode = mode
        self.folder = folder or data_dir()
        self.public_key, self.public_key_path = load_root_public()
        self.private_key = load_root_private()[0] if mode == MODE_ADMIN else None
        self.fingerprint = licensing.machine_fingerprint(self.folder)

    # ---------------------------------------------------------- اطلاعات پایه
    @property
    def path(self):
        return os.path.join(self.folder, "license.key")

    @property
    def can_issue(self):
        return bool(self.private_key)

    def stored_text(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    def machine_code(self):
        return licensing.machine_code(self.fingerprint)

    # -------------------------------------------------------------- بررسی
    def info(self):
        """وضعیت لایسنس؛ هرگز استثنا پرتاب نمی‌کند.

        در نسخهٔ مدیر لایسنس لازم نیست (آن نسخه خودش صادرکننده است).
        """
        text = self.stored_text()
        base = {"mode": self.mode, "installed": bool(text),
                "machine_code": self.machine_code(),
                "machine_fingerprint": self.fingerprint,
                "can_issue": self.can_issue,
                "required": self.mode != MODE_ADMIN,
                "valid": False, "reason": "missing", "message": "",
                "customer": "", "edition": "base", "features": [], "seats": 1,
                "issued": "", "expires": "", "days_left": None,
                "clock_tampered": False,
                "online": False, "cloud": None}
        if self.mode == MODE_ADMIN:
            base.update(valid=True, reason="admin", edition="premium",
                        features=list(licensing.ALL_FEATURES),
                        seats=licensing.EDITION_MAX_SEATS["premium"],
                        message="نسخهٔ مدیر — بدون محدودیت")
            if not self.public_key:
                base.update(message="کلید عمومی ریشه پیدا نشد؛ صدور لایسنس ممکن نیست.")
            if text:
                v = licensing.verify_license(text, self.public_key or b"",
                                             self.fingerprint, data_dir=self.folder)
                if v["valid"]:
                    base.update(customer=v["customer"], issued=str(v["payload"].get("issued") or ""),
                                expires=str(v["payload"].get("expires") or ""))
            return base
        if not self.public_key:
            base.update(reason="nokey",
                        message="کلید عمومی لایسنس همراه برنامه نصب نشده است.")
            return base
        if not text:
            base.update(reason="missing", message="برنامه فعال نشده است.")
            return base
        v = licensing.verify_license(text, self.public_key, self.fingerprint,
                                     data_dir=self.folder)
        base.update(valid=v["valid"], reason=v["reason"], message=v["message"],
                    customer=v["customer"], edition=v["edition"],
                    features=list(v["features"]), seats=v["seats"])
        payload = v["payload"] or {}
        base["issued"] = str(payload.get("issued") or "")
        base["expires"] = str(payload.get("expires") or "")
        if v["valid"] and base["expires"]:
            base["days_left"] = self._days_left(base["expires"])
        base["clock_tampered"] = licensing.clock_rolled_back(
            self.folder, self.fingerprint, jdate.today_str())
        if base["clock_tampered"]:
            base.update(valid=False, reason="clock",
                        message="ساعت سیستم از آخرین اجرا عقب‌تر است؛ لایسنس قفل شد.")
            return base
        if v["valid"]:
            licensing.write_state(self.folder, self.fingerprint,
                                  jdate.today_str(),
                                  {"customer": v["customer"],
                                   "edition": v["edition"],
                                   "expires": base["expires"],
                                   "online": bool(v["online"])})
            if v["online"] and self.cloud_configured():
                # لایسنس آنلاین: تا وقتی بررسی دوره‌ای تازه باشد معتبر است
                base["online"] = True
                base["cloud"] = self.cloud_info()
                enforce = self.cloud_enforcement()
                if not enforce["ok"]:
                    base.update(valid=False, reason=enforce["reason"],
                                message=enforce["message"])
                    return base
        return base

    @staticmethod
    def _days_left(expires):
        """روز باقی‌مانده تا انقضا — با تقویم شمسی حساب می‌شود (دقیق).

        فرمول تقریبی «ماه × ۳۱» اشتباه می‌داد: لایسنس ۹۰ روزه «۹۳ روز»
        نشان می‌داد. با اختلاف واقعی روزها، عدد نمایش‌داده‌شده همان مدت
        انتخاب‌شدهٔ فروشنده است.
        """
        if not expires:
            return None
        try:
            return jdate.diff_days(jdate.today_str(), expires)
        except (ValueError, TypeError, IndexError, AttributeError):
            return None

    # ------------------------------------------------------ لایسنس آنلاین
    @property
    def cloud_state_path(self):
        return os.path.join(self.folder, "cloud_state.json")

    def cloud_settings(self):
        """تنظیمات ارتباط با سرور لایسنس.

        ترتیب اولویت: متغیر محیطی ← تنظیمات کاربر در برنامه ← فایل اینستالر.
        """
        def setting(key, default=""):
            try:
                return self.db.get_setting(key, default) or default
            except Exception:                   # noqa: BLE001
                return default

        try:
            hours = max(1, int(setting("license_check_hours", "6")))
        except (TypeError, ValueError):
            hours = 6
        try:
            grace = int(setting("license_grace_days", "0"))
        except (TypeError, ValueError):
            grace = 0
        insecure = str(setting("license_insecure", "")).strip().lower() in (
            "1", "true", "yes", "بله")
        return {
            "server": install.license_server(setting("license_server", "")),
            "token": install.client_token(setting("license_client_token", "")),
            "admin": install.admin_token(setting("license_admin_token", "")),
            "hours": hours, "grace": grace, "insecure": insecure,
        }

    def cloud_configured(self):
        return bool(self.cloud_settings()["server"])

    def cloud_client(self):
        s = self.cloud_settings()
        if not s["server"]:
            return None
        return CloudClient(s["server"], s["token"], insecure=s["insecure"],
                           admin_token=s["admin"])

    def cloud_admin_ready(self):
        """آیا پنل تأیید درخواست‌ها در این نصب کار می‌کند؟

        سه شرط با هم: نسخهٔ فروشنده (MODE_ADMIN)، نشانی سرور لایسنس، و توکن
        مدیر. توکن را فقط اینستالر نسخهٔ فروشنده می‌نویسد؛ پس روی رایانهٔ
        مشتری این پنل هرگز باز نمی‌شود.
        """
        s = self.cloud_settings()
        return bool(self.mode == MODE_ADMIN and s["server"] and s["admin"])

    def cloud_state(self):
        """وضعیت ذخیره‌شدهٔ بررسی آنلاین (امضاشده؛ دست‌کاری تشخیص داده می‌شود)."""
        return licensing.state_load(self.cloud_state_path, self.fingerprint)

    def cloud_write(self, **fields):
        data = dict(self.cloud_state())
        data.pop("tampered", None)
        data.update(fields)
        return licensing.state_save(self.cloud_state_path, self.fingerprint, data)

    def cloud_info(self):
        """خلاصهٔ وضعیت آنلاین برای رابط کاربری."""
        s = self.cloud_settings()
        st = self.cloud_state()
        return {
            "configured": bool(s["server"]), "server": s["server"],
            "has_token": bool(s["token"]), "hours": s["hours"],
            "grace": s["grace"] or self.grace_days(),
            "status": str(st.get("status") or ""),
            "message": str(st.get("message") or ""),
            "lic_id": str(st.get("lic_id") or ""),
            "checked_at": str(st.get("at") or ""),
            "checked_day": str(st.get("day") or ""),
            "server_date": str(st.get("server_date") or ""),
            "request_id": st.get("request_id") or 0,
            "requested": bool(st.get("requested")),
            "error": str(st.get("error") or ""),
            "tampered": bool(st.get("tampered")),
        }

    def grace_days(self):
        """چند روز بی‌اتصال بودن مجاز است (تنظیم کاربر یا اعلام سرور)."""
        value = self.cloud_settings()["grace"]
        if value:
            return value
        try:
            stored = int(self.cloud_state().get("grace_days") or 0)
        except (TypeError, ValueError):
            stored = 0
        return stored or DEFAULT_GRACE_DAYS

    @staticmethod
    def _days_since(stamp):
        """چند روز از زمان داده‌شده (میلادی) گذشته است؛ None اگر نامعتبر باشد."""
        try:
            then = datetime.strptime(str(stamp)[:19], "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            return None
        return (datetime.now() - then).total_seconds() / 86400.0

    def cloud_enforcement(self):
        """آیا بررسی آنلاین، لایسنس را معتبر می‌داند؟

        فقط برای لایسنس‌های آنلاین (`online: true`) اجرا می‌شود؛ لایسنس‌های
        دستی قدیمی هیچ‌وقت به اینترنت نیاز ندارند.
        """
        st = self.cloud_state()
        if st.get("tampered"):
            return {"ok": False, "reason": "cloud_state",
                    "message": "فایل وضعیت بررسی آنلاین دست‌کاری شده است؛ برای "
                               "بررسی دوباره برنامه را ببندید و باز کنید."}
        status = str(st.get("status") or "")
        if status in ("revoked", "denied", "expired"):
            return {"ok": False, "reason": status,
                    "message": st.get("message") or CLOUD_STATUS_MESSAGES.get(
                        status, "لایسنس معتبر نیست.")}
        days = self._days_since(st.get("at"))
        if days is None:
            return {"ok": False, "reason": "never_checked",
                    "message": "این لایسنس آنلاین است و هنوز بررسی نشده؛ برای "
                               "تأیید به اینترنت وصل شوید."}
        grace = self.grace_days()
        if days > grace:
            return {"ok": False, "reason": "stale",
                    "message": "لایسنس آنلاین {} روز بررسی نشده است (مهلت {} روز). "
                               "اینترنت را وصل کنید و برنامه را باز کنید."
                               .format(int(days), grace)}
        return {"ok": True, "reason": "ok",
                "message": "بررسی آنلاین تازه است."}

    def _install_cloud_license(self, lic):
        """نصب لایسنسی که سرور فرستاده — با اعتبارسنجی کامل امضا و دستگاه."""
        key = str((lic or {}).get("key") or "").strip()
        if not key:
            return False, "متن لایسنس از سرور دریافت نشد."
        result = licensing.verify_license(key, self.public_key, self.fingerprint,
                                          data_dir=self.folder)
        if not result["valid"]:
            self.db.log_license_event(
                "cloud_bad_license",
                "{} | {}".format(result["reason"], result["message"]))
            return False, "لایسنس دریافتی معتبر نیست: " + result["message"]
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(key + "\n")
        except OSError as exc:
            return False, "نوشتن فایل لایسنس ممکن نشد: {}".format(exc)
        self.db.log_license_event("cloud_install", "{} | {}".format(
            (lic or {}).get("lic_id", ""), result["customer"]))
        return True, result["message"]

    def cloud_check(self):
        """گفت‌وگو با سرور: اگر لایسنس آماده بود نصب می‌شود و وضعیت ذخیره می‌گردد."""
        client = self.cloud_client()
        if client is None:
            return {"ok": False, "reason": "config",
                    "message": "نشانی سرور لایسنس تنظیم نشده است."}
        try:
            data = client.status(self.fingerprint, self.machine_code())
        except CloudError as exc:
            self.cloud_write(error=str(exc.message))
            self.db.log_license_event("cloud_error", str(exc.message))
            return {"ok": False, "reason": exc.kind, "message": str(exc.message),
                    "cloud": self.cloud_info(), "license": self.info()}
        status = str(data.get("status") or "")
        lic = data.get("license") or {}
        message = str(data.get("message") or "")
        fields = {"status": status, "message": message, "error": "",
                  "lic_id": str(lic.get("lic_id") or ""),
                  "day": jdate.today_str(),
                  "server_date": str(data.get("server_date") or ""),
                  "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        try:
            grace = int(data.get("grace_days") or 0)
        except (TypeError, ValueError):
            grace = 0
        if grace:
            fields["grace_days"] = grace
        if status == "active" and lic.get("key"):
            ok_install, why = self._install_cloud_license(lic)
            if not ok_install:
                self.cloud_write(error=why, status=status,
                                 day=jdate.today_str(), source="cloud")
                return {"ok": False, "reason": "license", "message": why,
                        "cloud": self.cloud_info(), "license": self.info()}
        self.cloud_write(source="cloud", **fields)
        return {"ok": True, "status": status,
                "message": message or CLOUD_STATUS_MESSAGES.get(status, ""),
                "cloud": self.cloud_info(), "license": self.info()}

    # --------------------------------- پنل فروشنده: تأیید از داخل برنامه
    def cloud_requests(self):
        """درخواست‌های در انتظار تأیید (از سرور لایسنس)."""
        client = self.cloud_client()
        if client is None or not self.cloud_admin_ready():
            return {"ok": False, "reason": "config",
                    "message": "این بخش فقط در نسخهٔ فروشنده و با توکن مدیر "
                               "کار می‌کند."}
        try:
            data = client.admin_requests()
        except CloudError as exc:
            return {"ok": False, "reason": exc.kind, "message": str(exc.message)}
        return {"ok": True, "data": data}

    def cloud_decide(self, request_id, action, edition="", seats=0, days=None,
                     note=""):
        """تأیید (با تعداد کاربر و روز) یا رد یک درخواست از داخل برنامه."""
        client = self.cloud_client()
        if client is None or not self.cloud_admin_ready():
            return {"ok": False, "reason": "config",
                    "message": "این بخش فقط در نسخهٔ فروشنده و با توکن مدیر "
                               "کار می‌کند."}
        try:
            data = client.admin_decide(request_id, action, edition=edition,
                                       seats=seats, days=days, note=note)
        except CloudError as exc:
            return {"ok": False, "reason": exc.kind, "message": str(exc.message)}
        self.db.log_license_event("cloud_{}".format(action),
                                  "{} | {}".format(request_id, data.get("lic_id")
                                                   or data.get("message") or ""))
        return {"ok": True, "data": data}

    def request_activation(self, name="", phone="", note=""):
        """ثبت درخواست فعال‌سازی در سرور (تأیید در بات بله توسط فروشنده)."""
        client = self.cloud_client()
        if client is None:
            return {"ok": False, "reason": "config",
                    "message": "نشانی سرور لایسنس تنظیم نشده است."}
        try:
            data = client.request_activation(self.fingerprint, self.machine_code(),
                                             name=name, phone=phone, note=note)
        except CloudError as exc:
            self.cloud_write(error=str(exc.message))
            return {"ok": False, "reason": exc.kind, "message": str(exc.message)}
        status = str(data.get("status") or "pending")
        self.cloud_write(status=status, requested=True,
                         message=str(data.get("message") or ""),
                         request_id=data.get("request_id") or 0,
                         day=jdate.today_str(),
                         at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         error="")
        self.db.log_license_event("cloud_request", "{} | {} | {}".format(
            data.get("request_id"), name, phone))
        return {"ok": True, "status": status,
                "message": str(data.get("message") or "درخواست ثبت شد."),
                "request_id": data.get("request_id") or 0,
                "cloud": self.cloud_info(), "license": self.info()}

    def has(self, feature):
        """آیا قابلیت پرمیوم در دسترس است؟ (نسخهٔ مدیر همیشه دارد.)"""
        if self.mode == MODE_ADMIN:
            return True
        info = self.info()
        return bool(info["valid"] and feature in info["features"])

    # ------------------------------------------------------------ فعال‌سازی
    def activate(self, text):
        text = (text or "").strip()
        if not self.public_key:
            return {"ok": False, "error": "کلید عمومی لایسنس همراه برنامه نیست."}
        result = licensing.verify_license(text, self.public_key, self.fingerprint,
                                          data_dir=self.folder)
        result["clock_tampered"] = licensing.clock_rolled_back(
            self.folder, self.fingerprint, jdate.today_str())
        if not result["valid"]:
            self.db.log_license_event("activate_failed",
                                      "{} | {}".format(result["reason"], result["message"]))
            return {"ok": False, "error": result["message"], "reason": result["reason"]}
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError as exc:
            return {"ok": False, "error": "نوشتن فایل لایسنس ممکن نشد: {}".format(exc)}
        self.db.log_license_event("activate", result["customer"] or "بدون نام")
        info = self.info()
        return {"ok": True, "license": info}

    def clear(self):
        try:
            os.remove(self.path)
        except OSError:
            pass
        self.db.log_license_event("deactivate", "")

    # ---------------------------------------------------------------- صدور
    def issue(self, d):
        """صدور لایسنس جدید (فقط نسخهٔ مدیر)."""
        if not self.can_issue:
            return {"ok": False,
                    "error": "کلید خصوصی صدور لایسنس در این نسخه وجود ندارد."}
        customer = str(d.get("customer") or "").strip()
        if not customer:
            return {"ok": False, "error": "نام مشتری الزامی است."}
        edition = str(d.get("edition") or "premium").lower()
        if edition not in licensing.EDITIONS:
            return {"ok": False, "error": "نسخهٔ انتخابی درست نیست."}
        feats = d.get("features")
        if feats is None:
            feats = list(licensing.EDITIONS[edition]["features"])
        feats = [f for f in feats if f in licensing.FEATURES]
        try:
            seats = int(d.get("seats") or licensing.EDITION_MAX_SEATS.get(edition, 1))
        except (TypeError, ValueError):
            return {"ok": False, "error": "تعداد کاربران درست نیست."}
        try:
            months = int(d.get("months") or 12)
        except (TypeError, ValueError):
            return {"ok": False, "error": "مدت اعتبار درست نیست."}
        if months not in (0, 1, 3, 6, 12, 24, 36):
            return {"ok": False, "error": "مدت اعتبار باید ۰، ۱، ۳، ۶، ۱۲، ۲۴ یا ۳۶ ماه باشد."}
        machine = str(d.get("machine") or "*").strip()
        if machine and machine != "*":
            machine = licensing.normalize_machine(machine)
            if len(machine) not in (20, 64):
                return {"ok": False, "error": "کد دستگاه معتبر نیست (باید ۲۰ نویسهٔ گروه‌بندی‌شده باشد)."}
        count = self.db.scalar("SELECT COUNT(*) FROM licenses", (), 0)
        lic_id = str(d.get("lic_id") or "SB-{}-{:04d}".format(
            jdate.today_str().replace("/", "")[:6], count + 1))
        out = licensing.issue_license(
            self.private_key, customer=customer, edition=edition, features=feats,
            seats=seats, machine=machine or "*", months=months, note=str(d.get("note") or ""),
            lic_id=lic_id)
        row_id = self.db.insert("licenses", {
            "lic_id": lic_id, "customer": customer, "edition": edition,
            "features": json.dumps(out["payload"]["features"], ensure_ascii=False),
            "seats": out["payload"]["seats"], "machine": out["payload"]["machine"],
            "issued": out["payload"]["issued"], "expires": out["payload"]["expires"],
            "note": out["payload"]["note"], "key_text": out["key"],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        self.db.log_license_event("issue", "{} | {}".format(lic_id, customer))
        return {"ok": True, "id": row_id, "lic_id": lic_id,
                "key": out["key"], "file": out["file"], "payload": out["payload"]}


def create_app(db_path=None, mode=None, folder=None):
    db_path = db_path or os.path.join(data_dir(), "hesabdari.db")
    mode = mode or app_mode()
    app = Flask(__name__, static_folder=None)
    # کلید نشست: تصادفی و مخصوص همین نصب (در پوشهٔ داده ذخیره می‌شود).
    app.secret_key = install_secret()
    app.config["JSON_AS_ASCII"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    db = DB(db_path)
    logic = Logic(db)
    lic = LicenseManager(db, mode, folder)

    # آیتم‌های پرمیوم هر بخش رابط کاربری و API
    PREMIUM_ROUTES = (
        ("/api/warehouses", "multi_warehouse"),
        ("/api/stock/transfer", "multi_warehouse"),
        ("/api/stock/adjust", "multi_warehouse"),
        ("/api/backup", "backup"),
        ("/api/restore", "backup"),
        ("/api/export/", "backup"),
        ("/api/reports/trial-balance", "adv_reports"),
        ("/api/reports/profit-loss", "adv_reports"),
        ("/api/reports/balance-sheet", "adv_reports"),
        ("/api/audit", "audit"),
        ("/api/activity", "audit"),
    )
    GATE_FREE = ("/api/ping", "/api/login", "/api/logout", "/api/meta",
                 "/api/license")

    # دسترسی‌های قابل واگذاری به هر کاربر (نام‌ها در رابط کاربری هم همین‌اند)
    PERM_KEYS = ("invoices", "battery", "inventory", "accounting",
                 "cheques", "defs", "reports")
    ALL_PERMS = tuple(PERM_KEYS)

    def ok(data=None, **kw):
        payload = {"ok": True}
        if data is not None:
            payload["data"] = data
        payload.update(kw)
        return jsonify(payload)

    def err(msg, code=400):
        return jsonify({"ok": False, "error": str(msg)}), code

    def user():
        return session.get("username", "")

    def user_row():
        return db.one("SELECT * FROM users WHERE username=? AND active=1", (user(),))

    def is_admin():
        return session.get("role") == "admin"

    def login_required(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("username"):
                return err("ابتدا وارد سامانه شوید", 401)
            return fn(*a, **kw)
        return wrapper

    def admin_required(fn):
        """فقط کاربران با نقش مدیر (و همیشه در نسخهٔ مدیر)."""
        @wraps(fn)
        @login_required
        def wrapper(*a, **kw):
            if not is_admin():
                return err("این بخش فقط برای مدیر سیستم است", 403)
            return fn(*a, **kw)
        return wrapper

    def premium_required(feature):
        """محافظ قابلیت‌های پرمیوم؛ در نسخهٔ مدیر همیشه باز است."""
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                if not lic.has(feature):
                    name = licensing.FEATURES.get(feature, feature)
                    return err("این بخش نیازمند نسخهٔ پرمیوم است: {}".format(name),
                               402)
                return fn(*a, **kw)
            return wrapper
        return deco

    def body():
        return request.get_json(silent=True) or {}

    # ------------------------------------------------------- دروازهٔ لایسنس
    @app.before_request
    def _license_gate():
        """پیش از هر درخواست API، اعتبار لایسنس بررسی می‌شود."""
        path = request.path
        if not path.startswith("/api/"):
            return None
        if any(path == p or path.startswith(p) for p in GATE_FREE):
            return None
        info = lic.info()
        if not info["valid"]:
            return jsonify({"ok": False, "license_required": True,
                            "error": info["message"] or "برنامه فعال نشده است",
                            "license": info}), 403
        return None

    # ------------------------------------------------------------------ عمومی
    @app.route("/")
    def index():
        """صفحهٔ اصلی؛ اسپرایت آیکون‌های SVG درون آن جای‌گذاری می‌شود."""
        web = resource_path("web")
        with open(os.path.join(web, "index.html"), encoding="utf-8") as f:
            html = f.read()
        try:
            with open(os.path.join(web, "icons.svg"), encoding="utf-8") as f:
                sprite = f.read()
        except OSError:
            sprite = ""
        if "<!--ICON_SPRITE-->" in html:
            html = html.replace("<!--ICON_SPRITE-->", sprite)
        return app.response_class(html, mimetype="text/html")

    MIME = {
        ".html": "text/html", ".css": "text/css",
        ".js": "application/javascript", ".json": "application/json",
        ".svg": "image/svg+xml", ".png": "image/png",
        ".jpg": "image/jpeg", ".ico": "image/x-icon",
        ".woff": "font/woff", ".woff2": "font/woff2",
    }

    @app.route("/<path:filename>")
    def static_files(filename):
        resp = send_from_directory(resource_path("web"), filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext in MIME:
            resp.headers["Content-Type"] = MIME[ext] + "; charset=utf-8"
        return resp

    @app.route("/api/ping")
    def ping():
        return ok({"app": APP_ID, "mode": mode, "today": jdate.today_str(),
                   "weekday": jdate.weekday_name(jdate.today_str())})

    MAX_FAILS = 5
    LOCK_MINUTES = 5

    def _lock_left(row):
        """دقیقه‌های باقی‌ماندهٔ قفل ورود (۰ اگر قفل نباشد)."""
        raw = str((row or {}).get("locked_until") or "")
        if not raw:
            return 0
        try:
            until = datetime.fromisoformat(raw)
        except ValueError:
            return 0
        left = (until - datetime.now()).total_seconds() / 60.0
        return int(left + 0.999) if left > 0 else 0

    @app.route("/api/login", methods=["POST"])
    def login():
        d = body()
        uname = str(d.get("username") or "").strip()
        row = db.user_by_name(uname)
        if row is not None:
            left = _lock_left(row)
            if left:
                return err("به دلیل تلاش‌های ناموفق، ورود این کاربر تا {} دقیقه"
                           " دیگر قفل است".format(left), 423)
        if not row or not row.get("active") or \
                not verify_password(d.get("password", ""), row["password"]):
            if row is not None:
                fails = int(row.get("failed_attempts") or 0) + 1
                upd = {"failed_attempts": fails}
                if fails >= MAX_FAILS:
                    upd["locked_until"] = (datetime.now()
                                           + timedelta(minutes=LOCK_MINUTES))
                    upd["failed_attempts"] = 0
                    logic.log(uname, "قفل موقت ورود پس از {} تلاش ناموفق".format(fails))
                db.update("users", row["id"], upd)
            return err("نام کاربری یا گذرواژه نادرست است", 401)
        session.clear()
        session["username"] = row["username"]
        session["role"] = row["role"]
        db.update("users", row["id"], {"failed_attempts": 0, "locked_until": "",
                                        "last_login": datetime.now().strftime(
                                            "%Y-%m-%d %H:%M:%S"),
                                        "last_ip": request.remote_addr or ""})
        logic.log(row["username"], "ورود به سامانه")
        return ok({"username": row["username"], "full_name": row["full_name"],
                   "role": row["role"],
                   "perms": user_perms(row), "license": lic.info()})

    def user_perms(row):
        """فهرست دسترسی‌های ویژهٔ کاربر (خالی = پیش‌فرض نقش)."""
        raw = (row or {}).get("perms") or ""
        try:
            data = json.loads(raw) if raw else []
        except ValueError:
            return []
        return [p for p in data if p in PERM_KEYS] if isinstance(data, list) else []

    @app.route("/api/logout", methods=["POST"])
    def logout():
        logic.log(user(), "خروج از سامانه")
        session.clear()
        return ok()

    @app.route("/api/meta")
    @login_required
    def meta():
        row = user_row() or {}
        return ok({
            "settings": db.all_settings(),
            "groups": db.rows("SELECT * FROM product_groups ORDER BY name"),
            "units": db.rows("SELECT * FROM units ORDER BY name"),
            "warehouses": db.rows("SELECT * FROM warehouses ORDER BY id"),
            "accounts": db.rows("SELECT * FROM accounts ORDER BY code"),
            "today": jdate.today_str(),
            "weekday": jdate.weekday_name(jdate.today_str()),
            "kinds": KINDS,
            "mode": mode,
            "license": lic.info(),
            "features": licensing.FEATURES,
            "perm_keys": list(ALL_PERMS),
            "user": {"username": user(), "role": session.get("role", ""),
                     "full_name": row.get("full_name", ""),
                     "perms": user_perms(row)},
        })

    # ----------------------------------------------------------------- لایسنس
    # این دو صفحه بدون ورود هم باز است تا کاربر جدید بتواند اول فعال‌سازی کند.
    @app.route("/api/license")
    def license_status():
        return ok(lic.info())

    @app.route("/api/license/activate", methods=["POST"])
    def license_activate():
        d = body()
        text = d.get("key") or d.get("text") or ""
        if not text.strip():
            return err("متن لایسنس را وارد کنید")
        res = lic.activate(text)
        if not res["ok"]:
            return err(res["error"], 400)
        return ok(res["license"], message="برنامه با موفقیت فعال شد")

    @app.route("/api/license/manage")
    @admin_required
    def license_list():
        return ok({
            "license": lic.info(),
            "can_issue": lic.can_issue,
            "editions": {k: {"label": v["label"],
                             "features": list(v["features"]),
                             "seats": licensing.EDITION_MAX_SEATS.get(k, 1)}
                         for k, v in licensing.EDITIONS.items()},
            "features": licensing.FEATURES,
            "issued": db.rows("SELECT * FROM licenses ORDER BY id DESC LIMIT 500"),
            "events": db.rows("SELECT * FROM license_events ORDER BY id DESC LIMIT 100"),
        })

    @app.route("/api/license/issue", methods=["POST"])
    @admin_required
    def license_issue():
        res = lic.issue(body())
        if not res["ok"]:
            return err(res["error"], 400)
        logic.audit(user(), "صدور لایسنس", "license", res["id"],
                    "{} — {}".format(res["lic_id"], res["payload"]["customer"]))
        return ok(res, message="لایسنس صادر شد")

    @app.route("/api/license/issued/<int:lid>")
    @admin_required
    def license_download(lid):
        row = db.one("SELECT * FROM licenses WHERE id=?", (lid,))
        if not row:
            return err("لایسنس یافت نشد", 404)
        payload, sig = licensing.decode_license(row["key_text"])
        text = licensing.license_file_text(payload, sig, customer=row["customer"])
        name = "{}-{}.key".format(row["lic_id"], (row["customer"] or "license").strip())
        name = "".join(ch for ch in name if ch not in '\\/:*?"<>|').replace(" ", "_")
        return send_file(io.BytesIO(text.encode("utf-8")), as_attachment=True,
                         download_name=name, mimetype="application/json")

    @app.route("/api/license/issued/<int:lid>", methods=["DELETE"])
    @admin_required
    def license_revoke(lid):
        row = db.one("SELECT * FROM licenses WHERE id=?", (lid,))
        if not row:
            return err("لایسنس یافت نشد", 404)
        db.delete("licenses", lid)
        logic.audit(user(), "حذف رکورد لایسنس", "license", lid, row["lic_id"])
        return ok()

    @app.route("/api/license/machine")
    @admin_required
    def license_machine():
        """کد دستگاه همین رایانه (برای صدور لایسنس مقید)."""
        return ok({"machine_code": lic.machine_code(),
                   "fingerprint": lic.fingerprint})

    # --------------------------------------------------- لایسنس آنلاین
    # این نشانی‌ها بدون ورود هم باز است (کاربر باید اول بتواند فعال کند).
    @app.route("/api/license/cloud")
    def license_cloud_status():
        """وضعیت ارتباط با سرور لایسنس + وضعیت لایسنس همین نصب."""
        # توکن‌ها هرگز به رابط کاربری نمی‌روند؛ فقط «دارد/ندارد» گفته می‌شود.
        return ok({"license": lic.info(), "cloud": lic.cloud_info(),
                   "settings": {k: v for k, v in lic.cloud_settings().items()
                                if k not in ("token", "admin")},
                   "has_token": bool(lic.cloud_settings()["token"]),
                   "has_admin_token": bool(lic.cloud_settings()["admin"]),
                   "admin_panel": lic.cloud_admin_ready(),
                   "mode": lic.mode})

    @app.route("/api/license/cloud/request", methods=["POST"])
    def license_cloud_request():
        """ثبت درخواست فعال‌سازی در سرور (تأیید توسط فروشنده در بات بله).

        از خود نشانی سرور نام و تلفن مشتری به سرور می‌رود؛ نتیجه در بات برای
        فروشنده می‌آید.
        """
        if not lic.cloud_configured():
            return err("نشانی سرور لایسنس تنظیم نشده است.", 400)
        d = body()
        name = str(d.get("name") or db.get_setting("company_name", "") or "").strip()
        phone = str(d.get("phone") or "").strip()
        note = str(d.get("note") or "").strip()
        res = lic.request_activation(name, phone, note)
        if not res["ok"]:
            return err(res["message"], 400)
        return ok(res, message=res["message"])

    @app.route("/api/license/cloud/poll", methods=["GET", "POST"])
    def license_cloud_poll():
        """بررسی فوری با سرور؛ اگر فروشنده تأیید کرده باشد لایسنس نصب می‌شود."""
        res = lic.cloud_check()
        payload = {
            "checked": bool(res.get("ok")),
            "reason": str(res.get("reason") or ""),
            "status": str(res.get("status") or ""),
            "message": str(res.get("message") or ""),
            "cloud": res.get("cloud") or lic.cloud_info(),
            "license": res.get("license") or lic.info(),
        }
        return ok(payload, message=payload["message"])

    @app.route("/api/license/cloud/settings", methods=["POST"])
    @admin_required
    def license_cloud_settings():
        """تنظیم نشانی سرور لایسنس و پارامترهای بررسی (فقط مدیر)."""
        d = body()
        allowed = ("license_server", "license_client_token",
                   "license_check_hours", "license_grace_days",
                   "license_insecure")
        changed = [k for k in allowed if k in d]
        if not changed:
            return err("هیچ تنظیمی فرستاده نشد", 400)
        for key in changed:
            db.set_setting(key, str(d[key]).strip())
        logic.audit(user(), "تغییر تنظیمات لایسنس", "settings", 0,
                    ", ".join(changed))
        return ok({"cloud": lic.cloud_info(), "license": lic.info()},
                  message="تنظیمات لایسنس ذخیره شد")

    @app.route("/api/license/requests")
    @admin_required
    def license_requests():
        """فهرست درخواست‌های در انتظار تأیید (پنل برنامهٔ فروشنده)."""
        res = lic.cloud_requests()
        if not res["ok"]:
            return err(res["message"], 400)
        return ok(res["data"])

    @app.route("/api/license/requests/<int:rid>/decide", methods=["POST"])
    @admin_required
    def license_decide(rid):
        """تأیید/رد درخواست از داخل برنامه؛ نتیجه با بات بله یکی می‌شود."""
        d = body()
        action = str(d.get("action") or "").strip().lower()
        if action not in ("approve", "deny"):
            return err("عملیات نامعتبر است (approve یا deny)")
        days = None
        raw_days = str(d.get("days") or "").strip()
        if raw_days:
            try:
                days = max(0, int(raw_days))
            except ValueError:
                return err("تعداد روز نامعتبر است")
        try:
            seats = max(0, int(d.get("seats") or 0))
        except (TypeError, ValueError):
            return err("تعداد کاربر نامعتبر است")
        res = lic.cloud_decide(rid, action,
                               edition=str(d.get("edition") or "").strip(),
                               seats=seats, days=days,
                               note=str(d.get("note") or "").strip())
        if not res["ok"]:
            return err(res["message"], 400)
        data = res["data"] or {}
        logic.audit(user(), "بررسی درخواست لایسنس", "license", rid,
                    "{} — {}".format(action, data.get("lic_id") or ""))
        return ok(data, message=data.get("message") or "انجام شد")

    @app.route("/api/dashboard")
    @login_required
    def dashboard():
        today = jdate.today_str()
        m_from, m_to = jdate.month_range(today)
        y_from, y_to = jdate.year_range(today)
        sales_today = db.scalar(
            "SELECT COALESCE(SUM(total),0) FROM invoices WHERE kind='sale' AND date=?",
            (today,), 0)
        sales_month = db.scalar(
            "SELECT COALESCE(SUM(total),0) FROM invoices WHERE kind='sale' "
            "AND date>=? AND date<=?", (m_from, m_to), 0)
        sales_year = db.scalar(
            "SELECT COALESCE(SUM(total),0) FROM invoices WHERE kind='sale' "
            "AND date>=? AND date<=?", (y_from, y_to), 0)
        purchase_month = db.scalar(
            "SELECT COALESCE(SUM(total),0) FROM invoices WHERE kind='purchase' "
            "AND date>=? AND date<=?", (m_from, m_to), 0)
        scrap = db.scrap_stock()
        debtors = logic.debtors()
        balances = {b["account"]: b["balance"] for b in logic.account_balances()}
        return ok({
            "sales_today": sales_today, "sales_month": sales_month,
            "sales_year": sales_year, "purchase_month": purchase_month,
            "cash": balances.get("صندوق", 0) + balances.get("بانک", 0),
            "receivable": sum(d["balance"] for d in debtors if d["balance"] > 0),
            "debtor_count": len([d for d in debtors if d["balance"] > 0]),
            "stock_value": db.scalar(
                "SELECT COALESCE(SUM((qty_in-qty_out)*unit_cost),0) FROM stock_moves"),
            "product_count": db.scalar("SELECT COUNT(*) FROM products WHERE active=1"),
            "party_count": db.scalar("SELECT COUNT(*) FROM parties WHERE active=1"),
            "scrap": scrap,
            "cheque_due": logic.cheque_due(15)[:10],
            "low_stock": [r for r in logic.inventory_report() if r["low"]][:10],
            "recent": db.rows("SELECT * FROM invoices ORDER BY id DESC LIMIT 8"),
            "low_scrap": False,
        })

    # ------------------------------------------------------------------ اشخاص
    @app.route("/api/parties")
    @login_required
    def parties_list():
        q = request.args.get("q", "")
        rows = db.rows(
            "SELECT * FROM parties WHERE (name LIKE ? OR phone LIKE ? OR mobile LIKE ? "
            "OR code LIKE ?) ORDER BY name", tuple(["%{}%".format(q)] * 4))
        for r in rows:
            r["balance"] = logic.party_balance(r["id"])
        return ok(rows)

    @app.route("/api/parties", methods=["POST"])
    @login_required
    def parties_create():
        d = body()
        if not d.get("name"):
            return err("نام شخص الزامی است")
        d.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        d["opening_balance"] = float(d.get("opening_balance") or 0)
        pid = db.insert("parties", d)
        logic.audit(user(), "ثبت شخص", "party", pid, d.get("name", ""))
        return ok({"id": pid})

    @app.route("/api/parties/<int:pid>", methods=["PUT"])
    @login_required
    def parties_update(pid):
        d = body()
        d.pop("id", None)
        d.pop("balance", None)
        d["opening_balance"] = float(d.get("opening_balance") or 0)
        db.update("parties", pid, d)
        logic.audit(user(), "اصلاح شخص", "party", pid, d.get("name", ""))
        return ok()

    @app.route("/api/parties/<int:pid>", methods=["DELETE"])
    @login_required
    def parties_delete(pid):
        used = db.scalar("SELECT COUNT(*) FROM invoices WHERE party_id=?", (pid,), 0)
        if used:
            return err("این شخص در فاکتورها استفاده شده و قابل حذف نیست")
        db.delete("parties", pid)
        logic.audit(user(), "حذف شخص", "party", pid, "")
        return ok()

    @app.route("/api/parties/<int:pid>/ledger")
    @login_required
    def parties_ledger(pid):
        p = db.one("SELECT * FROM parties WHERE id=?", (pid,))
        if not p:
            return err("شخص یافت نشد", 404)
        return ok({"party": p, "ledger": logic.party_ledger(pid),
                   "balance": logic.party_balance(pid)})

    # ------------------------------------------------------------------ کالاها
    @app.route("/api/products")
    @login_required
    def products_list():
        q = request.args.get("q", "")
        only_battery = request.args.get("battery")
        sql = ("SELECT p.*, g.name AS group_name, u.name AS unit_name, "
               "(SELECT COALESCE(SUM(qty_in-qty_out),0) FROM stock_moves m "
               "WHERE m.product_id=p.id) AS stock FROM products p "
               "LEFT JOIN product_groups g ON g.id=p.group_id "
               "LEFT JOIN units u ON u.id=p.unit_id WHERE p.active=1 "
               "AND (p.name LIKE ? OR p.code LIKE ? OR p.barcode LIKE ? OR p.brand LIKE ?)")
        params = ["%{}%".format(q)] * 4
        if only_battery == "1":
            sql += " AND p.is_battery=1"
        sql += " ORDER BY p.name"
        return ok(db.rows(sql, tuple(params)))

    @app.route("/api/products", methods=["POST"])
    @login_required
    def products_create():
        d = body()
        if not d.get("name"):
            return err("نام کالا الزامی است")
        d.setdefault("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        for k in ("purchase_price", "sale_price", "wholesale_price", "reorder_level",
                  "capacity_ah"):
            d[k] = float(d.get(k) or 0)
        d["warranty_months"] = int(float(d.get("warranty_months") or 0))
        pid = db.insert("products", d)
        logic.audit(user(), "ثبت کالا", "product", pid, d.get("name", ""))
        opening = float(d.get("opening_stock") or 0)
        if opening:
            wh = d.get("warehouse_id") or db.scalar(
                "SELECT id FROM warehouses ORDER BY is_default DESC LIMIT 1", (), None)
            logic.stock_adjust(d.get("opening_date") or jdate.today_str(), pid, wh,
                               opening, d.get("purchase_price"), "in", user(),
                               "موجودی اول دوره")
        return ok({"id": pid})

    @app.route("/api/products/<int:pid>", methods=["PUT"])
    @login_required
    def products_update(pid):
        d = body()
        d.pop("id", None)
        for k in ("stock", "group_name", "unit_name"):
            d.pop(k, None)
        for k in ("purchase_price", "sale_price", "wholesale_price", "reorder_level",
                  "capacity_ah"):
            if k in d:
                d[k] = float(d.get(k) or 0)
        if "warranty_months" in d:
            d["warranty_months"] = int(float(d.get("warranty_months") or 0))
        db.update("products", pid, d)
        logic.audit(user(), "اصلاح کالا", "product", pid, d.get("name", ""))
        return ok()

    @app.route("/api/products/<int:pid>", methods=["DELETE"])
    @login_required
    def products_delete(pid):
        used = db.scalar("SELECT COUNT(*) FROM invoice_items WHERE product_id=?",
                         (pid,), 0)
        if used:
            db.update("products", pid, {"active": 0})
            logic.audit(user(), "غیرفعال‌سازی کالا", "product", pid, "")
        else:
            db.delete("products", pid)
            logic.audit(user(), "حذف کالا", "product", pid, "")
        return ok()

    @app.route("/api/groups", methods=["GET", "POST"])
    @login_required
    def groups():
        if request.method == "POST":
            d = body()
            if not d.get("name"):
                return err("نام گروه الزامی است")
            try:
                gid = db.insert("product_groups", {"name": d["name"],
                                                   "note": d.get("note", "")})
            except sqlite3.IntegrityError:
                return err("این گروه قبلاً ثبت شده است")
            return ok({"id": gid})
        return ok(db.rows("SELECT * FROM product_groups ORDER BY name"))

    @app.route("/api/groups/<int:gid>", methods=["DELETE"])
    @login_required
    def groups_delete(gid):
        db.delete("product_groups", gid)
        return ok()

    @app.route("/api/units", methods=["GET", "POST"])
    @login_required
    def units():
        if request.method == "POST":
            d = body()
            if not d.get("name"):
                return err("نام واحد الزامی است")
            try:
                uid = db.insert("units", {"name": d["name"]})
            except sqlite3.IntegrityError:
                return err("این واحد قبلاً ثبت شده است")
            return ok({"id": uid})
        return ok(db.rows("SELECT * FROM units ORDER BY name"))

    @app.route("/api/units/<int:uid>", methods=["DELETE"])
    @login_required
    def units_delete(uid):
        db.delete("units", uid)
        return ok()

    @app.route("/api/warehouses", methods=["GET", "POST"])
    @login_required
    @premium_required("multi_warehouse")
    def warehouses():
        if request.method == "POST":
            d = body()
            if not d.get("name"):
                return err("نام انبار الزامی است")
            wid = db.insert("warehouses", {"name": d["name"],
                                           "location": d.get("location", "")})
            return ok({"id": wid})
        return ok(db.rows("SELECT * FROM warehouses ORDER BY id"))

    @app.route("/api/warehouses/<int:wid>", methods=["DELETE"])
    @login_required
    @premium_required("multi_warehouse")
    def warehouses_delete(wid):
        db.delete("warehouses", wid)
        return ok()

    # ------------------------------------------------------------------ انبار
    @app.route("/api/stock/moves")
    @login_required
    def stock_moves():
        pid = request.args.get("product_id")
        wid = request.args.get("warehouse_id")
        sql = ("SELECT m.*, p.name AS product_name, w.name AS warehouse_name "
               "FROM stock_moves m LEFT JOIN products p ON p.id=m.product_id "
               "LEFT JOIN warehouses w ON w.id=m.warehouse_id WHERE 1=1")
        params = []
        if pid:
            sql += " AND m.product_id=?"
            params.append(pid)
        if wid:
            sql += " AND m.warehouse_id=?"
            params.append(wid)
        sql += " ORDER BY m.date DESC, m.id DESC LIMIT 500"
        rows = db.rows(sql, tuple(params))
        bal = 0
        for r in reversed(rows):
            bal += (r["qty_in"] or 0) - (r["qty_out"] or 0)
            r["balance"] = bal
        return ok(rows)

    @app.route("/api/stock/adjust", methods=["POST"])
    @login_required
    @premium_required("multi_warehouse")
    def stock_adjust():
        d = body()
        try:
            logic.stock_adjust(d.get("date") or jdate.today_str(),
                               int(d.get("product_id")), d.get("warehouse_id"),
                               float(d.get("qty") or 0), d.get("unit_cost"),
                               d.get("direction", "in"), user(),
                               d.get("description", ""))
        except (ValueError, TypeError) as e:
            return err(e)
        return ok()

    @app.route("/api/stock/transfer", methods=["POST"])
    @login_required
    @premium_required("multi_warehouse")
    def stock_transfer():
        d = body()
        try:
            logic.transfer(d.get("date") or jdate.today_str(),
                           int(d.get("product_id")), d.get("src"), d.get("dst"),
                           float(d.get("qty") or 0), user(), d.get("description", ""))
        except (ValueError, TypeError) as e:
            return err(e)
        return ok()

    @app.route("/api/stock/levels")
    @login_required
    def stock_levels():
        return ok(db.rows(
            "SELECT m.product_id, p.name AS product_name, m.warehouse_id, "
            "w.name AS warehouse_name, COALESCE(SUM(m.qty_in-m.qty_out),0) AS qty "
            "FROM stock_moves m LEFT JOIN products p ON p.id=m.product_id "
            "LEFT JOIN warehouses w ON w.id=m.warehouse_id "
            "GROUP BY m.product_id, m.warehouse_id ORDER BY p.name"))

    # ------------------------------------------------------------------ فاکتورها
    @app.route("/api/invoices")
    @login_required
    def invoices_list():
        kind = request.args.get("kind", "")
        q = request.args.get("q", "")
        df = request.args.get("from", "")
        dt = request.args.get("to", "")
        sql = ("SELECT i.*, p.name AS party_name FROM invoices i "
               "LEFT JOIN parties p ON p.id=i.party_id WHERE 1=1")
        params = []
        if kind:
            sql += " AND i.kind=?"
            params.append(kind)
        if df:
            sql += " AND i.date>=?"
            params.append(df)
        if dt:
            sql += " AND i.date<=?"
            params.append(dt)
        if q:
            sql += " AND (i.number LIKE ? OR p.name LIKE ?)"
            params += ["%{}%".format(q)] * 2
        sql += " ORDER BY i.date DESC, i.id DESC LIMIT 1000"
        return ok(db.rows(sql, tuple(params)))

    @app.route("/api/invoices/<int:iid>")
    @login_required
    def invoice_get(iid):
        inv = db.one("SELECT * FROM invoices WHERE id=?", (iid,))
        if not inv:
            return err("فاکتور یافت نشد", 404)
        items = db.rows(
            "SELECT ii.*, p.name AS product_name, p.brand, p.amperage FROM invoice_items ii "
            "LEFT JOIN products p ON p.id=ii.product_id WHERE ii.invoice_id=?", (iid,))
        return ok({"invoice": inv, "items": items,
                   "journal": db.rows(
                       "SELECT * FROM journals WHERE ref_type=? AND ref_id=?",
                       (inv["kind"], iid))})

    @app.route("/api/invoices", methods=["POST"])
    @login_required
    def invoice_create():
        d = body()
        try:
            iid = logic.save_invoice(d, user())
        except (ValueError, TypeError) as e:
            return err(e)
        return ok({"id": iid})

    @app.route("/api/invoices/<int:iid>", methods=["PUT"])
    @login_required
    def invoice_update(iid):
        d = body()
        try:
            logic.save_invoice(d, user(), invoice_id=iid)
        except (ValueError, TypeError) as e:
            return err(e)
        return ok({"id": iid})

    @app.route("/api/invoices/<int:iid>", methods=["DELETE"])
    @login_required
    def invoice_delete(iid):
        try:
            logic.delete_invoice(iid, user())
        except ValueError as e:
            return err(e)
        return ok()

    @app.route("/api/invoices/next_number")
    @login_required
    def invoice_next_number():
        return ok({"number": logic.next_number(request.args.get("kind", "sale"))})

    # -------------------------------------------------------------- دریافت/پرداخت
    @app.route("/api/receipts", methods=["GET", "POST"])
    @login_required
    def receipts():
        if request.method == "POST":
            d = body()
            try:
                rid = logic.save_receipt(d, user())
            except (ValueError, TypeError) as e:
                return err(e)
            return ok({"id": rid})
        rows = db.rows(
            "SELECT r.*, p.name AS party_name FROM receipts r "
            "LEFT JOIN parties p ON p.id=r.party_id "
            "ORDER BY r.date DESC, r.id DESC LIMIT 500")
        return ok(rows)

    @app.route("/api/receipts/<int:rid>", methods=["DELETE"])
    @login_required
    def receipt_delete(rid):
        try:
            logic.delete_receipt(rid, user())
        except ValueError as e:
            return err(e)
        return ok()

    # ------------------------------------------------------------------- چک‌ها
    @app.route("/api/cheques", methods=["GET", "POST"])
    @login_required
    def cheques():
        if request.method == "POST":
            d = body()
            try:
                cid = logic.save_cheque(d, user())
            except (ValueError, TypeError) as e:
                return err(e)
            return ok({"id": cid})
        ctype = request.args.get("ctype", "")
        status = request.args.get("status", "")
        sql = ("SELECT c.*, p.name AS party_name FROM cheques c "
               "LEFT JOIN parties p ON p.id=c.party_id WHERE 1=1")
        params = []
        if ctype:
            sql += " AND c.ctype=?"
            params.append(ctype)
        if status:
            sql += " AND c.status=?"
            params.append(status)
        sql += " ORDER BY c.due_date, c.id"
        return ok(db.rows(sql, tuple(params)))

    @app.route("/api/cheques/<int:cid>", methods=["PUT", "DELETE"])
    @login_required
    def cheque_modify(cid):
        if request.method == "DELETE":
            logic.delete_cheque(cid, user())
            return ok()
        d = body()
        try:
            logic.save_cheque(d, user(), cheque_id=cid)
        except (ValueError, TypeError) as e:
            return err(e)
        return ok()

    # ------------------------------------------------------------------ ضایعات
    @app.route("/api/scrap", methods=["GET", "POST"])
    @login_required
    def scrap():
        if request.method == "POST":
            d = body()
            try:
                sid = logic.save_scrap(d, user())
            except (ValueError, TypeError) as e:
                return err(e)
            return ok({"id": sid})
        rows = db.rows(
            "SELECT s.*, p.name AS party_name FROM scrap_batteries s "
            "LEFT JOIN parties p ON p.id=s.party_id ORDER BY s.date DESC, s.id DESC")
        return ok(rows)

    @app.route("/api/scrap/<int:sid>", methods=["DELETE"])
    @login_required
    def scrap_delete(sid):
        jids = [x["id"] for x in db.rows(
            "SELECT id FROM journals WHERE ref_type='scrap' AND ref_id=?", (sid,))]
        for jid in jids:
            db.conn.execute("DELETE FROM journal_lines WHERE journal_id=?", (jid,))
            db.conn.execute("DELETE FROM journals WHERE id=?", (jid,))
        db.conn.execute("DELETE FROM party_tx WHERE ref_type='scrap' AND ref_id=?", (sid,))
        db.delete("scrap_batteries", sid)
        db.conn.commit()
        return ok()

    @app.route("/api/scrap/stock")
    @login_required
    def scrap_stock():
        return ok(db.scrap_stock())

    @app.route("/api/scrap/sales", methods=["GET", "POST"])
    @login_required
    def scrap_sales():
        if request.method == "POST":
            d = body()
            try:
                weight = float(d.get("weight_kg") or 0)
                sid = logic.save_scrap_sale(d, user())
                if weight:
                    logic.allocate_scrap_out(weight)
            except (ValueError, TypeError) as e:
                return err(e)
            return ok({"id": sid})
        return ok(db.rows(
            "SELECT s.*, p.name AS party_name FROM scrap_sales s "
            "LEFT JOIN parties p ON p.id=s.party_id ORDER BY s.date DESC, s.id DESC"))

    # ------------------------------------------------------------------ گارانتی
    @app.route("/api/serials")
    @login_required
    def serials():
        q = request.args.get("q", "")
        status = request.args.get("status", "")
        sql = ("SELECT s.*, p.name AS product_name, pa.name AS party_name "
               "FROM battery_serials s LEFT JOIN products p ON p.id=s.product_id "
               "LEFT JOIN parties pa ON pa.id=s.party_id WHERE "
               "(s.serial LIKE ? OR p.name LIKE ?)")
        params = ["%{}%".format(q)] * 2
        if status:
            sql += " AND s.status=?"
            params.append(status)
        sql += " ORDER BY s.id DESC LIMIT 500"
        rows = db.rows(sql, tuple(params))
        today = jdate.today_str()
        for r in rows:
            r["warranty_active"] = bool(
                r["warranty_end"] and jdate.diff_days(today, r["warranty_end"]) >= 0)
        return ok(rows)

    @app.route("/api/serials/claim", methods=["POST"])
    @login_required
    def serial_claim():
        d = body()
        try:
            logic.warranty_claim(int(d.get("serial_id")), user(), d.get("note", ""))
        except (ValueError, TypeError) as e:
            return err(e)
        return ok()

    @app.route("/api/serials/scrap", methods=["POST"])
    @login_required
    def serial_scrap():
        d = body()
        try:
            sid = logic.serial_to_scrap(int(d.get("serial_id")), d, user())
        except (ValueError, TypeError) as e:
            return err(e)
        return ok({"id": sid})

    # ------------------------------------------------------------------ یادداشت
    @app.route("/api/notes", methods=["GET", "POST"])
    @login_required
    def notes():
        if request.method == "POST":
            d = body()
            nid = db.insert("notes", {
                "title": d.get("title", ""), "body": d.get("body", ""),
                "remind_at": d.get("remind_at", ""), "done": 0,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            return ok({"id": nid})
        return ok(db.rows("SELECT * FROM notes ORDER BY done, remind_at, id DESC"))

    @app.route("/api/notes/<int:nid>", methods=["PUT", "DELETE"])
    @login_required
    def note_modify(nid):
        if request.method == "DELETE":
            db.delete("notes", nid)
            return ok()
        d = body()
        db.update("notes", nid, d)
        return ok()

    # ------------------------------------------------------------------ کاربران
    USER_COLS = ("id", "username", "full_name", "role", "active", "email",
                 "phone", "note", "perms", "last_login", "failed_attempts",
                 "locked_until", "created_at", "created_by")

    @app.route("/api/users", methods=["GET", "POST"])
    @admin_required
    def users():
        info = lic.info()
        if request.method == "POST":
            d = body()
            if not d.get("username") or not d.get("password"):
                return err("نام کاربری و گذرواژه الزامی است")
            # سهم کاربران: بدون قابلیت «بیش از یک کاربر» فقط یک کاربر فعال مجاز است
            if not lic.has("more_users") and db.active_user_count() >= 1:
                return err("افزودن کاربر بیشتر نیازمند نسخهٔ پرمیوم است"
                           " (قابلیت «{}»)".format(licensing.FEATURES["more_users"]), 402)
            if int(db.active_user_count() or 0) >= int(info.get("seats") or 1):
                return err("سقف کاربران این لایسنس {} نفر است".format(info.get("seats")), 402)
            perms = d.get("perms")
            if perms is None:
                perms = [] if d.get("role") == "admin" else list(ALL_PERMS)
            perms = [p for p in perms if p in PERM_KEYS]
            try:
                uid = db.insert("users", {
                    "username": d["username"],
                    "password": hash_password(d["password"]),
                    "full_name": d.get("full_name", ""),
                    "role": "admin" if d.get("role") == "admin" else "user",
                    "email": d.get("email", ""), "phone": d.get("phone", ""),
                    "note": d.get("note", ""),
                    "perms": json.dumps(perms, ensure_ascii=False),
                    "active": 1 if d.get("active", 1) else 0,
                    "created_by": user(),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            except sqlite3.IntegrityError:
                return err("این نام کاربری قبلاً ثبت شده است")
            logic.audit(user(), "ایجاد کاربر", "user", uid, d["username"])
            return ok({"id": uid})
        rows = db.rows("SELECT {} FROM users ORDER BY id".format(
            ", ".join(USER_COLS)))
        for r in rows:
            r["perms"] = user_perms(r)
            r["locked"] = bool(_lock_left(r))
        return ok(rows, seats=info.get("seats"), mode=mode)

    @app.route("/api/users/<int:uid>", methods=["PUT", "DELETE"])
    @admin_required
    def user_modify(uid):
        row = db.one("SELECT * FROM users WHERE id=?", (uid,))
        if not row:
            return err("کاربر یافت نشد", 404)
        if request.method == "DELETE":
            if uid == (db.scalar("SELECT MIN(id) FROM users", (), 0)):
                return err("کاربر مدیر اصلی قابل حذف نیست")
            if row["username"] == user():
                return err("نمی‌توانید حساب خودتان را حذف کنید")
            db.delete("users", uid)
            logic.audit(user(), "حذف کاربر", "user", uid, row["username"])
            return ok()
        d = body()
        upd = {}
        for k in ("full_name", "email", "phone", "note"):
            if k in d:
                upd[k] = str(d[k])
        if "role" in d:
            upd["role"] = "admin" if d["role"] == "admin" else "user"
        if "perms" in d and isinstance(d["perms"], list):
            upd["perms"] = json.dumps([p for p in d["perms"] if p in PERM_KEYS],
                                      ensure_ascii=False)
        if "active" in d:
            active = 1 if d["active"] else 0
            if not active and uid == (db.scalar("SELECT MIN(id) FROM users", (), 0)):
                return err("کاربر مدیر اصلی را نمی‌توان غیرفعال کرد")
            if active and not row["active"] and \
                    int(db.active_user_count() or 0) >= int(lic.info()["seats"] or 1):
                return err("سقف کاربران این لایسنس پر شده است", 402)
            upd["active"] = active
        if d.get("password"):
            if len(str(d["password"])) < 4:
                return err("گذرواژه باید حداقل ۴ نویسه باشد")
            upd["password"] = hash_password(d["password"])
        if "unlock" in d and d["unlock"]:
            upd["failed_attempts"] = 0
            upd["locked_until"] = ""
        db.update("users", uid, upd)
        logic.audit(user(), "اصلاح کاربر", "user", uid, row["username"])
        return ok()

    @app.route("/api/account/password", methods=["POST"])
    @login_required
    def change_password():
        d = body()
        u = db.one("SELECT * FROM users WHERE username=?", (user(),))
        if not verify_password(d.get("old", ""), u["password"]):
            return err("گذرواژه فعلی نادرست است")
        if len(d.get("new", "")) < 4:
            return err("گذرواژه جدید باید حداقل ۴ نویسه باشد")
        db.update("users", u["id"], {"password": hash_password(d["new"])})
        logic.log(user(), "تغییر گذرواژه")
        return ok()

    # ------------------------------------------------------------------ گزارش
    @app.route("/api/reports/trial-balance")
    @login_required
    @premium_required("adv_reports")
    def r_trial():
        return ok(logic.trial_balance())

    @app.route("/api/reports/profit-loss")
    @login_required
    @premium_required("adv_reports")
    def r_pl():
        return ok(logic.profit_loss(request.args.get("from"),
                                    request.args.get("to")))

    @app.route("/api/reports/balance-sheet")
    @login_required
    @premium_required("adv_reports")
    def r_bs():
        return ok(logic.balance_sheet(request.args.get("to")))

    @app.route("/api/reports/sales-summary")
    @login_required
    def r_sales():
        return ok(logic.sales_summary(request.args.get("from"),
                                      request.args.get("to")))

    @app.route("/api/reports/product-sales")
    @login_required
    def r_prod_sales():
        return ok(logic.product_sales(request.args.get("from"),
                                      request.args.get("to")))

    @app.route("/api/reports/inventory")
    @login_required
    def r_inv():
        return ok(logic.inventory_report())

    @app.route("/api/reports/debtors")
    @login_required
    def r_debtors():
        return ok(logic.debtors())

    @app.route("/api/reports/cheque-due")
    @login_required
    def r_chq():
        return ok(logic.cheque_due(int(request.args.get("days", 30))))

    @app.route("/api/reports/journal")
    @login_required
    def r_journal():
        df = request.args.get("from", "")
        dt = request.args.get("to", "")
        q = request.args.get("q", "")
        sql = ("SELECT j.*, (SELECT COALESCE(SUM(l.debit),0) FROM journal_lines l "
               "WHERE l.journal_id=j.id) AS sum_debit FROM journals j WHERE 1=1")
        params = []
        if df:
            sql += " AND j.date>=?"
            params.append(df)
        if dt:
            sql += " AND j.date<=?"
            params.append(dt)
        if q:
            sql += " AND (j.description LIKE ? OR j.number LIKE ?)"
            params += ["%{}%".format(q)] * 2
        sql += " ORDER BY j.date DESC, j.id DESC LIMIT 500"
        return ok(db.rows(sql, tuple(params)))

    @app.route("/api/journal/<int:jid>")
    @login_required
    def journal_get(jid):
        j = db.one("SELECT * FROM journals WHERE id=?", (jid,))
        if not j:
            return err("سند یافت نشد", 404)
        return ok({"journal": j,
                   "lines": db.rows("SELECT * FROM journal_lines WHERE journal_id=?", (jid,))})

    @app.route("/api/journal", methods=["POST"])
    @login_required
    def journal_create():
        d = body()
        lines = d.get("lines") or []
        clean = [(l.get("account", ""), float(l.get("debit") or 0),
                  float(l.get("credit") or 0), l.get("description", ""))
                 for l in lines if l.get("account")]
        deb = sum(l[1] for l in clean)
        cred = sum(l[2] for l in clean)
        if not clean:
            return err("سند باید حداقل یک ردیف داشته باشد")
        if abs(deb - cred) > 1:
            return err("سند تراز نیست (بدهکار: {}، بستانکار: {})".format(deb, cred))
        jid = logic.add_journal(d.get("date") or jdate.today_str(),
                                d.get("description", "سند دستی"), clean,
                                ref_type="manual", username=user())
        logic.audit(user(), "ثبت سند دستی", "journal", jid, d.get("description", ""))
        return ok({"id": jid})

    @app.route("/api/journal/<int:jid>", methods=["DELETE"])
    @login_required
    def journal_delete(jid):
        j = db.one("SELECT * FROM journals WHERE id=?", (jid,))
        if not j:
            return err("سند یافت نشد", 404)
        db.conn.execute("DELETE FROM journal_lines WHERE journal_id=?", (jid,))
        db.conn.execute("DELETE FROM journals WHERE id=?", (jid,))
        db.conn.commit()
        logic.audit(user(), "حذف سند", "journal", jid, j["number"])
        return ok()

    # ------------------------------------------------------------------ سیستم
    @app.route("/api/activity")
    @login_required
    @admin_required
    @premium_required("audit")
    def activity():
        return ok(db.rows(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT 300"))

    @app.route("/api/audit")
    @login_required
    @admin_required
    @premium_required("audit")
    def audit_list():
        return ok(db.rows("SELECT * FROM audit ORDER BY id DESC LIMIT 300"))

    @app.route("/api/settings", methods=["GET", "POST"])
    @admin_required
    def settings():
        if request.method == "POST":
            d = body()
            for k, v in d.items():
                db.set_setting(k, v)
            logic.audit(user(), "تغییر تنظیمات", "settings", 0, "")
            return ok()
        return ok(db.all_settings())

    @app.route("/api/search")
    @login_required
    def search():
        q = "%{}%".format(request.args.get("q", ""))
        res = {
            "parties": db.rows(
                "SELECT id, name, mobile FROM parties WHERE name LIKE ? LIMIT 10", (q,)),
            "products": db.rows(
                "SELECT id, name, brand, amperage FROM products WHERE name LIKE ? "
                "OR barcode LIKE ? LIMIT 10", (q, q)),
            "invoices": db.rows(
                "SELECT id, number, kind, date, total FROM invoices WHERE number LIKE ? "
                "LIMIT 10", (q,)),
        }
        return ok(res)

    # ---------------------------------------------- مدیریت پشتیبان‌ها
    def _safe_backup_name(name):
        """نام فایل پشتیبان را ایمن می‌کند (جلوگیری از خروج از پوشه)."""
        name = os.path.basename(str(name or "").strip())
        if not name or name.startswith(".") or not name.lower().endswith(".db"):
            return ""
        if "/" in name or "\\" in name or ".." in name:
            return ""
        return name

    def _backup_files(folder):
        rows = []
        try:
            names = os.listdir(folder)
        except OSError:
            return rows
        for name in names:
            path = os.path.join(folder, name)
            if not name.lower().endswith(".db") or not os.path.isfile(path):
                continue
            info = os.stat(path)
            rows.append({
                "name": name, "size": info.st_size,
                "at": datetime.fromtimestamp(info.st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"),
                "kind": "auto" if "-auto-" in name else (
                    "safety" if "before-restore" in name else "manual"),
            })
        rows.sort(key=lambda r: r["name"], reverse=True)
        return rows

    def _prune_backups(folder, keep):
        """نگه‌داشتن فقط `keep` نسخهٔ تازه‌تر (قدیمی‌ترها پاک می‌شوند)."""
        removed = []
        for row in _backup_files(folder)[keep:]:
            try:
                os.remove(os.path.join(folder, row["name"]))
                removed.append(row["name"])
            except OSError:
                pass
        return removed

    def _create_backup(tag="manual"):
        """نسخهٔ پشتیبان امن از پایگاه‌داده (بدون بستن برنامه)."""
        folder = backup_dir(db)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            return "", [], "پوشهٔ پشتیبان ساخته نشد: {}".format(exc)
        db.conn.commit()
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        name = "hesabdari-{}-{}.db".format(tag, stamp)
        dest = os.path.join(folder, name)
        try:
            source = sqlite3.connect(db_path)
            try:
                target = sqlite3.connect(dest)
                try:
                    source.backup(target)
                finally:
                    target.close()
            finally:
                source.close()
        except sqlite3.Error as exc:
            return "", [], "پشتیبان‌گیری ناموفق بود: {}".format(exc)
        removed = _prune_backups(folder, backup_keep(db))
        return name, removed, ""

    def _auto_backup_once():
        """پشتیبان خودکار هنگام بالا آمدن برنامه (اگر روشن باشد)."""
        try:
            if str(db.get_setting("backup_auto", "1")) != "1":
                return None
            if not lic.has("backup"):
                return None
        except Exception:                       # noqa: BLE001
            return None
        name, _removed, problem = _create_backup("auto")
        if problem:
            log_line("پشتیبان‌گیری خودکار: " + problem)
        else:
            log_line("پشتیبان خودکار ساخته شد: " + name)
        return name

    @app.route("/api/backups", methods=["GET", "POST"])
    @login_required
    @premium_required("backup")
    def backups():
        """فهرست/تنظیم/ساخت پشتیبان‌ها (پوشه قابل تغییر است)."""
        if request.method == "POST":
            d = body()
            if d.get("dir"):
                target = os.path.abspath(os.path.expanduser(str(d["dir"]).strip()))
                try:
                    os.makedirs(target, exist_ok=True)
                except OSError as exc:
                    return err("پوشهٔ پشتیبان ساخته نشد: {}".format(exc))
                if not install._usable(target):       # noqa: SLF001 - بررسی نوشتنی
                    return err("در این پوشه نمی‌توان نوشت؛ پوشهٔ دیگری انتخاب کنید")
                db.set_setting("backup_dir", target)
                logic.audit(user(), "تغییر پوشهٔ پشتیبان", "settings", 0, target)
            if d.get("keep") is not None:
                try:
                    db.set_setting("backup_keep", str(max(1, int(d["keep"]))))
                except (TypeError, ValueError):
                    return err("تعداد نسخه‌های نگه‌داری‌شده درست نیست")
            if d.get("auto") is not None:
                value = str(d["auto"]).strip().lower()
                db.set_setting("backup_auto",
                               "1" if value in ("1", "true", "on", "yes", "بله")
                               else "0")
            created = ""
            if d.get("create"):
                created, removed, problem = _create_backup("manual")
                if problem:
                    return err(problem)
                if removed:
                    log_line("پشتیبان‌های قدیمی پاک شدند: " + ", ".join(removed))
                logic.audit(user(), "پشتیبان‌گیری", "backup", 0, created)
            return ok({"dir": backup_dir(db), "files": _backup_files(backup_dir(db)),
                       "created": created, "keep": backup_keep(db),
                       "auto": db.get_setting("backup_auto", "1")})
        folder = backup_dir(db)
        return ok({"dir": folder, "files": _backup_files(folder),
                   "keep": backup_keep(db),
                   "auto": db.get_setting("backup_auto", "1")})

    @app.route("/api/backups/restore", methods=["POST"])
    @login_required
    @premium_required("backup")
    def backup_restore():
        """بازگرداندن یکی از نسخه‌های روی دیسک (قبلش از وضعیت فعلی نسخه می‌گیرد)."""
        name = _safe_backup_name(body().get("name"))
        if not name:
            return err("نام فایل پشتیبان درست نیست")
        folder = backup_dir(db)
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            return err("فایل پشتیبان پیدا نشد", 404)
        check = sqlite3.connect(path)
        try:
            check.execute("SELECT name FROM sqlite_master LIMIT 1")
        except sqlite3.Error:
            check.close()
            return err("فایل پشتیبان معتبر نیست")
        check.close()
        safety, _removed, problem = _create_backup("before-restore")
        if problem:
            return err("بازگشت انجام نشد؛ نسخهٔ امن ساخته نشد: {}".format(problem))
        logic.audit(user(), "بازگرداندن پشتیبان", "backup", 0, name)
        db.conn.close()
        shutil.copyfile(path, db_path)
        return ok({"message": "بازگردانی انجام شد؛ برنامه را دوباره اجرا کنید",
                   "safety": safety})

    @app.route("/api/backups/<name>", methods=["GET", "DELETE"])
    @login_required
    @premium_required("backup")
    def backup_item(name):
        """دریافت (دانلود) یا حذف یک فایل پشتیبان."""
        safe = _safe_backup_name(name)
        if not safe:
            return err("نام فایل پشتیبان درست نیست")
        path = os.path.join(backup_dir(db), safe)
        if not os.path.isfile(path):
            return err("فایل پشتیبان پیدا نشد", 404)
        if request.method == "DELETE":
            # ویندوز اگر فایل در حال دانلود باشد قفلش می‌کند؛ چند بار تلاش می‌کنیم.
            import time as _time
            problem = ""
            for attempt in range(3):
                try:
                    os.remove(path)
                    problem = ""
                    break
                except OSError as exc:
                    problem = str(exc)
                    _time.sleep(0.25 * (attempt + 1))
            if problem:
                return err("حذف ناموفق بود (فایل در حال استفاده است): {}".format(
                    problem))
            logic.audit(user(), "حذف پشتیبان", "backup", 0, safe)
            return ok({"files": _backup_files(backup_dir(db))})
        return send_file(path, as_attachment=True, download_name=safe,
                         mimetype="application/octet-stream")

    @app.route("/api/backup")
    @login_required
    @premium_required("backup")
    def backup():
        db.conn.commit()
        with open(db_path, "rb") as f:
            data = f.read()
        name = "hesabdari-backup-{}.db".format(jdate.today_str().replace("/", "-"))
        return send_file(io.BytesIO(data), as_attachment=True, download_name=name,
                         mimetype="application/octet-stream")

    @app.route("/api/restore", methods=["POST"])
    @login_required
    @premium_required("backup")
    def restore():
        f = request.files.get("file")
        if not f:
            return err("فایلی ارسال نشد")
        tmp = db_path + ".restore"
        f.save(tmp)
        try:
            test = sqlite3.connect(tmp)
            test.execute("SELECT name FROM sqlite_master LIMIT 1")
            test.close()
        except sqlite3.Error:
            os.remove(tmp)
            return err("فایل پشتیبان معتبر نیست")
        db.conn.close()
        shutil.move(tmp, db_path)
        return ok({"message": "بازیابی انجام شد؛ برنامه را دوباره اجرا کنید"})

    @app.route("/api/export/<kind>")
    @login_required
    @premium_required("backup")
    def export_csv(kind):
        import csv
        mapping = {
            "parties": "SELECT code,name,party_type,national_id,phone,mobile,address,city,opening_balance FROM parties",
            "products": "SELECT code,barcode,name,brand,amperage,purchase_price,sale_price,reorder_level FROM products",
            "invoices": "SELECT number,kind,date,subtotal,discount,tax,total FROM invoices",
            "inventory": ("SELECT p.name, p.brand, p.amperage, "
                          "(SELECT COALESCE(SUM(qty_in-qty_out),0) FROM stock_moves m "
                          "WHERE m.product_id=p.id) AS stock FROM products p"),
        }
        if kind not in mapping:
            abort(404)
        rows = db.rows(mapping[kind])
        buf = io.StringIO()
        w = csv.writer(buf)
        if rows:
            w.writerow(list(rows[0].keys()))
            for r in rows:
                w.writerow(list(r.values()))
        data = "\ufeff" + buf.getvalue()
        return send_file(io.BytesIO(data.encode("utf-8")), as_attachment=True,
                         download_name="{}-{}.csv".format(kind, jdate.today_str().replace("/", "-")),
                         mimetype="text/csv")

    @app.after_request
    def _no_store(resp):
        if resp.mimetype in NO_STORE_TYPES:
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        return resp

    @app.teardown_appcontext
    def _teardown(exc):
        pass

    # ------------------------------------------------- کارهای پس‌زمینه
    def _background_loop():
        """پشتیبان‌گیری خودکار + بررسی دوره‌ای لایسنس آنلاین.

        بررسی دوره‌ای همان چیزی است که «لغو از راه دور» را ممکن می‌کند؛
        فاصلهٔ آن با `license_check_hours` قابل تنظیم است.
        """
        import time as _time
        _time.sleep(8)                          # فرصت بالا آمدن برنامه
        try:
            _auto_backup_once()
        except Exception as exc:                # noqa: BLE001 - هرگز نباید بکشد
            log_line("پشتیبان‌گیری خودکار ناموفق بود: {!r}".format(exc))
        while True:
            try:
                if lic.cloud_configured():
                    res = lic.cloud_check()
                    if not res.get("ok"):
                        log_line("بررسی لایسنس آنلاین: {}".format(
                            res.get("message")))
            except Exception as exc:            # noqa: BLE001
                log_line("خطای بررسی لایسنس آنلاین: {!r}".format(exc))
            try:
                hours = lic.cloud_settings()["hours"]
            except Exception:                   # noqa: BLE001
                hours = 6
            _time.sleep(max(1, hours) * 3600)

    start_background(_background_loop)

    app.db = db
    app.logic = logic
    app.license = lic
    app.mode = mode
    # قلاب‌های آزمون/نگهداری: ساخت پشتیبان بدون درخواست HTTP
    app.create_backup = _create_backup
    app.auto_backup = _auto_backup_once
    return app
