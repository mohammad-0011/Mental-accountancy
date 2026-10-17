"""ساخت فایل‌های اجرایی ویندوز (exe) و فایل نصب با PyInstaller.

خروجی‌ها:

    dist/Mental accounting.exe              ← نسخهٔ کاربری (به مشتری داده می‌شود)
                                           فقط کلید عمومی لایسنس داخل آن است.
    dist/Mental admin accounting.exe        ← نسخهٔ مدیر (نزد شما می‌ماند)
                                           کلید خصوصی صدور لایسنس داخل آن است.
    dist/installer/Mental accounting Setup.exe        ← فایل نصب مشتری
    dist/installer/Mental admin accounting Setup.exe  ← فایل نصب نسخهٔ مدیر

فایل نصب، یک ویزارد گرافیکی است که مسیر نصب، پوشهٔ اطلاعات، پوشهٔ پشتیبان و
نشانی سرور لایسنس را از کاربر می‌پرسد و میان‌بر و حذف‌کننده می‌سازد؛ فایل
اجرایی برنامه داخل خودش بسته‌بندی شده است.

اجرا:
    python build.py                     # هر دو exe برنامه
    python build.py --user              # فقط نسخهٔ کاربری
    python build.py --admin             # فقط نسخهٔ مدیر
    python build.py --installer         # exeها + فایل نصب
    python build.py --installer-admin   # + فایل نصب نسخهٔ مدیر
    python build.py --installer-only    # فقط فایل نصب، از exeهای موجود در dist
    python build.py --server=https://license.example.com --installer

پیش‌نیاز: اگر app/license_keys خالی است، اول
    python tools/make_license_keys.py
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY_DIR = os.path.join(ROOT, "app", "license_keys")
PUBLIC_KEY = os.path.join(KEY_DIR, "root_public.key")
PRIVATE_KEY = os.path.join(KEY_DIR, "root_private.key")

BASE_HIDDEN = ["flask", "jinja2", "werkzeug", "sqlite3", "cryptography",
               "cryptography.hazmat.primitives.asymmetric.ed25519",
               "cryptography.hazmat.backends.openssl"]

INSTALLER_DIR = os.path.join(ROOT, "installer")
SETUP_PY = os.path.join(INSTALLER_DIR, "setup.py")
INSTALLER_OUT = os.path.join(ROOT, "dist", "installer")
ADMIN_EXE = "Mental admin accounting.exe"
USER_EXE = "Mental accounting.exe"
# آیکون ویندوز (نشان Mental)؛ با `python tools/make_icon.py` ساخته می‌شود.
ICON = os.path.join(ROOT, "assets", "app.ico")


def _spec(name, extra_data, hidden_extra):
    """پارامترهای خط فرمان PyInstaller برای یک نسخه."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", name,
        "--add-data", "{}{}web".format(os.path.join(ROOT, "web"), os.pathsep),
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build", name),
        "--specpath", os.path.join(ROOT, "build"),
    ]
    if os.path.isfile(ICON):
        cmd += ["--icon", ICON]
    else:
        print("⚠ آیکون پیدا نشد ({}); بدون آیکون ساخته می‌شود. "
              "برای ساخت: python tools/make_icon.py".format(ICON))
    for src, dest in extra_data:
        cmd += ["--add-data", "{}{}{}".format(src, os.pathsep, dest)]
    for h in BASE_HIDDEN + hidden_extra:
        cmd += ["--hidden-import", h]
    cmd.append(os.path.join(ROOT, "run.py"))
    return cmd


def build(label, name, extra_data, hidden_extra=()):
    print("\n=== ساخت {} ({}) ===".format(label, name))
    cmd = _spec(name, extra_data, list(hidden_extra))
    print("Running:", " ".join(cmd))
    rc = subprocess.call(cmd)
    if rc != 0:
        print("ساخت {} ناموفق بود (کد {}).".format(label, rc))
        return rc, None
    exe = os.path.join(ROOT, "dist", name + ".exe")
    print("✅ {} ساخته شد: {}  ({:.1f} مگابایت)".format(
        label, exe, os.path.getsize(exe) / 1024 / 1024))
    return 0, exe


