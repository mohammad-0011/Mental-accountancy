"""آزمون منطق راه‌انداز (run.py) و هدرهای کش.

خطای «ارتباط با سرور برقرار نشد» وقتی رخ می‌داد که صفحهٔ قدیمی از کش
مرورگر می‌آمد یا سرویس روی پورت دیگری مرده بود. این آزمون همان دو
سناریو را قطعی می‌سنجد:

  * پورت ثابت + استفادهٔ دوباره از نمونهٔ در حال اجرا
  * no-store بودن صفحه و دارایی‌ها تا هیچ‌وقت صفحهٔ کهنه نشان داده نشود

روی پورت‌های تست (۱۸۷۵۶+) کار می‌کند تا نمونهٔ واقعی کاربر را مزاحم نشود.
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import run  # noqa: E402
from app.server import create_app, APP_ID  # noqa: E402

PASS, FAIL = [], []
TEST_BASE = 18756


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (("  -> " + str(extra)) if extra else ""))


def wait_listening(port, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.15)
    return False


def serve_flask(app, port):
    """سرور واقعی روی پورت دلخواه؛ در نخ پس‌زمینه."""
    t = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, threaded=True,
                               use_reloader=False),
        daemon=True)
    t.start()
    return t


def foreign_listener(port):
    """شنوندهٔ غریبه (نه HTTP، شبیه برنامهٔ دیگری روی همان پورت)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", port))
    s.listen(5)
    return s


