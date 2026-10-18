"""اینستالر (ویزارد نصب) سیستم حسابداری Mental.

این فایل هم **نصب‌کننده** است و هم **حذف‌کننده**:

    Mental accounting Setup.exe                     نصب گرافیکی (ویزارد)
    Mental accounting Setup.exe /SILENT ...         نصب بی‌صدا (برای چند رایانه)
    Mental accounting Setup.exe --uninstall         حذف برنامه

کارهایی که هنگام نصب انجام می‌شود:
  * انتخاب مسیر نصب توسط کاربر
  * انتخاب پوشهٔ داده‌ها و پوشهٔ پشتیبان‌ها (جدا از هم)
  * پرسیدن نشانی سرور لایسنس (برای فعال‌سازی آنلاین با بات بله) — اختیاری
  * میان‌بر دسکتاپ و منوی شروع
  * ثبت برنامه در «برنامه‌ها و ویژگی‌ها» (حذف‌کننده)
  * نوشتن سه فایل کنار فایل اجرایی: data-dir.txt / backup-dir.txt /
    license-server.txt که برنامه موقع اجرا می‌خواند

فایل اجرایی برنامه (payload) داخل همین فایل نصب‌کننده بسته‌بندی شده است،
پس یک فایل تک‌کلیکی برای فرستادن به مشتری کافی است.
"""
import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

APP_NAME = "سیستم حسابداری Mental"
APP_FOLDER = "HesabDari-Saba"
APP_VERSION = "1.0.1"
APP_ID = "HesabDari-Saba"          # کلید ثبت در ویندوز
UNINSTALL_KEY = ("Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"
                 + APP_ID)
CREATE_NO_WINDOW = 0x08000000

# نام فایل اجرایی که داخل نصب‌کننده بسته‌بندی شده است
EXE_NAME = "Mental accounting.exe"
ADMIN_EXE_NAME = "Mental admin accounting.exe"


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:                   # noqa: BLE001 - روی غیرویندوز هم کار کند
        return False


def local_appdata():
    return os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()


def user_documents():
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    docs = os.path.join(profile, "Documents")
    return docs if os.path.isdir(docs) else profile


def default_install_dir(all_users=False):
    if all_users:
        return os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                            APP_FOLDER)
    return os.path.join(local_appdata(), "Programs", APP_FOLDER)


def quote(value):
    """مسیر امن برای PowerShell (تک‌کوتیشن‌ها دو برابر می‌شوند)."""
    return str(value).replace("'", "''")


def run_hidden(args):
    """اجرای فرمان بدون پنجرهٔ سیاه؛ خروجی (کد، متن) برمی‌گرداند."""
    try:
        proc = subprocess.run(args, capture_output=True, text=False,
                              creationflags=CREATE_NO_WINDOW)
        out = (proc.stdout or b"").decode("utf-8", "replace")
        err = (proc.stderr or b"").decode("utf-8", "replace")
        return proc.returncode, (out + err).strip()
    except OSError as exc:
        return 1, str(exc)


def make_shortcut(link_path, target, working_dir="", icon="", description=""):
    """ساخت میان‌بر .lnk با WScript.Shell (بدون وابستگی بیرونی)."""
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
        "$s.TargetPath='{target}';"
        "$s.WorkingDirectory='{work}';"
        "$s.Description='{desc}';"
        "$s.IconLocation='{icon}';"
        "$s.Save()"
    ).format(link=quote(link_path), target=quote(target),
             work=quote(working_dir or os.path.dirname(target)),
             desc=quote(description or APP_NAME),
             icon=quote(icon or (target + ",0")))
    code, out = run_hidden(["powershell", "-NoProfile", "-ExecutionPolicy",
                            "Bypass", "-Command", script])
    return code == 0, out


def start_menu_dir(all_users=False):
    """پوشهٔ منوی شروع؛ برای نصب کاربری نیازی به دسترسی مدیر نیست."""
    if all_users:
        base = os.environ.get("ProgramData") or r"C:\ProgramData"
    else:
        base = os.environ.get("APPDATA") or local_appdata()
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs")


