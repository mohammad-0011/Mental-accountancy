"""سیستم حسابداری Mental (نسخه باتری‌فروشان) — فایل اجرای برنامه.

نکات پایداری:
  * ابتدا پورت ثابت ۸۷۵۶ امتحان می‌شود تا نشانی برنامه بین اجراها عوض نشود؛
    اگر نمونه‌ای از خود برنامه در حال اجرا باشد، همان دوباره استفاده می‌شود.
  * همهٔ کارها در فایل گزارش `data/app.log` ثبت می‌شود تا عیب‌یابی ممکن باشد.
  * پنجرهٔ برنامه بدون پروکسی باز می‌شود تا پروکسی/VPN محلی را قطع نکند.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser

from app.server import create_app, APP_ID, data_dir, app_mode

BASE_PORT = 8756
PORT_RANGE = range(8756, 8800)
HOST = "127.0.0.1"


def log(msg):
    line = "{}  {}".format(time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(os.path.join(data_dir(), "app.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def port_taken(port, timeout=0.4):
    try:
        with socket.create_connection((HOST, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_our_server(port, mode=None, timeout=1.2):
    """آیا روی این پورت، همین نسخه از برنامه سرو می‌کند؟

    پاسخ /api/ping در پوشش {"ok":true,"data":{...}} می‌آید؛ اگر شناسه در
    لایهٔ بیرونی خوانده شود همیشه False می‌شود و راه‌انداز به‌جای استفادهٔ
    دوباره از نمونهٔ در حال اجرا، نمونهٔ دوم را روی پورت دیگری بالا می‌آورد.

    حالت (کاربری/مدیر) هم مقایسه می‌شود تا نسخهٔ مدیر اشتباهاً به سرویس
    نسخهٔ کاربری وصل نشود.
    """
    try:
        url = "http://{}:{}/api/ping".format(HOST, port)
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    inner = data.get("data")
    payload = inner if isinstance(inner, dict) else data
    if payload.get("app") != APP_ID:
        return False
    if mode and payload.get("mode") and payload.get("mode") != mode:
        return False
    return True


def choose_port(mode=None):
    """(حالت، پورت): حالت یکی از 'reuse' یا 'serve' یا 'none'."""
    for p in PORT_RANGE:
        if is_our_server(p, mode):
            return "reuse", p
        if not port_taken(p):
            return "serve", p
    return "none", 0


def find_browser():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    for name in ("msedge", "chrome"):
        try:
            subprocess.run([name, "--version"], capture_output=True, timeout=5)
            return name
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def open_window(url, edition="user"):
    """پنجرهٔ برنامه را باز می‌کند؛ در صورت موفقیت پروسهٔ مرورگر را برمی‌گرداند.

    هر نسخه پروفایل مرورگر جداگانه دارد؛ چون کوکی‌ها در مرورگر به پورت
    گره نمی‌خورند، بدون این جداسازی نشست دو برنامه روی هم می‌افتد.
    """
    browser = find_browser()
    profile = os.path.join(
        os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
        "HesabDari-Saba", "browser-profile-" + edition)
    try:
        os.makedirs(profile, exist_ok=True)
    except OSError:
        profile = os.path.join(tempfile.gettempdir(),
                               "HesabDari-Saba-profile-" + edition)
        os.makedirs(profile, exist_ok=True)

    if browser:
        args = [
            browser, "--app=" + url,
            "--window-size=1400,900",
            "--user-data-dir=" + profile,
            "--no-first-run", "--no-default-browser-check",
            "--no-proxy-server",             # پروکسی/VPN نباید لوکال‌هاست را قطع کند
            "--disable-session-crashed-bubble",
            "--disable-features=msEdgeSplashScreen",
        ]
        try:
            proc = subprocess.Popen(args)
            log("پنجرهٔ برنامه با {!r} باز شد (pid={})".format(browser, proc.pid))
            return proc
        except OSError as exc:
            log("اجرای مرورگر ناموفق بود: {!r}".format(exc))
    log("مرورگر پیدا نشد؛ از مرورگر پیش‌فرض استفاده می‌شود.")
    try:
        webbrowser.open(url)
    except Exception as exc:
        log("بازکردن مرورگر پیش‌فرض ناموفق بود: {!r}".format(exc))
    return None


def main():
    edition = app_mode()
    state, port = choose_port(edition)
    mode = state
    log("شروع اجرا — نسخه={} حالت={} پورت={}".format(edition, mode, port))

    if mode == "none":
        log("هیچ پورت آزادی در بازه ۸۷۵۶ تا ۸۷۹۹ پیدا نشد.")
        return 1

    url = "http://{}:{}/".format(HOST, port)

    if mode == "reuse":
        log("نمونهٔ در حال اجرای برنامه پیدا شد؛ همان سرویس استفاده می‌شود: " + url)
        open_window(url, edition)
        return 0

    app = create_app(mode=edition)

    def serve():
        try:
            app.run(host=HOST, port=port, debug=False, threaded=True,
                    use_reloader=False)
        except Exception as exc:            # noqa: BLE001 - ثبت و ادامه
            log("خطای سرور محلی: {!r}".format(exc))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    ready = False
    for _ in range(150):                    # تا ۳۰ ثانیه صبر (آنتی‌ویروس کند)
        if not thread.is_alive():
            log("نخ سرور محلی پیش از آماده شدن متوقف شد.")
            break
        if port_taken(port):
            ready = True
            break
        time.sleep(0.2)

    if not ready:
        log("سرویس محلی آماده نشد؛ اجرا لغو شد.")
        return 1
    log("سرویس محلی آماده است: " + url)

    proc = open_window(url, edition)

    # اگر مرورگر بلافاصله خارج شد (تحویل به نمونهٔ در حال اجرای Edge)،
    # نباید آن را مرگ پنجره تلقی کنیم.
    if proc is not None:
        time.sleep(3)
        if proc.poll() is not None:
            log("پروسهٔ مرورگر بلافاصله خارج شد؛ پایش پنجره غیرفعال شد.")
            proc = None

    try:
        while thread.is_alive():
            if proc is not None and proc.poll() is not None:
                log("پنجرهٔ برنامه بسته شد؛ خروج از برنامه.")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("خروج با درخواست کاربر.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