def main():
    tmp = tempfile.mkdtemp(prefix="hesablaunch_")
    app = create_app(os.path.join(tmp, "launch.db"))

    print("\n[۱] نشانی ثابت برنامه")
    check("پورت پایهٔ برنامه ۸۷۵۶ است", run.BASE_PORT == 8756, run.BASE_PORT)

    # بازهٔ پورت را به بازهٔ تست محدود می‌کنیم تا نمونهٔ واقعی کاربر مزاحم نشود
    saved_range = run.PORT_RANGE
    run.PORT_RANGE = range(TEST_BASE, TEST_BASE + 5)
    flask_thread = None
    foreign = None
    try:
        print("\n[۲] انتخاب پورت و استفادهٔ دوباره از نمونهٔ در حال اجرا")
        mode, port = run.choose_port()
        check("پورت آزاد -> حالت serve روی پورت پایه",
              (mode, port) == ("serve", TEST_BASE), (mode, port))

        # یک شنوندهٔ غریبه روی پورت پایه (برنامهٔ دیگری روی همان پورت)
        foreign = foreign_listener(TEST_BASE)
        check("شنوندهٔ غریبه پورت را اشغال نشان می‌دهد",
              run.port_taken(TEST_BASE) is True)
        check("شنوندهٔ غریبه به‌عنوان برنامهٔ ما شناخته نمی‌شود",
              run.is_our_server(TEST_BASE) is False)
        mode, port = run.choose_port()
        check("با اشغال پورت پایه، پورت بعدی انتخاب می‌شود",
              (mode, port) == ("serve", TEST_BASE + 1), (mode, port))
        foreign.close()
        foreign = None

        # نمونهٔ واقعی برنامه روی پورت دیگری از همان بازه؛ بازه را طوری تنظیم
        # می‌کنیم که پورت نمونهٔ در حال اجرا، پورت پایهٔ همین بازه باشد.
        LIVE = TEST_BASE + 1
        run.PORT_RANGE = range(LIVE, LIVE + 5)
        flask_thread = serve_flask(app, LIVE)
        check("سرویس تست بالا آمد", wait_listening(LIVE))
        check("سرویس خودمان شناسایی می‌شود", run.is_our_server(LIVE) is True)
        mode, port = run.choose_port()
        check("نمونهٔ در حال اجرا دوباره استفاده می‌شود (پورت عوض نمی‌شود)",
              (mode, port) == ("reuse", LIVE), (mode, port))

        raw = urllib.request.urlopen(
            "http://127.0.0.1:{}/api/ping".format(LIVE), timeout=3).read()
        body = json.loads(raw.decode("utf-8"))
        check("پاسخ /api/ping شناسهٔ برنامه را دارد",
              body.get("data", {}).get("app") == APP_ID, raw[:90])
    finally:
        if foreign is not None:
            foreign.close()
        run.PORT_RANGE = saved_range

    print("\n[۳] هدرهای کش — جلوگیری از نمایش صفحهٔ کهنه")
    c = app.test_client()
    r = c.get("/")
    cc = r.headers.get("Cache-Control", "")
    check("صفحهٔ اصلی no-store است", "no-store" in cc, cc)
    check("صفحهٔ اصلی no-cache هم دارد", "no-cache" in cc, cc)
    html = r.data.decode("utf-8", "replace")
    check("صفحهٔ اصلی سمبل‌های آیکون را درون خود دارد",
          html.count('<symbol id="i-') >= 60, html.count('<symbol id="i-'))
    check("صفحهٔ اصلی پیوند پرش و ناحیهٔ محتوا دارد",
          'class="skip-link"' in html and '<main id="content"' in html)
    check("ناحیهٔ پیام‌ها aria-live دارد",
          'aria-live="polite"' in html and 'id="toastRoot"' in html)

    for path, needle in (("/app.js", "application/javascript"),
                         ("/style.css", "text/css"),
                         ("/icons.svg", "image/svg+xml")):
        rr = c.get(path)
        cch = rr.headers.get("Cache-Control", "")
        check("{} با no-store سرو می‌شود".format(path), "no-store" in cch, cch)
        check("{} با نوع درست سرو می‌شود".format(path),
              needle in rr.headers.get("Content-Type", ""),
              rr.headers.get("Content-Type"))

    fonts = ("Vazirmatn-Regular.woff2", "Vazirmatn-Medium.woff2",
             "Vazirmatn-SemiBold.woff2", "Vazirmatn-Bold.woff2")
    for name in fonts:
        rr = c.get("/fonts/" + name)
        on_disk = os.path.join(ROOT, "web", "fonts", name)
        with open(on_disk, "rb") as fh:
            want = fh.read()
        check("فونت {} با بایت‌های فایل اصلی سرو می‌شود".format(name),
              rr.status_code == 200 and rr.data == want,
              "{} {} بایت".format(rr.status_code, len(rr.data)))
        check("فونت {} با نوع font/woff2 سرو می‌شود".format(name),
              "font/woff2" in rr.headers.get("Content-Type", ""),
              rr.headers.get("Content-Type"))
        check("فونت {} با no-store سرو می‌شود".format(name),
              "no-store" in rr.headers.get("Cache-Control", ""))

    check("بازهٔ پورت پس از آزمون بازگردانده شد",
          run.PORT_RANGE == saved_range)

    # نام فایل‌های اجرایی بعداً عوض شد («Mental admin accounting.exe»)؛ اگر
    # تشخیص نسخه فقط به «-admin» وابسته بماند، نسخهٔ فروشنده بی‌صدا در حالت
    # کاربری بالا می‌آمد و پنل صدور لایسنس غیب می‌شد.
    print("\n[۴] تشخیص نسخه (کاربری/مدیر) از نام فایل اجرایی")
    import app.server as srv
    saved_frozen = getattr(sys, "frozen", None)
    saved_executable = sys.executable
    saved_mode_env = os.environ.pop("SABA_MODE", None)
    try:
        sys.frozen = True
        for exe_name, want in (("Mental admin accounting.exe", "admin"),
                               ("HesabDari-Saba-Admin.exe", "admin"),
                               ("Mental accounting.exe", "user"),
                               ("HesabDari-Saba.exe", "user"),
                               ("Mental-Admin-Accounting.exe", "admin")):
            sys.executable = os.path.join(tempfile.gettempdir(), exe_name)
            got = srv.app_mode()
            check("نام {!r} -> نسخهٔ {}".format(exe_name, want), got == want, got)

        del sys.frozen
        sys.executable = os.path.join(tempfile.gettempdir(),
                                      "Mental admin accounting.exe")
        check("اجرای غیربسته‌بندی‌شده در حالت کاربری می‌ماند",
              srv.app_mode() == "user", srv.app_mode())

        os.environ["SABA_MODE"] = "admin"
        check("متغیر SABA_MODE بر نام فایل اولویت دارد",
              srv.app_mode() == "admin", srv.app_mode())
    finally:
        os.environ.pop("SABA_MODE", None)
        if saved_mode_env is not None:
            os.environ["SABA_MODE"] = saved_mode_env
        sys.executable = saved_executable
        if saved_frozen is None:
            if hasattr(sys, "frozen"):
                del sys.frozen
        else:
            sys.frozen = saved_frozen

    print("\n" + "=" * 52)
    print("موفق: {}   ناموفق: {}".format(len(PASS), len(FAIL)))
    if FAIL:
        print("موارد ناموفق:")
        for f in FAIL:
            print("  - " + f)
        return 1
    print("همهٔ بررسی‌های راه‌انداز موفق بود.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