def write_registry(install_dir, uninstall_exe, size_kb, all_users, version):
    """ثبت برنامه در فهرست «برنامه‌ها و ویژگی‌ها»."""
    import winreg
    root = winreg.HKEY_LOCAL_MACHINE if all_users else winreg.HKEY_CURRENT_USER
    with winreg.CreateKey(root, UNINSTALL_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ,
                          "{} — نسخهٔ صنف باتری‌فروشان".format(APP_NAME))
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Mental")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
        winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ,
                          '"{}" --uninstall'.format(uninstall_exe))
        winreg.SetValueEx(key, "QuietUninstallString", 0, winreg.REG_SZ,
                          '"{}" --uninstall --silent --keep-data'.format(
                              uninstall_exe))
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ,
                          os.path.join(install_dir, EXE_NAME) + ",0")
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD,
                          int(max(1, size_kb)))
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def remove_registry(all_users):
    import winreg
    last_error = ""
    for root in ((winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
                 if all_users else
                 (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)):
        try:
            winreg.DeleteKey(root, UNINSTALL_KEY)
            return True, ""
        except OSError as exc:
            last_error = str(exc)
    return False, last_error


# ---------------------------------------------------------------- نصب/حذف
class InstallPlan:
    """همهٔ انتخاب‌های کاربر؛ در حالت بی‌صدا از خط فرمان پر می‌شود."""

    def __init__(self, install_dir, data_dir, backup_dir, server="", token="",
                 all_users=False, desktop=True, start_menu=True, run_after=True,
                 exe_name=EXE_NAME, uninstall_exe="", admin_token=""):
        self.install_dir = os.path.abspath(install_dir)
        self.data_dir = os.path.abspath(data_dir)
        self.backup_dir = os.path.abspath(backup_dir)
        self.server = (server or "").strip().rstrip("/")
        self.token = (token or "").strip()
        self.admin_token = (admin_token or "").strip()
        self.all_users = bool(all_users)
        self.desktop = bool(desktop)
        self.start_menu = bool(start_menu)
        self.run_after = bool(run_after)
        self.exe_name = exe_name
        self.uninstall_exe = uninstall_exe


def payload_dirs():
    """پوشهٔ محتوای بسته‌بندی‌شده (داخل exe یا کنار همین فایل)."""
    return [resource_path("payload"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "payload")]


def payload_exe(exe_name=EXE_NAME, override=""):
    """مسیر فایل اجرایی برنامه که باید نصب شود.

    اول نام خواسته‌شده، بعد هر *.exe دیگری که در محتوا هست (تا اگر نام فایل
    اجرایی در آینده عوض شد، نصب‌کننده همچنان کار کند).
    """
    if override and os.path.isfile(override):
        return override
    for folder in payload_dirs():
        candidate = os.path.join(folder, exe_name)
        if os.path.isfile(candidate):
            return candidate
    for folder in payload_dirs():
        try:
            names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".exe"))
        except OSError:
            continue
        for name in names:
            if "admin" not in name.lower():
                return os.path.join(folder, name)
        if names:
            return os.path.join(folder, names[0])
    return ""


def embedded_server_default():
    """نشانی سرور لایسنس که هنگام ساخت داخل نصب‌کننده گذاشته شده است."""
    if os.environ.get("SABA_LICENSE_SERVER_DEFAULT"):
        return os.environ["SABA_LICENSE_SERVER_DEFAULT"].strip()
    for folder in payload_dirs():
        path = os.path.join(folder, "license-server.txt")
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return ""


def embedded_token_default():
    if os.environ.get("SABA_CLIENT_TOKEN_DEFAULT"):
        return os.environ["SABA_CLIENT_TOKEN_DEFAULT"].strip()
    for folder in payload_dirs():
        path = os.path.join(folder, "client-token.txt")
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return ""


def embedded_admin_token_default():
    """توکن مدیر که هنگام ساخت نسخهٔ فروشنده داخل نصب‌کننده گذاشته شده است."""
    if os.environ.get("SABA_ADMIN_TOKEN_DEFAULT"):
        return os.environ["SABA_ADMIN_TOKEN_DEFAULT"].strip()
    for folder in payload_dirs():
        path = os.path.join(folder, "admin-token.txt")
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return ""


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _exe_from_payload(exe_name, override=""):
    path = payload_exe(exe_name, override)
    return os.path.basename(path) if path else exe_name


