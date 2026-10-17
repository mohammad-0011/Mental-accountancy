"""ساخت اسپرایت آیکون‌های SVG از Lucide.

طبق راهنمای اسکیل ui-ux-pro-max نباید از ایموجی به‌عنوان آیکون استفاده شود؛
این ابزار یک مجموعه آیکون خطی یکدست (Lucide، مجوز ISC) را دانلود کرده و
آن‌ها را به‌صورت <symbol> در فایل web/icons.svg می‌نویسد.

اجرا:  python tools/fetch_icons.py
"""
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "icons.svg")
BASE = "https://unpkg.com/lucide-static@latest/icons/{}.svg"

# نام هر جای‌گاه به همراه نام‌های جایگزین در لوساید
SLOTS = {
    "dashboard": ["layout-dashboard", "layout-grid", "gauge"],
    "invoice-sale": ["receipt"],
    "proforma": ["clipboard-list", "file-pen"],
    "sale-return": ["undo-2", "corner-up-left"],
    "purchase": ["arrow-down-to-line", "truck"],
    "purchase-return": ["redo-2", "corner-up-right"],
    "battery": ["battery-charging", "battery-full"],
    "scrap": ["recycle"],
    "scrap-sale": ["truck", "shopping-cart"],
    "inventory": ["boxes", "package"],
    "cardex": ["chart-column", "bar-chart-3", "activity"],
    "transfer": ["arrow-left-right", "repeat"],
    "adjust": ["sliders-horizontal"],
    "money-in": ["banknote", "wallet"],
    "journal": ["book-open"],
    "trial": ["scale"],
    "profit": ["trending-up"],
    "balance": ["landmark", "building-2"],
    "cheque-in": ["file-check-2", "file-check"],
    "cheque-out": ["file-x-2", "file-minus"],
    "cheque-due": ["clock"],
    "parties": ["users"],
    "products": ["tag"],
    "groups": ["layers"],
    "units": ["ruler"],
    "warehouses": ["warehouse", "building-2"],
    "report-sales": ["chart-line"],
    "report-products": ["star"],
    "report-debtors": ["user-x"],
    "report-inventory": ["coins"],
    "users": ["shield-check"],
    "activity": ["history"],
    "audit": ["file-search"],
    "notes": ["sticky-note"],
    "backup": ["database-backup", "hard-drive-download"],
    "settings": ["settings"],
    "logout": ["log-out"],
    "menu": ["menu"],
    "close": ["x"],
    "search": ["search"],
    "plus": ["plus"],
    "edit": ["pencil"],
    "trash": ["trash-2"],
    "save": ["save"],
    "chevron-down": ["chevron-down"],
    "calendar": ["calendar"],
    "printer": ["printer"],
    "download": ["download"],
    "upload": ["upload"],
    "warning": ["triangle-alert", "alert-triangle"],
    "check": ["check"],
    "info": ["info"],
    "refresh": ["rotate-cw"],
    "filter": ["filter"],
    "card": ["credit-card"],
    "empty": ["package-open", "inbox"],
    "command": ["command"],
    "sort": ["chevrons-up-down", "arrow-up-down"],
    "close-circle": ["circle-x"],
    "eye": ["eye"],
    "lock": ["lock"],
    "keyboard": ["keyboard"],
}

_INNER = re.compile(r"<svg[^>]*>(.*)</svg>", re.S)


def fetch(name):
    url = BASE.format(name)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read().decode("utf-8")
    except Exception:  # noqa: BLE001 - شبکه؛ نام جایگزین امتحان می‌شود
        return None


def build():
    symbols, failed = [], []
    for slot, candidates in SLOTS.items():
        svg = None
        for cand in candidates:
            svg = fetch(cand)
            if svg and "<path" in svg:
                break
            svg = None
        if not svg:
            failed.append(slot)
            continue
        m = _INNER.search(svg)
        inner = m.group(1) if m else ""
        inner = re.sub(r"\s+", " ", inner).strip()
        inner = inner.replace(' stroke-width="2"', ' stroke-width="1.75"')
        symbols.append(
            '<symbol id="i-{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">{}</symbol>'
            .format(slot, inner))
    sprite = ('<svg xmlns="http://www.w3.org/2000/svg" style="display:none" '
              'aria-hidden="true"><defs>{}</defs></svg>'.format("\n".join(symbols)))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(sprite + "\n")
    print("icons written: {} -> {}".format(len(symbols), OUT))
    if failed:
        print("MISSING SLOTS: {}".format(", ".join(failed)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(build())
