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

سازگاری ویندوز: خروجی‌ها باید روی ویندوز ۷ SP1 (۳۲ و ۶۴ بیتی) تا ویندوز ۱۱
کار کنند. پس **باید با پایتون ۳٫۸ ساخته شوند** (آخرین نسخه‌ای که ویندوز ۷ را
پشتیبانی می‌کند؛ از ۳٫۹ به بعد `api-ms-win-core-path-l1-1-0.dll` لازم می‌شود
که فقط از ویندوز ۸ وجود دارد). همچنین کتابخانهٔ UCRT از Windows SDK همراه
برنامه بسته‌بندی می‌شود تا روی ویندوز ۷ تازه (بدون KB2999226) هم اجرا شود.

اجرا با پایتون ۳٫۸:
    \.venv38\\Scripts\\python.exe build.py --installer --installer-admin

اگر Windows SDK نصب نباشد، پوشهٔ UCRT را با متغیر محیطی `UCRT_DLL_DIR`
معرفی کنید.
"""
import glob
import hashlib
import os
import shutil
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY_DIR = os.path.join(ROOT, "app", "license_keys")
PUBLIC_KEY = os.path.join(KEY_DIR, "root_public.key")
PRIVATE_KEY = os.path.join(KEY_DIR, "root_private.key")

BASE_HIDDEN = ["flask", "jinja2", "werkzeug", "sqlite3", "cryptography",
               "cryptography.hazmat.primitives.asymmetric.ed25519",
               "cryptography.hazmat.backends.openssl"]

WIN7_PYTHON = (3, 8)          # آخرین پایتونی که ویندوز ۷ را پشتیبانی می‌کند

# با پایتون ۳۲ بیتی، خروجی ۳۲ بیتی است و در نام فایل مشخص می‌شود تا با
# نسخهٔ ۶۴ بیتی روی یک رایانه قاطی نشود.
IS_32BIT = struct.calcsize("P") == 4
ARCH_TAG = " (32-bit)" if IS_32BIT else ""
ARCH_NAME = "x86" if IS_32BIT else "x64"

try:
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import win7_check           # noqa: E402 - بازرسی سازگاری ویندوز ۷
except ImportError:             # pragma: no cover - pefile نصب نیست
    win7_check = None

INSTALLER_DIR = os.path.join(ROOT, "installer")
SETUP_PY = os.path.join(INSTALLER_DIR, "setup.py")
INSTALLER_OUT = os.path.join(ROOT, "dist", "installer")
ADMIN_EXE = "Mental admin accounting" + ARCH_TAG + ".exe"
USER_EXE = "Mental accounting" + ARCH_TAG + ".exe"
# آیکون ویندوز (نشان Mental)؛ با `python tools/make_icon.py` ساخته می‌شود.
ICON = os.path.join(ROOT, "assets", "app.ico")


def ucrt_dll_dir():
    """پوشهٔ DLLهای UCRT مخصوص ویندوز ۷ از Windows SDK.

    ویندوز ۷ به‌طور پیش‌فرض Universal C Runtime ندارد. اگر DLLهای UCRT از
    System32 همین ویندوز (۱۰/۱۱) برداشته شوند، خودشان به APIهای ویندوز ۱۰
    وابسته‌اند و روی ویندوز ۷ بالا نمی‌آیند. نسخهٔ موجود در Windows SDK
    (Redist\\ucrt\\DLLs) همان نسخه‌ای است که مایکروسافت برای ویندوز ۷ منتشر
    کرده و باید همراه برنامه بسته‌بندی شود.
    """
    arch = "x86" if struct.calcsize("P") == 4 else "x64"
    candidates = []
    override = os.environ.get("UCRT_DLL_DIR", "").strip()
    if override:
        candidates.append(override)
    for base in (os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("ProgramFiles")):
        if not base:
            continue
        kits = os.path.join(base, "Windows Kits", "10", "Redist")
        candidates += sorted(glob.glob(os.path.join(kits, "*", "ucrt", "DLLs", arch)),
                             reverse=True)
        candidates.append(os.path.join(kits, "ucrt", "DLLs", arch))
    for path in candidates:
        if os.path.isfile(os.path.join(path, "ucrtbase.dll")) and os.path.isfile(
                os.path.join(path, "api-ms-win-crt-runtime-l1-1-0.dll")):
            return path
    return ""


def pyinstaller_env():
    """محیط اجرای PyInstaller با UCRT ویندوز-۷ در ابتدای PATH.

    PyInstaller وابستگی‌ها را اول در PATH می‌گردد؛ اگر پوشهٔ SDK اول باشد،
    نسخهٔ سازگار با ویندوز ۷ برداشته می‌شود (نه نسخهٔ System32 یا هر برنامهٔ
    دیگری که اتفاقی در PATH است).
    """
    env = os.environ.copy()
    ucrt = ucrt_dll_dir()
    if ucrt:
        env["PATH"] = ucrt + os.pathsep + env.get("PATH", "")
    return env


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
    rc = subprocess.call(cmd, env=pyinstaller_env())
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


def audit_win7(exe):
    """تأیید اینکه فایل اجرایی روی ویندوز ۷ SP1 بالا می‌آید.

    دو چیز بررسی می‌شود:
      * هیچ باینری داخل exe به API/DLLای که در ویندوز ۷ نیست وابسته نباشد
        (همان خطای `api-ms-win-core-path-l1-1-0.dll` که با پایتون ۳٫۹+ رخ می‌دهد).
      * DLLهای UCRT داخل exe دقیقاً همان نسخهٔ Windows SDK باشند، نه نسخهٔ
        System32 یا فایل تصادفی دیگری از PATH.
    """
    print("\n--- بازرسی سازگاری با ویندوز ۷: {} ---".format(os.path.basename(exe)))
    if win7_check is None:
        print("❌ ابزار tools/win7_check.py کار نکرد (pefile نصب است؟).")
        return False
    problems = win7_check.check_exe(exe, arch=ARCH_NAME)

    ucrt = ucrt_dll_dir()
    if not ucrt:
        problems.append("پوشهٔ UCRT ویندوز ۷ پیدا نشد؛ Windows SDK نصب نیست و "
                        "UCRT_DLL_DIR هم تنظیم نشده.")
    else:
        try:
            from PyInstaller.archive.readers import CArchiveReader
            reader = CArchiveReader(exe)
            entries = {str(n).lower(): str(n) for n in reader.toc}
            bundled = [n for n in entries if n.endswith(".dll") and (
                n == "ucrtbase.dll" or n.startswith("api-ms-win-crt-"))]
            if "ucrtbase.dll" not in [n.lower() for n in bundled]:
                problems.append("ucrtbase.dll همراه برنامه نیست؛ ویندوز ۷ تازه "
                                "برنامه را اجرا نمی‌کند.")
            for low in bundled:
                src = os.path.join(ucrt, low)
                if not os.path.isfile(src):
                    continue                       # فایل اضافی، مشکلی نیست
                data = reader.extract(entries[low])
                if hashlib.sha256(data).hexdigest() != _sha256(src):
                    problems.append(
                        "{}: نسخهٔ داخل exe با UCRT سازگار با ویندوز ۷ برابر "
                        "نیست (احتمالاً از System32 برداشته شده).".format(low))
        except Exception as exc:                  # noqa: BLE001
            problems.append("محتویات exe بازرسی نشد: {!r}".format(exc))

    if problems:
        for p in problems:
            print("  ❌ " + p)
        return False
    print("  ✅ سازگار با ویندوز ۷ SP1 (۳۲/۶۴ بیتی) تا ویندوز ۱۱")
    return True


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    rc = subprocess.call(cmd, env=pyinstaller_env())
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
    if {"--user", "--admin"} <= set(args):
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

    print("ساخت با پایتون {} — معماری {}".format(
        sys.version.split()[0], ARCH_NAME))
    if sys.version_info[:2] != WIN7_PYTHON and \
            "--allow-newer-python" not in args:
        print("❌ این پایتون {} است، ولی برای پشتیبانی از ویندوز ۷ باید با "
              "پایتون {}.{} ساخته شود.".format(
                  sys.version.split()[0], WIN7_PYTHON[0], WIN7_PYTHON[1]))
        print("   پایتون ۳٫۹ و بالاتر به api-ms-win-core-path-l1-1-0.dll نیاز "
              "دارند که در ویندوز ۷ وجود ندارد؛ برنامه با خطای «api-ms-win-"
              "core-path-l1-1-0.dll is missing» باز نمی‌شود.")
        print("   اگر فقط برای ویندوز ۸ و بالاتر می‌سازید: --allow-newer-python")
        return 5
    if not ucrt_dll_dir():
        print("⚠ پوشهٔ UCRT ویندوز ۷ پیدا نشد (Windows SDK). برنامه ساخته می‌شود "
              "ولی بازرسی سازگاری ویندوز ۷ رد خواهد شد.")

    build_root = os.path.join(ROOT, "build")
    if os.path.isdir(build_root):
        shutil.rmtree(build_root, ignore_errors=True)

    rc = 0
    user_exe = admin_exe = None
    os.makedirs(INSTALLER_OUT, exist_ok=True)

    if want_user:
        # تنها کلید عمومی؛ کلید خصوصی هرگز بسته‌بندی نمی‌شود.
        code, user_exe = build("نسخهٔ کاربری", "Mental accounting" + ARCH_TAG,
                               [(PUBLIC_KEY, "license_keys")])
        rc = rc or code

    if want_admin:
        code, admin_exe = build(
            "نسخهٔ مدیر", "Mental admin accounting" + ARCH_TAG,
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

    for exe in (user_exe, admin_exe):
        if exe and not audit_win7(exe):
            print("ساخت به دلیل ناسازگاری با ویندوز ۷ تأیید نشد.")
            return 6

    installers = []
    if want_installer:
        user_payload = user_exe or os.path.join(ROOT, "dist", USER_EXE)
        code, path = build_installer(
            "فایل نصب نسخهٔ کاربری", user_payload,
            "Mental accounting Setup" + ARCH_TAG, server=server)
        rc = rc or code
        if path:
            installers.append(path)
    if want_installer_admin:
        admin_payload = admin_exe or os.path.join(ROOT, "dist", ADMIN_EXE)
        code, path = build_installer(
            "فایل نصب نسخهٔ مدیر", admin_payload,
            "Mental admin accounting Setup" + ARCH_TAG, server=server)
        rc = rc or code
        if path:
            installers.append(path)
    if rc:
        return rc

    for path in installers:
        if not audit_win7(path):
            print("فایل نصب به دلیل ناسازگاری با ویندوز ۷ تأیید نشد.")
            return 6

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