def install(plan, log=print, self_exe=""):
    """انجام واقعی نصب؛ True برمی‌گرداند اگر موفق باشد."""
    source = payload_exe(plan.exe_name, getattr(plan, "payload", ""))
    if not source or not os.path.isfile(source):
        log("❌ فایل اجرایی برنامه (payload) پیدا نشد: {}".format(
            source or plan.exe_name))
        return False
    plan.exe_name = os.path.basename(source)      # نام واقعی داخل محتوا
    with open(source, "rb") as f:
        if f.read(2) != b"MZ":
            log("❌ فایل اجرایی برنامه سالم نیست (امضای MZ ندارد).")
            return False

    log("ساخت پوشهٔ نصب: " + plan.install_dir)
    try:
        os.makedirs(plan.install_dir, exist_ok=True)
        for folder in (plan.data_dir, plan.backup_dir):
            os.makedirs(folder, exist_ok=True)
    except OSError as exc:
        log("❌ ساخت پوشه‌ها ممکن نشد: {}".format(exc))
        return False

    target = os.path.join(plan.install_dir, plan.exe_name)
    try:
        if not _same_path(source, target):
            shutil.copyfile(source, target)
    except OSError as exc:
        log("❌ رونوشت فایل اجرایی ممکن نشد: {}".format(exc))
        return False
    log("✅ برنامه در «{}» نصب شد.".format(plan.install_dir))

    # فایل‌های تنظیمات که برنامه می‌خواند
    configs = {
        "data-dir.txt": plan.data_dir,
        "backup-dir.txt": plan.backup_dir,
        "license-server.txt": plan.server,
        "client-token.txt": plan.token,
        "admin-token.txt": plan.admin_token,
    }
    for name, value in configs.items():
        try:
            with open(os.path.join(plan.install_dir, name), "w",
                      encoding="utf-8") as f:
                f.write(value + "\n")
        except OSError as exc:
            log("⚠️ نوشتن {} ممکن نشد: {}".format(name, exc))
    log("پوشهٔ داده: {}".format(plan.data_dir))
    log("پوشهٔ پشتیبان: {}".format(plan.backup_dir))
    if plan.server:
        log("سرور لایسنس: {}".format(plan.server))

    # میان‌برها
    if plan.desktop:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.join(user_documents(), "Desktop")
        ok, out = make_shortcut(os.path.join(desktop, APP_NAME + ".lnk"), target,
                                plan.install_dir, description=APP_NAME)
        log(("✅ میان‌بر دسکتاپ ساخته شد." if ok
             else "⚠️ میان‌بر دسکتاپ ساخته نشد: " + out))
    if plan.start_menu:
        base = start_menu_dir(plan.all_users)
        folder = os.path.join(base, APP_NAME)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            folder = base
        ok, out = make_shortcut(os.path.join(folder, APP_NAME + ".lnk"), target,
                                plan.install_dir, description=APP_NAME)
        log(("✅ میان‌بر منوی شروع ساخته شد." if ok
             else "⚠️ میان‌بر منوی شروع ساخته نشد: " + out))

    # حذف‌کننده: خود همین فایل، کنار برنامه
    uninstall_exe = os.path.join(plan.install_dir, "Uninstall-{}.exe".format(APP_ID))
    plan.uninstall_exe = uninstall_exe
    if self_exe and os.path.isfile(self_exe) and not _same_path(self_exe, uninstall_exe):
        try:
            shutil.copyfile(self_exe, uninstall_exe)
            log("✅ حذف‌کننده نصب شد.")
        except OSError as exc:
            log("⚠️ رونوشت حذف‌کننده ممکن نشد: {}".format(exc))
    try:
        size_kb = sum(os.path.getsize(os.path.join(plan.install_dir, n))
                      for n in os.listdir(plan.install_dir)
                      if os.path.isfile(os.path.join(plan.install_dir, n))) // 1024
    except OSError:
        size_kb = 0
    try:
        write_registry(plan.install_dir, uninstall_exe, size_kb, plan.all_users,
                       APP_VERSION)
        log("✅ برنامه در فهرست «برنامه‌ها و ویژگی‌ها» ثبت شد.")
    except OSError as exc:
        log("⚠️ ثبت در فهرست ویندوز ممکن نشد: {}".format(exc))

    # ثبت مسیر نصب برای حذف‌کنندهٔ بعدی
    try:
        with open(os.path.join(plan.install_dir, "install-info.txt"), "w",
                  encoding="utf-8") as f:
            f.write("install_dir={}\n".format(plan.install_dir))
            f.write("data_dir={}\n".format(plan.data_dir))
            f.write("backup_dir={}\n".format(plan.backup_dir))
            f.write("all_users={}\n".format(int(plan.all_users)))
            f.write("version={}\n".format(APP_VERSION))
    except OSError:
        pass
    return True