def bundled_files(exe):
    """فهرست مسیرهای داده‌ای بسته‌بندی‌شده در exe (برای بازرسی امنیتی).

    اگر خواندن آرشیو ممکن نشد None برمی‌گردد؛ «نشد بررسی کرد» هرگز
    با «بررسی موفق» اشتباه گرفته نمی‌شود.
    """
    try:
        from PyInstaller.archive.readers import CArchiveReader
    except Exception:
        return None
    try:
        archive = CArchiveReader(exe)
        names = []
        for name, entry in archive.toc.items():
            if isinstance(entry, dict):
                pos = entry.get("dpos", entry.get("pos"))
            elif hasattr(entry, "dpos"):
                pos = entry.dpos
            else:
                pos = entry[0]
            if pos:
                names.append(str(name))
        return names
    except Exception:
        return None


def audit_user_build(exe):
    """تأیید اینکه کلید خصوصی صدور لایسنس در نسخهٔ کاربری نیست.

    نخست فهرست داده‌های داخل exe خوانده می‌شود؛ اگر خواندن آرشیو ممکن نبود،
    به جست‌وجوی متنی در بدنهٔ فایل برمی‌گردیم (PyInstaller به‌طور پیش‌فرض
    داده‌ها را فشرده نمی‌کند).
    """
    print("\n--- بازرسی امنیتی نسخهٔ کاربری ---")
    ok = True
    files = bundled_files(exe)
    if files is not None:
        norm = [f.replace("\\", "/") for f in files]
        private = [f for f in norm if "root_private" in f]
        public = [f for f in norm if "root_public" in f]
    else:
        print("⚠ فهرست آرشیو خوانده نشد؛ بررسی متنی روی بدنهٔ فایل انجام می‌شود.")
        private, public = [], []

    # جست‌وجوی «مقدار» کلیدها در بدنهٔ فایل (نه فقط نام فایل، چون نام
    # root_private در بایت‌کد سرور هم هست و نتیجهٔ مثبت کاذب می‌دهد).
    with open(exe, "rb") as f:
        blob = f.read()

    def _key_text(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""

    if not private and _key_text(PRIVATE_KEY).encode("ascii") in blob:
        private.append("«مقدار» کلید خصوصی در بدنهٔ exe پیدا شد")
    if not public and _key_text(PUBLIC_KEY).encode("ascii") in blob:
        public.append("«مقدار» کلید عمومی در بدنهٔ exe پیدا شد")

    if private:
        print("❌ کلید خصوصی داخل نسخهٔ کاربری است: {}".format(private))
        ok = False
    else:
        print("✅ هیچ کلید خصوصی داخل نسخهٔ کاربری نیست.")
    if public:
        print("✅ کلید عمومی لایسنس همراه برنامه است.")
    else:
        print("❌ کلید عمومی لایسنس همراه برنامه نیست؛ فعال‌سازی کار نمی‌کند.")
        ok = False
    return ok


def audit_admin_build(exe):
    """شاهد مثبت: کلید خصوصی باید **داخل** نسخهٔ مدیر باشد.

    این بررسی ثابت می‌کند روش بازرسی (لیست دارایی‌های exe) کار می‌کند؛
    وگرنه «نبود کلید خصوصی در نسخهٔ کاربری» یک نتیجهٔ بی‌اعتبار بود.
    """
    print("\n--- بازرسی امنیتی نسخهٔ مدیر ---")
    files = bundled_files(exe)
    if files is None:
        print("❌ فهرست آرشیو خوانده نشد؛ بازرسی امنیتی قابل اتکا نیست.")
        return False
    norm = [f.replace("\\", "/") for f in files]
    if any("root_private" in f for f in norm):
        print("✅ کلید خصوصی صدور لایسنس همراه نسخهٔ مدیر است.")
        return True
    print("❌ کلید خصوصی داخل نسخهٔ مدیر نیست؛ صدور لایسنس کار نمی‌کند.")
    return False


def build_installer(label, payload, name, server=""):
    """ساخت فایل نصب گرافیکی با بسته‌بندی فایل اجرایی برنامه درون آن."""
    print("\n=== ساخت {} ({}) ===".format(label, name))
    if not os.path.isfile(SETUP_PY):
        print("❌ فایل نصب‌کننده پیدا نشد: {}".format(SETUP_PY))
        return 1, None
    if not os.path.isfile(payload):
        print("❌ فایل اجرایی برنامه پیدا نشد: {}".format(payload))
        return 1, None

    data = [(payload, "payload")]
    if server:
        # نشانی سرور لایسنس داخل نصب‌کننده می‌رود تا هنگام نصب پیشنهاد شود.
        tmp = os.path.join(ROOT, "build", name, "license-server.txt")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(server.strip() + "\n")
        data.append((tmp, "payload"))

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", name,
        "--distpath", INSTALLER_OUT,
        "--workpath", os.path.join(ROOT, "build", name),
        "--specpath", os.path.join(ROOT, "build"),
    ]
    if os.path.isfile(ICON):
        cmd += ["--icon", ICON]
    for mod in ("tkinter", "tkinter.ttk", "tkinter.filedialog",
                "tkinter.messagebox", "winreg"):
        cmd += ["--hidden-import", mod]
    for src, dest in data:
        cmd += ["--add-data", "{}{}{}".format(src, os.pathsep, dest)]
    cmd.append(SETUP_PY)
    rc = subprocess.call(cmd)
    if rc != 0:
        print("ساخت {} ناموفق بود (کد {}).".format(label, rc))
        return rc, None
    exe = os.path.join(INSTALLER_OUT, name + ".exe")
    print("✅ {} ساخته شد: {}  ({:.1f} مگابایت)".format(
        label, exe, os.path.getsize(exe) / 1024 / 1024))
    return 0, exe


