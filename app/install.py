"""مسیر نصب، پوشهٔ داده، پوشهٔ پشتیبان و نشانی سرور لایسنس.

اینستالر (ویزارد نصب) سه فایل کوچک کنار فایل اجرایی می‌گذارد:

    data-dir.txt        ← پوشهٔ داده‌ها (پایگاه‌داده، لایسنس، تنظیمات)
    backup-dir.txt      ← پوشهٔ فایل‌های پشتیبان
    license-server.txt  ← نشانی سرور لایسنس آنلاین

ترتیب اولویت برای هر مقدار:

    ۱) متغیر محیطی (برای آزمون و اجرای دستی)
    ۲) مقداری که کاربر در خود برنامه تنظیم کرده (جدول settings)
    ۳) فایل کنار فایل اجرایی (نوشتهٔ اینستالر)
    ۴) پیش‌فرض امن

اگر پوشهٔ داده نوشتنی نباشد (مثلاً نصب در Program Files)، به پوشهٔ کاربر
برمی‌گردیم تا هیچ‌وقت برنامه بدون جای نوشتن نماند.
"""
import os
import sys
import tempfile

APP_NAME = "HesabDari-Saba"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR_FILE = "data-dir.txt"
BACKUP_DIR_FILE = "backup-dir.txt"
SERVER_FILE = "license-server.txt"
TOKEN_FILE = "client-token.txt"
ADMIN_TOKEN_FILE = "admin-token.txt"

DEFAULT_SERVER = os.environ.get("SABA_LICENSE_SERVER_DEFAULT", "")


def install_dir():
    """پوشهٔ نصب برنامه (کنار فایل اجرایی در نسخهٔ بسته‌بندی‌شده)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return BASE_DIR


def read_text_file(name):
    """مقدار یک خطی از فایل کنار فایل اجرایی (خالی اگر نبود)."""
    path = os.path.join(install_dir(), name)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _env(name):
    return (os.environ.get(name) or "").strip()


def _usable(path):
    """آیا می‌شود در این پوشه نوشت؟ (پوشه ساخته می‌شود اگر نباشد.)"""
    if not path:
        return False
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _user_fallback(folder):
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, APP_NAME, folder)


# `data_dir()` در هر درخواست API خوانده می‌شود (دروازهٔ لایسنس)؛ بنابراین
# نتیجه در همین پروسه نگه داشته می‌شود تا آزمون نوشتنی‌بودن پوشه در هر
# فراخوانی تکرار نشود.
_CACHE = {}


def clear_cache():
    """پاک‌کردن حافظهٔ مسیرها (برای آزمون‌ها و تغییرات دستی)."""
    _CACHE.clear()


def _resolve(kind, candidates, fallback):
    key = (kind, tuple(candidates))
    if key in _CACHE:
        return _CACHE[key]
    chosen = ""
    for path in candidates:
        if path and _usable(path):
            chosen = path
            break
    if not chosen:
        os.makedirs(fallback, exist_ok=True)
        chosen = fallback
    if len(_CACHE) > 64:                    # جلوگیری از رشد بی‌پایان
        _CACHE.clear()
    _CACHE[key] = chosen
    return chosen


def data_dir():
    """پوشهٔ داده‌ها؛ همیشه نوشتنی."""
    return _resolve("data", [
        _env("SABA_DATA_DIR"),
        read_text_file(DATA_DIR_FILE),
        os.path.join(install_dir(), "data"),
        os.path.join(os.environ.get("APPDATA") or "", APP_NAME, "data"),
        _user_fallback("data"),
    ], os.path.join(tempfile.gettempdir(), APP_NAME, "data"))


def backup_dir(settings_value=""):
    """پوشهٔ پشتیبان‌ها؛ پیش‌فرض: زیرپوشهٔ backups در پوشهٔ داده."""
    return _resolve("backup", [
        _env("SABA_BACKUP_DIR"),
        settings_value or "",
        read_text_file(BACKUP_DIR_FILE),
        os.path.join(data_dir(), "backups"),
    ], os.path.join(tempfile.gettempdir(), APP_NAME, "backups"))


def license_server(settings_value=""):
    """نشانی سرور لایسنس آنلاین (خالی = فقط لایسنس دستی)."""
    for value in (_env("SABA_LICENSE_SERVER"), settings_value or "",
                  read_text_file(SERVER_FILE), DEFAULT_SERVER):
        value = (value or "").strip().rstrip("/")
        if value:
            return value
    return ""


def client_token(settings_value=""):
    """کلید نرم‌افزاری کلاینت (اختیاری؛ اگر سرور تنظیم کرده باشد)."""
    for value in (_env("SABA_CLIENT_TOKEN"), settings_value or "",
                  read_text_file(TOKEN_FILE)):
        value = (value or "").strip()
        if value:
            return value
    return ""


def admin_token(settings_value=""):
    """توکن مدیر برای تأیید درخواست‌های لایسنس از داخل برنامهٔ فروشنده.

    فقط نسخهٔ فروشنده (Admin) آن را دارد؛ اگر خالی باشد، پنل تأیید در برنامه
    خاموش می‌ماند و تأییدها از بات بله انجام می‌شود.
    """
    for value in (_env("SABA_ADMIN_TOKEN"), settings_value or "",
                  read_text_file(ADMIN_TOKEN_FILE)):
        value = (value or "").strip()
        if value:
            return value
    return ""


def cloud_configured():
    return bool(license_server())