def read_install_info(install_dir):
    info = {}
    try:
        with open(os.path.join(install_dir, "install-info.txt"),
                  encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    key, _, value = line.strip().partition("=")
                    info[key] = value
    except OSError:
        pass
    return info


def uninstall(install_dir, keep_data=True, log=print, all_users=None):
    """حذف برنامه؛ داده‌ها و پشتیبان‌ها به‌طور پیش‌فرض دست‌نخورده می‌مانند."""
    info = read_install_info(install_dir)
    data_dir = info.get("data_dir", "")
    backup_dir = info.get("backup_dir", "")
    if all_users is None:
        all_users = info.get("all_users") == "1"

    removed = 0
    for name in os.listdir(install_dir) if os.path.isdir(install_dir) else []:
        path = os.path.join(install_dir, name)
        if not os.path.isfile(path):
            continue
        if keep_data and name in ("data-dir.txt", "backup-dir.txt"):
            pass
        try:
            os.remove(path)
            removed += 1
        except OSError as exc:
            log("⚠️ حذف {} ممکن نشد: {}".format(name, exc))

    # میان‌برها
    links = [os.path.join(os.path.expanduser("~"), "Desktop", APP_NAME + ".lnk"),
             os.path.join(start_menu_dir(False), APP_NAME, APP_NAME + ".lnk"),
             os.path.join(start_menu_dir(True), APP_NAME, APP_NAME + ".lnk")]
    for link in links:
        try:
            if os.path.isfile(link):
                os.remove(link)
        except OSError:
            pass
    for all_users in (False, True):
        try:
            folder = os.path.join(start_menu_dir(all_users), APP_NAME)
            if os.path.isdir(folder) and not os.listdir(folder):
                os.rmdir(folder)
        except OSError:
            pass

    ok, err = remove_registry(bool(all_users))
    log("✅ {} فایل حذف شد.".format(removed))
    log("✅ ثبت ویندوز پاک شد." if ok else "⚠️ پاک‌کردن ثبت ویندوز: " + err)
    if keep_data:
        if data_dir:
            log("اطلاعات شما دست‌نخورده ماند: " + data_dir)
        if backup_dir:
            log("پشتیبان‌ها دست‌نخورده ماند: " + backup_dir)
    try:
        if os.path.isdir(install_dir) and not os.listdir(install_dir):
            os.rmdir(install_dir)
    except OSError:
        pass
    return True


def schedule_self_delete(folder):
    """پس از پایان حذف‌کننده، خودش و پوشهٔ خالی نصب را پاک می‌کند.

    ویندوز اجازهٔ حذف فایل در حال اجرا را نمی‌دهد؛ پس یک دستور کوتاه در
    پس‌زمینه با کمی تأخیر آن را پاک می‌کند.
    """
    if not getattr(sys, "frozen", False):
        return
    exe = os.path.abspath(sys.executable)
    try:
        subprocess.Popen(
            'ping -n 3 127.0.0.1 >nul & del /f /q "{}" & rmdir "{}"'.format(
                exe, folder),
            shell=True, creationflags=CREATE_NO_WINDOW, close_fds=True)
    except OSError:
        pass


def launch_app(plan):
    target = os.path.join(plan.install_dir, plan.exe_name)
    try:
        subprocess.Popen([target], cwd=plan.install_dir, close_fds=True,
                         creationflags=CREATE_NO_WINDOW)
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ ویزارد
class Wizard:
    """ویزارد نصب گرافیکی (tkinter، راست‌به‌چپ)."""

    def __init__(self, plan=None, exe_name=EXE_NAME, payload=""):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        self.tk, self.ttk = tk, ttk
        self.filedialog, self.messagebox = filedialog, messagebox
        self.root = tk.Tk()
        self.root.title("نصب " + APP_NAME)
        self.root.geometry("760x560")
        self.root.minsize(700, 520)
        self.root.configure(bg="#F4F6F9")
        self.font = ("Tahoma", 10)
        self.font_bold = ("Tahoma", 11, "bold")
        self.step = 0
        self.logs = []
        self.done = False
        self.plan = plan or InstallPlan(
            install_dir=default_install_dir(False),
            data_dir=os.path.join(default_install_dir(False), "data"),
            backup_dir=os.path.join(user_documents(), "پشتیبان Mental"),
            server=embedded_server_default())
        self.plan.exe_name = exe_name
        self.plan.payload = payload
        self.exe_name = exe_name
        self.build_ui()

    # ------------------------------------------------------------- اجزای UI
    def build_ui(self):
        tk, ttk = self.tk, self.ttk
        header = tk.Frame(self.root, bg="#1E3A5F", height=74)
        header.pack(fill="x")
        tk.Label(header, text="نصب " + APP_NAME, bg="#1E3A5F", fg="white",
                 font=("Tahoma", 15, "bold")).pack(side="right", padx=20, pady=(16, 2))
        tk.Label(header, text="نسخهٔ صنف باتری‌فروشان — " + APP_VERSION,
                 bg="#1E3A5F", fg="#C7D6E8", font=("Tahoma", 9)).pack(
                     side="right", padx=20)

        self.body = tk.Frame(self.root, bg="#F4F6F9")
        self.body.pack(fill="both", expand=True, padx=18, pady=14)

        foot = tk.Frame(self.root, bg="#E8EDF3", height=56)
        foot.pack(fill="x", side="bottom")
        self.back_btn = ttk.Button(foot, text="مرحلهٔ قبل", command=self.prev)
        self.back_btn.pack(side="right", padx=(16, 6), pady=12)
        self.next_btn = ttk.Button(foot, text="مرحلهٔ بعد", command=self.next)
        self.next_btn.pack(side="right", padx=6, pady=12)
        self.cancel_btn = ttk.Button(foot, text="انصراف", command=self.root.destroy)
        self.cancel_btn.pack(side="left", padx=16, pady=12)
        self.step_label = tk.Label(foot, text="", bg="#E8EDF3", fg="#44566C",
                                   font=("Tahoma", 9))
        self.step_label.pack(side="left", padx=10)

        self.pages = [self.page_welcome, self.page_dirs, self.page_data,
                      self.page_server, self.page_options, self.page_install]
        self.page_frame = tk.Frame(self.body, bg="#F4F6F9")
        self.page_frame.pack(fill="both", expand=True)
        self.show(0)

    def clear(self):
        for child in self.page_frame.winfo_children():
            child.destroy()

    def show(self, index):
        self.step = max(0, min(index, len(self.pages) - 1))
        self.clear()
        self.pages[self.step]()
        total = len(self.pages) - 1
        self.step_label.config(text="مرحلهٔ {} از {}".format(
            min(self.step + 1, total), total))
        self.back_btn.config(state=("normal" if self.step > 0 else "disabled"))
        if self.step == len(self.pages) - 1:
            self.next_btn.config(text="پایان", command=self.finish)
        else:
            self.next_btn.config(text="مرحلهٔ بعد", command=self.next)

    def title(self, text, sub=""):
        tk = self.tk
        tk.Label(self.page_frame, text=text, bg="#F4F6F9", fg="#1E3A5F",
                 font=("Tahoma", 13, "bold"), anchor="e",
                 justify="right").pack(fill="x", pady=(4, 2))
        if sub:
            tk.Label(self.page_frame, text=sub, bg="#F4F6F9", fg="#5A6B80",
                     font=self.font, anchor="e", justify="right",
                     wraplength=690).pack(fill="x", pady=(0, 10))

    def path_row(self, parent, label, variable, is_file=False):
        """ردیف «برچسب + جعبهٔ مسیر + دکمهٔ انتخاب»."""
        tk, ttk = self.tk, self.ttk
        tk.Label(parent, text=label, bg="#F4F6F9", fg="#33475B",
                 font=self.font_bold, anchor="e").pack(fill="x", pady=(8, 2))
        row = tk.Frame(parent, bg="#F4F6F9")
        row.pack(fill="x")
        entry = ttk.Entry(row, textvariable=variable, font=self.font)
        entry.pack(side="right", fill="x", expand=True)

        def browse():
            if is_file:
                chosen = self.filedialog.askopenfilename(parent=self.root,
                                                         title=label)
            else:
                chosen = self.filedialog.askdirectory(parent=self.root,
                                                      title=label)
            if chosen:
                variable.set(os.path.normpath(chosen))
        ttk.Button(row, text="انتخاب…", command=browse).pack(side="left", padx=(6, 0))
        return entry

    # ------------------------------------------------------------- صفحه‌ها
    def page_welcome(self):
        tk = self.tk
        self.title("به نصب‌کنندهٔ سیستم حسابداری Mental خوش آمدید",
                   "این ویزارد برنامه را روی این رایانه نصب می‌کند و می‌توانید "
                   "مسیر نصب، پوشهٔ اطلاعات و پوشهٔ پشتیبان‌ها را خودتان انتخاب کنید.")
        box = tk.Frame(self.page_frame, bg="white", highlightbackground="#D6DEE8",
                       highlightthickness=1)
        box.pack(fill="both", expand=True)
        items = [
            ("✅ پیش از ادامه", "برنامهٔ در حال اجرا (اگر باز است) بسته شود."),
            ("📂 مسیر نصب", "فایل‌های برنامه در پوشه‌ای که انتخاب می‌کنید می‌نشیند."),
            ("🗄 پوشهٔ اطلاعات", "پایگاه‌دادهٔ حسابداری در پوشه‌ای جدا از برنامه "
                                 "نگه داشته می‌شود تا هنگام به‌روزرسانی از دست نرود."),
            ("💾 پوشهٔ پشتیبان", "پشتیبان‌ها (دستی و خودکار) در پوشهٔ انتخابی شما "
                                 "ذخیره می‌شوند و از خود برنامه مدیریت می‌شوند."),
            ("🔐 فعال‌سازی", "برای لایسنس آنلاین، نشانی سرور فروشنده را وارد کنید "
                             "(اختیاری؛ بعداً هم از داخل برنامه قابل تغییر است)."),
        ]
        for head, text in items:
            row = tk.Frame(box, bg="white")
            row.pack(fill="x", padx=16, pady=6)
            tk.Label(row, text=head, bg="white", fg="#1E3A5F",
                     font=self.font_bold, anchor="e").pack(anchor="e")
            tk.Label(row, text=text, bg="white", fg="#44566C", font=self.font,
                     anchor="e", justify="right", wraplength=660).pack(anchor="e")

    def page_dirs(self):
        tk = self.tk
        from tkinter import StringVar
        self.title("مسیر نصب", "پوشه‌ای که فایل‌های برنامه در آن نصب شود.")
        self.var_install = StringVar(value=self.plan.install_dir)
        self.path_row(self.page_frame, "پوشهٔ نصب برنامه:", self.var_install)
        hint = ("پیشنهاد: «{}» — نیازی به دسترسی مدیر ندارد.\n"
                "می‌توانید پوشه‌ای مثل C:\\HesabDari هم انتخاب کنید.").format(
                    os.path.join(local_appdata(), "Programs", APP_FOLDER))
        tk.Label(self.page_frame, text=hint, bg="#F4F6F9", fg="#5A6B80",
                 font=("Tahoma", 9), anchor="e", justify="right",
                 wraplength=690).pack(fill="x", pady=(10, 0))

    def page_data(self):
        tk = self.tk
        from tkinter import StringVar
        self.title("پوشهٔ اطلاعات و پشتیبان",
                   "این دو پوشه را جدا از محل نصب انتخاب کنید تا هنگام نصب نسخهٔ "
                   "تازه یا حذف برنامه، اطلاعات و پشتیبان‌ها سالم بمانند.")
        self.var_data = StringVar(value=self.plan.data_dir)
        self.var_backup = StringVar(value=self.plan.backup_dir)
        self.path_row(self.page_frame, "پوشهٔ اطلاعات (پایگاه‌داده و لایسنس):",
                      self.var_data)
        self.path_row(self.page_frame, "پوشهٔ پشتیبان‌ها:", self.var_backup)
        tk.Label(self.page_frame,
                 text="پشتیبان‌گیری خودکار و دستی از داخل برنامه مدیریت می‌شود؛ "
                      "تعداد نسخه‌های نگه‌داشته‌شده هم قابل تنظیم است.",
                 bg="#F4F6F9", fg="#5A6B80", font=("Tahoma", 9), anchor="e",
                 justify="right", wraplength=690).pack(fill="x", pady=(10, 0))

    def page_server(self):
        tk = self.tk
        from tkinter import StringVar
        self.title("سرور لایسنس (اختیاری)",
                   "اگر فروشنده سرور لایسنس و بات بله را راه انداخته باشد، نشانی آن "
                   "را اینجا بگذارید تا در صفحهٔ فعال‌سازی، درخواست آنلاین کار کند.")
        self.var_server = StringVar(value=self.plan.server)
        self.var_token = StringVar(value=self.plan.token)
        self.var_admin = StringVar(value=self.plan.admin_token)
        self.path_row(self.page_frame,
                      "نشانی سرور لایسنس (مثل https://license.example.com):",
                      self.var_server)
        self.path_row(self.page_frame, "کلید اتصال برنامه (اگر فروشنده داده است):",
                      self.var_token)
        self.path_row(self.page_frame,
                      "توکن مدیر (فقط برای نسخهٔ فروشنده؛ تأیید درخواست‌ها از "
                      "داخل برنامه):", self.var_admin)
        tk.Label(self.page_frame,
                 text="اگر خالی بگذارید، فعال‌سازی دستی با متن لایسنس و تأیید "
                      "درخواست‌ها از بات بله همچنان کار می‌کند؛ پنل «درخواست‌های "
                      "لایسنس» در برنامه فقط با توکن مدیر باز می‌شود.",
                 bg="#F4F6F9", fg="#5A6B80", font=("Tahoma", 9), anchor="e",
                 justify="right", wraplength=690).pack(fill="x", pady=(10, 0))

    def page_options(self):
        tk = self.tk
        from tkinter import BooleanVar, Checkbutton
        self.title("گزینه‌های نصب")
        self.var_desktop = BooleanVar(value=True)
        self.var_start = BooleanVar(value=True)
        self.var_run = BooleanVar(value=True)
        self.var_all = BooleanVar(value=False)
        box = tk.Frame(self.page_frame, bg="white", highlightbackground="#D6DEE8",
                       highlightthickness=1)
        box.pack(fill="both", expand=True)
        opts = [
            (self.var_desktop, "ساخت میان‌بر روی دسکتاپ"),
            (self.var_start, "ساخت میان‌بر در منوی شروع"),
            (self.var_run, "اجرای برنامه پس از پایان نصب"),
            (self.var_all, "نصب برای همهٔ کاربران این رایانه (نیاز به دسترسی مدیر "
                           "و نصب در Program Files)"),
        ]
        for var, label in opts:
            Checkbutton(box, text=label, variable=var, bg="white", fg="#33475B",
                        font=self.font, anchor="e", justify="right",
                        activebackground="white").pack(fill="x", padx=16, pady=8)

    def page_install(self):
        tk, ttk = self.tk, self.ttk
        self.title("نصب", "برای شروع دکمهٔ «نصب» را بزنید.")
        row = tk.Frame(self.page_frame, bg="#F4F6F9")
        row.pack(fill="x", pady=(0, 8))
        self.install_btn = ttk.Button(row, text="نصب", command=self.do_install)
        self.install_btn.pack(side="right")
        self.progress = ttk.Progressbar(row, mode="determinate", maximum=100,
                                        length=460)
        self.progress.pack(side="right", padx=10, fill="x", expand=True)
        self.log_text = tk.Text(self.page_frame, height=16, font=("Consolas", 9),
                                bg="#0F172A", fg="#D7E3F4", relief="flat",
                                wrap="word")
        self.log_text.pack(fill="both", expand=True)

    # --------------------------------------------------------------- جریان
    def collect(self):
        if self.step >= 1:
            self.plan.install_dir = self.var_install.get().strip() or self.plan.install_dir
        if self.step >= 2:
            self.plan.data_dir = self.var_data.get().strip() or self.plan.data_dir
            self.plan.backup_dir = (self.var_backup.get().strip()
                                    or self.plan.backup_dir)
        if self.step >= 3:
            self.plan.server = self.var_server.get().strip()
            self.plan.token = self.var_token.get().strip()
            self.plan.admin_token = self.var_admin.get().strip()
        if self.step >= 4:
            self.plan.desktop = self.var_desktop.get()
            self.plan.start_menu = self.var_start.get()
            self.plan.run_after = self.var_run.get()
            self.plan.all_users = self.var_all.get()
            if self.plan.all_users:
                self.plan.install_dir = default_install_dir(True)

    def next(self):
        self.collect()
        if self.step == 1 and not self.plan.install_dir:
            self.messagebox.showerror("مسیر نصب", "پوشهٔ نصب را انتخاب کنید.")
            return
        if self.step == 2:
            if _same_path(self.plan.data_dir, self.plan.install_dir):
                self.messagebox.showerror(
                    "پوشهٔ اطلاعات",
                    "پوشهٔ اطلاعات نباید همان پوشهٔ نصب باشد؛ پوشهٔ جدا انتخاب کنید.")
                return
            if _same_path(self.plan.backup_dir, self.plan.data_dir):
                self.messagebox.showerror(
                    "پوشهٔ پشتیبان",
                    "پوشهٔ پشتیبان باید جدا از پوشهٔ اطلاعات باشد.")
                return
        self.show(self.step + 1)

    def prev(self):
        self.collect()
        self.show(self.step - 1)

    def log(self, text):
        self.logs.append(text)
        try:
            self.log_text.insert("end", text + "\n")
            self.log_text.see("end")
        except Exception:                       # noqa: BLE001
            pass
        self.root.update_idletasks()

    def do_install(self):
        self.collect()
        if self.plan.all_users and not is_admin():
            if self.messagebox.askyesno(
                    "دسترسی مدیر",
                    "برای نصب در Program Files نیاز به دسترسی مدیر است.\n"
                    "همین حالا پنجرهٔ تأیید ویندوز باز شود؟"):
                relaunch_elevated()
                self.root.destroy()
                return
            self.plan.all_users = False
            self.plan.install_dir = default_install_dir(False)
        self.install_btn.config(state="disabled")
        self.progress["value"] = 5
        self.log("شروع نصب…")

        def work():
            self.progress["value"] = 20
            # فقط در نسخهٔ بسته‌بندی‌شده می‌توان خود نصب‌کننده را به‌عنوان
            # حذف‌کننده رونوشت کرد (فایل exe).
            self_exe = sys.executable if getattr(sys, "frozen", False) else ""
            ok = install(self.plan, log=self.log, self_exe=self_exe)
            self.progress["value"] = 90
            self.finish_ok = ok
            self.root.after(0, lambda: self.after_install(ok))

        threading.Thread(target=work, daemon=True).start()

    def after_install(self, ok):
        self.progress["value"] = 100
        if not ok:
            self.messagebox.showerror("نصب",
                                      "نصب کامل نشد؛ پیام‌های پنجره را ببینید.")
            self.install_btn.config(state="normal")
            return
        self.done = True
        self.log("")
        self.log("نصب با موفقیت تمام شد.")
        self.log("برای اجرا از میان‌بر «{}» استفاده کنید.".format(APP_NAME))
        launch = self.plan.run_after
        self.next_btn.config(text="پایان", command=self.finish)
        self.messagebox.showinfo("نصب کامل شد",
                                 "برنامه نصب شد.\n\nپوشهٔ نصب: {}\n"
                                 "پوشهٔ اطلاعات: {}\nپوشهٔ پشتیبان: {}".format(
                                     self.plan.install_dir, self.plan.data_dir,
                                     self.plan.backup_dir))
        if launch:
            launch_app(self.plan)

    def finish(self):
        try:
            log_path = os.path.join(tempfile.gettempdir(),
                                    "HesabDari-install.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.logs) + "\n")
        except OSError:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def relaunch_elevated():
    """اجرای دوبارهٔ همین فایل با درخواست دسترسی مدیر (پنجرهٔ UAC ویندوز)."""
    try:
        params = " ".join('"{}"'.format(a) for a in sys.argv[1:] + ["--elevated"])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                            params, None, 1)
        return True
    except Exception:                           # noqa: BLE001
        return False


# ------------------------------------------------------- حالت خط فرمان
def parse_args(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--silent", "-SILENT", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument("--dir", dest="install_dir")
    parser.add_argument("--data-dir", dest="data_dir")
    parser.add_argument("--backup-dir", dest="backup_dir")
    parser.add_argument("--server")
    parser.add_argument("--token")
    parser.add_argument("--admin-token", dest="admin_token")
    parser.add_argument("--exe-name")
    parser.add_argument("--payload")
    parser.add_argument("--no-desktop", action="store_true")
    parser.add_argument("--no-start-menu", action="store_true")
    parser.add_argument("--no-run", action="store_true")
    parser.add_argument("--all-users", action="store_true")
    parser.add_argument("--elevated", action="store_true")
    parser.add_argument("--help", "-?", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    return args, unknown


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args, unknown = parse_args(argv)

    exe_name = args.exe_name or os.environ.get("SABA_INSTALL_EXE") or \
        _exe_from_payload(EXE_NAME, args.payload or "")
    install_dir = os.path.abspath(args.install_dir or default_install_dir(
        args.all_users))
    data_dir = os.path.abspath(args.data_dir or os.path.join(install_dir, "data"))
    backup_dir = os.path.abspath(args.backup_dir or os.path.join(
        user_documents(), "پشتیبان Mental"))

    if args.help:
        print(__doc__)
        return 0

    if args.uninstall:
        if not args.silent:
            import tkinter.messagebox as mb
            keep = mb.askyesno("حذف " + APP_NAME,
                               "برنامه حذف شود؟\n\nاطلاعات و پشتیبان‌ها پاک "
                               "نمی‌شوند.")
            if not keep:
                return 0
        # حذف‌کننده همیشه داخل پوشهٔ نصب است؛ اگر نصب در پوشهٔ دلخواه (نه
        # پیش‌فرض) انجام شده باشد، باید همان پوشه پاک شود، نه پوشهٔ پیش‌فرض.
        target_dir = install_dir
        if getattr(sys, "frozen", False):
            here = os.path.dirname(os.path.abspath(sys.executable))
            if os.path.isfile(os.path.join(here, "install-info.txt")):
                target_dir = here
        uninstall(target_dir, keep_data=True, log=print,
                  all_users=args.all_users or None)
        schedule_self_delete(target_dir)
        return 0

    plan = InstallPlan(
        install_dir=install_dir, data_dir=data_dir, backup_dir=backup_dir,
        server=args.server or embedded_server_default(),
        token=args.token or embedded_token_default(),
        admin_token=args.admin_token or embedded_admin_token_default(),
        all_users=args.all_users, desktop=not args.no_desktop,
        start_menu=not args.no_start_menu, run_after=not args.no_run,
        exe_name=exe_name)
    plan.payload = args.payload or ""

    if args.silent:
        # رونوشت خود نصب‌کننده به‌عنوان حذف‌کننده فقط در نسخهٔ exe معنا دارد.
        self_exe = sys.executable if getattr(sys, "frozen", False) else ""
        ok = install(plan, log=print, self_exe=self_exe)
        return 0 if ok else 2

    try:
        wizard = Wizard(plan=plan, exe_name=exe_name, payload=plan.payload)
    except Exception as exc:                    # noqa: BLE001 - محیط بدون گرافیک
        print("رابط گرافیکی در دسترس نیست ({}); از حالت بی‌صدا استفاده می‌کنم."
              .format(exc))
        plan.run_after = False
        self_exe = (sys.executable if getattr(sys, "frozen", False) else "")
        return 0 if install(plan, log=print, self_exe=self_exe) else 2
    wizard.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