def main():
    os.chdir(ROOT)
    args = sys.argv[1:]
    want_user = "--admin" not in args
    want_admin = "--user" not in args
    if "--user" in args and "--admin" in args:
        want_user = want_admin = True
    want_installer = any(a in args for a in ("--installer", "--installer-only"))
    want_installer_admin = "--installer-admin" in args
    only_installer = "--installer-only" in args
    server = ""
    for arg in args:
        if arg.startswith("--server="):
            server = arg.split("=", 1)[1].strip()
    if only_installer:
        want_user = want_admin = False
    if want_installer_admin and not want_installer:
        want_installer = True

    if not os.path.exists(PUBLIC_KEY):
        print("کلید عمومی لایسنس پیدا نشد: {}".format(PUBLIC_KEY))
        print("اول اجرا کنید: python tools/make_license_keys.py")
        return 2
    if want_admin and not os.path.exists(PRIVATE_KEY):
        print("کلید خصوصی لایسنس پیدا نشد: {}".format(PRIVATE_KEY))
        print("اول اجرا کنید: python tools/make_license_keys.py")
        return 2

    build_root = os.path.join(ROOT, "build")
    if os.path.isdir(build_root):
        shutil.rmtree(build_root, ignore_errors=True)

    rc = 0
    user_exe = admin_exe = None
    os.makedirs(INSTALLER_OUT, exist_ok=True)

    if want_user:
        # تنها کلید عمومی؛ کلید خصوصی هرگز بسته‌بندی نمی‌شود.
        code, user_exe = build("نسخهٔ کاربری", "Mental accounting",
                               [(PUBLIC_KEY, "license_keys")])
        rc = rc or code

    if want_admin:
        code, admin_exe = build(
            "نسخهٔ مدیر", "Mental admin accounting",
            [(PUBLIC_KEY, "license_keys"), (PRIVATE_KEY, "license_keys")])
        rc = rc or code

    if rc:
        return rc

    if user_exe:
        if not audit_user_build(user_exe):
            print("ساخت نسخهٔ کاربری به دلیل مشکل امنیتی تأیید نشد.")
            return 3

    if admin_exe:
        if not audit_admin_build(admin_exe):
            print("ساخت نسخهٔ مدیر تأیید نشد.")
            return 4

    installers = []
    if want_installer:
        user_payload = user_exe or os.path.join(ROOT, "dist", USER_EXE)
        code, path = build_installer(
            "فایل نصب نسخهٔ کاربری", user_payload, "Mental accounting Setup",
            server=server)
        rc = rc or code
        if path:
            installers.append(path)
    if want_installer_admin:
        admin_payload = admin_exe or os.path.join(ROOT, "dist", ADMIN_EXE)
        code, path = build_installer(
            "فایل نصب نسخهٔ مدیر", admin_payload, "Mental admin accounting Setup",
            server=server)
        rc = rc or code
        if path:
            installers.append(path)
    if rc:
        return rc

    print("\nخروجی‌ها:")
    if user_exe:
        print("   {}".format(user_exe))
    if admin_exe:
        print("   {}".format(admin_exe))
    for path in installers:
        print("   {}".format(path))
        print("      (برای نصب: همین فایل را روی رایانهٔ مشتری اجرا کنید)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
