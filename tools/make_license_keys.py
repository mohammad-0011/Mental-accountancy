"""ساخت جفت‌کلید ریشهٔ لایسنس (یک‌بار برای همیشه).

اجرا:
    python tools/make_license_keys.py            # اگر کلید نباشد می‌سازد
    python tools/make_license_keys.py --force    # ساخت مجدد (خطرناک)

خروجی:
    app/license_keys/root_private.key   ← فقط نزد شما؛ در برنامهٔ کاربری بسته‌بندی نمی‌شود
    app/license_keys/root_public.key    ← در هر دو برنامه بسته‌بندی می‌شود

هشدار: اگر کلید خصوصی را پاک کنید یا --force بزنید، **همهٔ لایسنس‌های
صادرشدهٔ قبلی باطل می‌شوند** و باید برای مشتریان دوباره لایسنس بسازید و
برنامهٔ کاربری را از نو بسازید.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import licensing  # noqa: E402

KEY_DIR = os.path.join(ROOT, "app", "license_keys")
PRIVATE = os.path.join(KEY_DIR, "root_private.key")
PUBLIC = os.path.join(KEY_DIR, "root_public.key")


def main():
    force = "--force" in sys.argv
    has_private = os.path.exists(PRIVATE)
    has_public = os.path.exists(PUBLIC)

    if has_private and has_public and not force:
        with open(PUBLIC, encoding="utf-8") as f:
            pub = f.read().strip()
        print("کلید ریشه از قبل وجود دارد؛ چیزی ساخته نشد.")
        print("کلید عمومی فعلی:")
        print("  " + pub)
        print("\nبرای ساخت مجدد (و باطل‌شدن همهٔ لایسنس‌های قبلی): --force")
        return 0

    if force and has_private:
        print("هشدار: با --force همهٔ لایسنس‌های صادرشدهٔ قبلی باطل می‌شوند.")
        if os.environ.get("SABA_FORCE_KEYS") != "1":
            print("برای ادامه مقدار محیطی SABA_FORCE_KEYS=1 را تنظیم کنید.")
            return 2

    os.makedirs(KEY_DIR, exist_ok=True)
    priv_raw, pub_raw = licensing.generate_keypair()
    priv_text, pub_text = licensing.keypair_to_text(priv_raw, pub_raw)
    with open(PRIVATE, "w", encoding="utf-8") as f:
        f.write(priv_text + "\n")
    with open(PUBLIC, "w", encoding="utf-8") as f:
        f.write(pub_text + "\n")

    try:                                    # کلید خصوصی فقط برای کاربر جاری
        os.chmod(PRIVATE, 0o600)
    except OSError:
        pass

    bot_dir = os.path.join(ROOT, "bot", "keys")
    if os.path.isdir(os.path.dirname(bot_dir)):
        # سرور لایسنس/بات به همان جفت‌کلید نیاز دارد؛ تا کپی دستی لازم نباشد.
        os.makedirs(bot_dir, exist_ok=True)
        with open(os.path.join(bot_dir, "root_private.key"), "w",
                  encoding="utf-8") as f:
            f.write(priv_text + "\n")
        with open(os.path.join(bot_dir, "root_public.key"), "w",
                  encoding="utf-8") as f:
            f.write(pub_text + "\n")
        try:
            os.chmod(os.path.join(bot_dir, "root_private.key"), 0o600)
        except OSError:
            pass

    print("جفت‌کلید ریشه ساخته شد:")
    print("  کلید خصوصی: " + PRIVATE + "   (محرمانه — به مشتری ندهید)")
    print("  کلید عمومی: " + PUBLIC)
    if os.path.isdir(os.path.dirname(bot_dir)):
        print("  همان جفت در bot/keys هم نوشته شد (سرور لایسنس).")
    print("\nکلید عمومی (برای بررسی در برنامهٔ کاربری):")
    print("  " + pub_text)
    print("\nقدم بعدی: python build.py --all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
