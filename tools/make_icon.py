"""ساخت آیکون ویندوز (assets/app.ico) هم‌شکل با نشان «Mental».

لوگوی رابط کاربری در `web/logo.svg` (برداری) است؛ ویندوز برای آیکون فایل
اجرایی و میان‌برها به `.ico` نیاز دارد. این اسکریپت همان نشان را با Pillow
می‌کشد: مربع گردِ گرادیانی، حرف M و خط سبز پایین.

اجرا:

    python tools/make_icon.py            # ساخت assets/app.ico
    python tools/make_icon.py --preview  # ساخت پیش‌نمایش PNG در assets/

اگر Pillow نبود، اسکریپت بی‌خطر رد می‌شود (ساخت برنامه به آیکون وابسته نیست).
"""
import argparse
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets")
ICO = os.path.join(OUT_DIR, "app.ico")
PNG = os.path.join(OUT_DIR, "app-icon.png")

SIZES = (256, 128, 64, 48, 32, 16)
# بزرگ می‌کشیم و کوچک می‌کنیم تا لبه‌ها نرم شوند
SUPER = 1024

NAVY = (30, 58, 95)
BLUE = (37, 99, 235)
GREEN = (5, 150, 105)


def _gradient(size):
    """گرادیان خطی از آبی به سرمه‌ای (گوشهٔ بالا-راست ← پایین-چپ)."""
    from PIL import Image
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2.0 * (size - 1))
            px[x, y] = (int(BLUE[0] + (NAVY[0] - BLUE[0]) * t),
                        int(BLUE[1] + (NAVY[1] - BLUE[1]) * t),
                        int(BLUE[2] + (NAVY[2] - BLUE[2]) * t))
    return img


def draw(size=SUPER, baseline=True):
    """نشان کامل در اندازهٔ دلخواه (پیش‌فرض بزرگ با خط سبز پایین)."""
    from PIL import Image, ImageDraw
    img = _gradient(size).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.266), fill=255)
    img.putalpha(mask)

    d = ImageDraw.Draw(img)
    k = size / 64.0

    def p(x, y):
        return (x * k, y * k)

    width = max(2, int(round(5.4 * k)))
    # حرف M
    d.line([p(14.5, 44.5), p(14.5, 21.8)], fill="white", width=width, joint="curve")
    d.line([p(14.5, 21.8), p(32, 39.2), p(49.5, 21.8)], fill="white",
           width=width, joint="curve")
    d.line([p(49.5, 21.8), p(49.5, 44.5)], fill="white", width=width, joint="curve")
    # گردکردن سرها
    r = width / 2.0
    for cx, cy in ((14.5, 44.5), (14.5, 21.8), (32, 39.2), (49.5, 21.8),
                   (49.5, 44.5)):
        x, y = p(cx, cy)
        d.ellipse([x - r, y - r, x + r, y + r], fill="white")
    if baseline:
        x0, y0 = p(16.5, 51.5)
        x1, y1 = p(47.5, 55.7)
        d.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) / 2.0, fill=GREEN)
    return img


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--preview", action="store_true",
                    help="فقط یک PNG برای بازبینی بساز")
    args = ap.parse_args(argv)

    try:
        from PIL import Image          # noqa: F401
    except ImportError:
        print("⚠️ Pillow نصب نیست؛ آیکون ساخته نشد "
              "(برای ساخت: pip install pillow)")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    large = draw(SUPER)
    if args.preview:
        large.resize((512, 512), Image.LANCZOS).save(PNG)
        print("✅ پیش‌نمایش ساخته شد: " + PNG)
        return 0

    frames = [large.resize((s, s), Image.LANCZOS) for s in SIZES]
    frames[0].save(ICO, format="ICO",
                   sizes=[(s, s) for s in SIZES], append_images=frames[1:])
    large.resize((512, 512), Image.LANCZOS).save(PNG)
    print("✅ آیکون ساخته شد: {}  ({} اندازه)".format(ICO, len(SIZES)))
    print("✅ پیش‌نمایش: " + PNG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
