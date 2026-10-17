"""هستهٔ سیستم لایسنس برنامه.

اصول امنیتی این ماژول:

* **امضای نامتقارن Ed25519.** کلید خصوصی فقط در برنامهٔ مدیر (صادرکننده) است؛
  برنامهٔ کاربری تنها کلید عمومی را دارد. پس ساختن لایسنس جعلی حتی با داشتن
  سورس کامل برنامهٔ کاربری ممکن نیست.
* **گره خوردن به سخت‌افزار.** لایسنس به اثر انگشت دستگاه (شناسهٔ ویندوز +
  سریال درایو سیستم) مقید می‌شود؛ کپی پوشهٔ برنامه روی رایانهٔ دیگر کار نمی‌کند.
* **دستکاری = باطل.** هر تغییری در متن لایسنس امضا را می‌شکند.
* **عقب‌بردن ساعت سیستم تشخیص داده می‌شود** (نگهبان تاریخ آخرین اجرا).

هشدار صادقانه: هیچ برنامهٔ آفلاینی «کرک‌ناپذیر مطلق» نیست. کسی که فایل اجرایی
را در اختیار دارد می‌تواند با تلاش کافی چک را دور بزند. کاری که این ماژول
تضمین می‌کند این است که *ساختن* لایسنس بدون کلید خصوصی ناممکن است و
*کپی/دستکاری* لایسنس و برنامه کار نمی‌کند.
"""
import base64
import hashlib
import hmac
import json
import os
import platform
import re
import uuid

APP_ID = "hesabdari-saba"
LICENSE_VERSION = 1
KEY_PREFIX = "SABA1"

# قابلیت‌های پرمیوم. کلید هر قابلیت در متن لایسنس قرار می‌گیرد.
FEATURES = {
    "multi_warehouse": "چند انبار، انتقال و اصلاح موجودی چند‌انباری",
    "more_users": "بیش از یک کاربر فعال",
    "backup": "پشتیبان‌گیری، بازیابی و خروجی اکسل (CSV)",
    "adv_reports": "گزارش‌های مالی پیشرفته (تراز آزمایشی، سود و زیان، ترازنامه)",
    "audit": "ردیابی حذف و اصلاح و گردش فعالیت کاربران",
}
ALL_FEATURES = tuple(FEATURES.keys())

EDITIONS = {
    "base": {"label": "پایه", "features": ()},
    "premium": {"label": "پرمیوم", "features": ALL_FEATURES},
}

# سهمیهٔ کاربران هر نسخه (سقف مطلق؛ عدد دقیق از خود لایسنس می‌آید)
EDITION_MAX_SEATS = {"base": 1, "premium": 100}

_DEFAULT_PEPPER = b"hesabdari-saba-license-state-v1"
_DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")


class LicenseError(Exception):
    """خطای اعتبارسنجی لایسنس همراه با کد قابل‌نمایش."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------------ رمزنگاری
def _b64e(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text):
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def canonical(payload):
    """نمایش بایتی یکسان از لایسنس؛ هر دو طرف باید همین را امضا/بررسی کنند."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _ed25519_private(raw_bytes):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(raw_bytes)


def _ed25519_public(raw_bytes):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    return Ed25519PublicKey.from_public_bytes(raw_bytes)


def generate_keypair():
    """(کلید خصوصی، کلید عمومی) به‌صورت بایت خام ۳۲ بایتی."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    priv = Ed25519PrivateKey.generate()
    raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    return raw, pub


def public_key_from_private(priv_raw):
    """کلید عمومی متناظر با یک کلید خصوصی (برای اطمینان از درستی جفت‌کلید)."""
    from cryptography.hazmat.primitives import serialization
    key = _ed25519_private(priv_raw).public_key()
    return key.public_bytes(encoding=serialization.Encoding.Raw,
                            format=serialization.PublicFormat.Raw)


def keypair_to_text(priv_raw, pub_raw):
    return _b64e(priv_raw), _b64e(pub_raw)


def keypair_from_text(priv_text, pub_text):
    return _b64d(priv_text.strip()), _b64d(pub_text.strip())


def sign_bytes(message, priv_raw):
    """امضای خام Ed25519 روی بایت‌ها (مبنای آزمون بردارهای RFC 8032)."""
    return _ed25519_private(priv_raw).sign(message)


def verify_bytes(message, sig_raw, pub_raw):
    from cryptography.exceptions import InvalidSignature
    try:
        _ed25519_public(pub_raw).verify(sig_raw, message)
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def sign_payload(payload, priv_raw):
    """امضای لایسنس با کلید خصوصی؛ خروجی base64."""
    return _b64e(sign_bytes(canonical(payload), priv_raw))


def verify_signature(payload, sig_text, pub_raw):
    try:
        sig = _b64d(sig_text)
    except Exception:
        return False
    return verify_bytes(canonical(payload), sig, pub_raw)


# ------------------------------------------------------- قالب متن لایسنس
def encode_license(payload, sig_text):
    """لایسنس به‌صورت یک متن قابل کپی/ارسال."""
    return "{}.{}.{}".format(KEY_PREFIX,
                             _b64e(canonical(payload)), sig_text.strip())


def decode_license(text):
    """متن لایسنس را به (payload، sig) تبدیل می‌کند. متد PAZIRANDE سخت‌گیر است."""
    if not text:
        raise LicenseError("empty", "لایسنس دریافت نشد")
    raw = "".join(text.split())
    parts = raw.split(".")
    if len(parts) != 3 or parts[0] != KEY_PREFIX:
        raise LicenseError("format", "قالب لایسنس درست نیست")
    try:
        payload = json.loads(_b64d(parts[1]).decode("utf-8"))
    except Exception:
        raise LicenseError("format", "محتوای لایسنس خوانده نشد")
    if not isinstance(payload, dict):
        raise LicenseError("format", "محتوای لایسنس درست نیست")
    return payload, parts[2]


def license_file_text(payload, sig_text, customer=""):
    """محتوای فایل `.key` که به مشتری داده می‌شود."""
    return json.dumps({
        "app": APP_ID,
        "v": LICENSE_VERSION,
        "customer": customer,
        "payload": payload,
        "sig": sig_text,
        "key": encode_license(payload, sig_text),
    }, ensure_ascii=False, indent=2)


def decode_license_file(text):
    """فایل `.key` یا متن خام لایسنس را می‌پذیرد."""
    text = (text or "").strip()
    if not text:
        raise LicenseError("empty", "فایل لایسنس خالی است")
    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            raise LicenseError("format", "فایل لایسنس خوانده نشد")
        if isinstance(data, dict) and isinstance(data.get("payload"), dict):
            return data["payload"], str(data.get("sig", ""))
        raise LicenseError("format", "فایل لایسنس ساختار درستی ندارد")
    return decode_license(text)


# --------------------------------------------------------- اثر انگشت دستگاه
def _windows_fingerprint():
    """شناسهٔ ویندوز + سریال درایو سیستم؛ روی کپی پوشه جابه‌جا نمی‌شود."""
    parts = []
    try:
        import winreg
        for view in (getattr(winreg, "KEY_WOW64_64KEY", 0), 0):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    r"SOFTWARE\Microsoft\Cryptography", 0,
                                    winreg.KEY_READ | view) as k:
                    parts.append(str(winreg.QueryValueEx(k, "MachineGuid")[0]))
                    break
            except OSError:
                continue
    except Exception:
        pass
    try:
        import ctypes
        drive = os.environ.get("SystemDrive", "C:") + "\\"
        serial = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive), None, 0, ctypes.byref(serial),
            None, None, None, 0)
        if ok:
            parts.append(str(serial.value))
    except Exception:
        pass
    return parts


def machine_fingerprint(data_dir=None):
    """اثر انگشت پایدار دستگاه (۶۴ نویسهٔ هگز).

    اگر شناسهٔ سیستمی در دسترس نباشد (مثلاً در آزمون‌ها)، یک شناسهٔ تصادفی
    پایدار در پوشهٔ داده ساخته می‌شود. این حالت ضعیف‌تر است چون با کپی پوشه
    منتقل می‌شود؛ بنابراین روی ویندوز همیشه مسیر شناسهٔ سیستمی اولویت دارد.
    """
    parts = _windows_fingerprint()
    raw = "|".join(parts) + "|" + platform.node() + "|" + APP_ID
    if not parts:
        raw += "|" + _fallback_machine_id(data_dir)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fallback_machine_id(data_dir):
    path = os.path.join(data_dir or ".", ".machine-id")
    try:
        with open(path, encoding="utf-8") as f:
            val = f.read().strip()
        if val:
            return val
    except OSError:
        pass
    val = uuid.uuid4().hex
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(val)
    except OSError:
        pass
    return val


def machine_code(fingerprint):
    """نسخهٔ کوتاه و خوانا برای ارسال به مشتری: XXXX-XXXX-XXXX-XXXX."""
    head = fingerprint[:20].upper()
    return "-".join(head[i:i + 4] for i in range(0, 20, 4))


def normalize_machine(text):
    """کد دستگاه یا اثر انگشت را به شکل مقایسه‌پذیر (فقط حروف کوچک) درمی‌آورد."""
    return re.sub(r"[\s\-_.]", "", (text or "")).lower()


def machine_matches(bound, fingerprint):
    """آیا قید دستگاه لایسنس با این رایانه می‌خواند؟

    هم کد کوتاه دستگاه (۲۰ نویسه) و هم اثر انگشت کامل (۶۴ نویسه) پذیرفته می‌شود.
    """
    b = normalize_machine(bound)
    if b in ("", "*"):
        return True
    if b == normalize_machine(fingerprint):
        return True
    return b == normalize_machine(machine_code(fingerprint))


# ------------------------------------------------------- اعتبارسنجی لایسنس
def _check_dates(payload, today):
    issued = str(payload.get("issued") or "")
    expires = str(payload.get("expires") or "")
    if issued and _DATE_RE.match(issued) and issued > today:
        raise LicenseError("not_yet", "تاریخ صدور این لایسنس از تاریخ سیستم جلوتر است"
                                       " (ساعت سیستم را بررسی کنید).")
    if expires:
        if not _DATE_RE.match(expires):
            raise LicenseError("expired", "تاریخ انقضای لایسنس معتبر نیست.")
        if today > expires:
            raise LicenseError("expired", "این لایسنس در تاریخ {} منقضی شده است."
                                           .format(expires))


def verify_license(text, public_key_raw, fingerprint=None, today=None,
                   data_dir=None):
    """اعتبارسنجی کامل یک لایسنس.

    خروجی: dict شامل valid, reason, message, payload, edition, features, seats
    هیچ‌وقت استثنا پرتاب نمی‌کند؛ خطا در `reason` برمی‌گردد.
    """
    from . import jdate
    today = today or jdate.today_str()
    result = {"valid": False, "reason": "", "message": "", "payload": None,
              "edition": "base", "features": (), "seats": 1, "customer": "",
              "online": False}
    try:
        payload, sig = decode_license_file(text)
    except LicenseError as exc:
        result.update(reason=exc.code, message=exc.message)
        return result

    if not verify_signature(payload, sig, public_key_raw):
        result.update(reason="signature",
                      message="امضای لایسنس معتبر نیست. متن لایسنس دست‌کاری شده"
                              " یا مربوط به برنامهٔ دیگری است.")
        return result
    if str(payload.get("app") or "") != APP_ID:
        result.update(reason="app", message="این لایسنس برای این برنامه صادر نشده است.")
        return result
    try:
        version = int(payload.get("v") or LICENSE_VERSION)
    except (TypeError, ValueError):
        version = LICENSE_VERSION
    if version > LICENSE_VERSION:
        result.update(reason="version",
                      message="این لایسنس مربوط به نسخهٔ جدیدتری از برنامه است.")
        return result

    bound = str(payload.get("machine") or "*")
    fingerprint = fingerprint or machine_fingerprint(data_dir)
    if not machine_matches(bound, fingerprint):
        result.update(reason="machine",
                      message="این لایسنس برای رایانهٔ دیگری صادر شده است.")
        return result

    try:
        _check_dates(payload, today)
    except LicenseError as exc:
        result.update(reason=exc.code, message=exc.message)
        return result

    edition = str(payload.get("edition") or "base").lower()
    if edition not in EDITIONS:
        edition = "base"
    feats = payload.get("features")
    if not isinstance(feats, list):
        feats = list(EDITIONS[edition]["features"])
    feats = tuple(f for f in feats if f in FEATURES)
    try:
        seats = int(payload.get("seats") or 1)
    except (TypeError, ValueError):
        seats = 1
    seats = max(1, min(seats, EDITION_MAX_SEATS.get(edition, 1)))

    result.update(valid=True, reason="ok", message="لایسنس معتبر است.",
                  payload=payload, edition=edition, features=feats, seats=seats,
                  customer=str(payload.get("customer") or ""),
                  online=bool(payload.get("online")))
    return result


# ----------------------------------------------- نگهبان تاریخ (ضد عقب‌بردن)
def _state_path(data_dir):
    return os.path.join(data_dir or ".", "license_state.json")


def _state_tag(fingerprint):
    return hmac.new(_DEFAULT_PEPPER, fingerprint.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def state_load(path, fingerprint):
    """خواندن یک فایل وضعیت امضاشده (HMAC) و تشخیص دست‌کاری.

    هر فایل وضعیتی که برنامه می‌نویسد یک `tag` دارد که با کلید مشتق‌شده از
    اثر انگشت همین دستگاه ساخته می‌شود؛ پس اگر کسی فایل را دست‌کاری کند
    (مثلاً تاریخ آخرین بررسی را جلو ببرد) متوجه می‌شویم.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"tampered": False}
    if not isinstance(data, dict):
        return {"tampered": True}
    tag = str(data.get("tag") or "")
    body = json.dumps({k: v for k, v in data.items() if k != "tag"},
                      sort_keys=True, ensure_ascii=False).encode("utf-8")
    expect = hmac.new(_state_tag(fingerprint).encode("utf-8"), body,
                      hashlib.sha256).hexdigest()
    out = dict(data)
    out["tampered"] = not hmac.compare_digest(tag, expect)
    return out


def state_save(path, fingerprint, data):
    """نوشتن فایل وضعیت همراه امضای HMAC (خطاها بی‌صدا نادیده می‌روند)."""
    data = dict(data or {})
    data.pop("tag", None)
    body = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    data["tag"] = hmac.new(_state_tag(fingerprint).encode("utf-8"), body,
                           hashlib.sha256).hexdigest()
    try:
        folder = os.path.dirname(os.path.abspath(path))
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass
    return data


def read_state(data_dir, fingerprint):
    """وضعیت ذخیره‌شدهٔ لایسنس؛ در صورت دست‌کاری `tampered` True می‌شود."""
    return state_load(_state_path(data_dir), fingerprint)


def write_state(data_dir, fingerprint, last_seen, extra=None):
    data = {"last_seen": last_seen}
    if extra:
        data.update(extra)
    return state_save(_state_path(data_dir), fingerprint, data)


def clock_rolled_back(data_dir, fingerprint, today):
    """اگر ساعت سیستم از آخرین اجرا عقب‌تر باشد، دست‌کاری است."""
    state = read_state(data_dir, fingerprint)
    last = str(state.get("last_seen") or "")
    if state.get("tampered"):
        return True
    return bool(last and _DATE_RE.match(last) and today < last)


# ------------------------------------------------------- بارگذاری کلیدها
def read_key(path):
    """کلید خام را از فایل می‌خواند؛ اگر نبود یا خراب بود None برمی‌گرداند."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
    except OSError:
        return None
    try:
        raw = _b64d(text)
    except Exception:
        return None
    return raw if len(raw) == 32 else None


def find_public_key(paths):
    for p in paths:
        raw = read_key(p)
        if raw:
            return raw, p
    return None, ""


# ------------------------------------------------------------ صدور لایسنس
def build_payload(customer, edition="premium", features=None, seats=None,
                  machine="*", months=12, today=None, note="", lic_id="",
                  extra=None, days=None):
    """ساخت بدنهٔ لایسنس. تاریخ‌ها شمسی «۱۴۰۵/۰۷/۲۲» هستند.

    مدت اعتبار دو حالت دارد: `days` (شمار روز، دقیق) و `months` (شمار ماه،
    پیش‌فرض سازگاری با لایسنس‌های قدیمی). اگر `days` بدهید، همان ملاک است.

    `extra` کلیدهای افزوده را در بدنه می‌گذارد (مثل `online: true` برای
    لایسنس‌هایی که سرور آنلاین صادر می‌کند و باید دوره‌ای بررسی شوند).
    چون امضا روی کل بدنه است، هر تغییری در این کلیدها امضا را می‌شکند.
    """
    from . import jdate
    today = today or jdate.today_str()
    if edition not in EDITIONS:
        edition = "premium"
    if features is None:
        features = list(EDITIONS[edition]["features"])
    features = [f for f in features if f in FEATURES]
    if seats is None:
        seats = EDITION_MAX_SEATS.get(edition, 1)
    seats = max(1, min(int(seats), EDITION_MAX_SEATS.get(edition, 1)))
    y, m, d = (int(x) for x in today.split("/"))
    if days is not None and int(days) > 0:
        expires = _add_days(y, m, d, int(days))
    else:
        expires = _add_months(y, m, d, months) if months else ""
    payload = {
        "app": APP_ID, "v": LICENSE_VERSION, "lic": lic_id,
        "customer": customer, "edition": edition, "features": sorted(features),
        "seats": seats, "machine": (machine or "*").strip(),
        "issued": today, "expires": expires,
        "note": note,
    }
    for key, value in (extra or {}).items():
        if key not in payload:                  # کلیدهای پایه بازنویسی نمی‌شوند
            payload[key] = value
    return payload


def _add_months(y, m, d, months):
    from . import jdate
    total = (y * 12 + (m - 1)) + int(months)
    ny, nm = divmod(total, 12)
    return jdate.fmt(ny, nm + 1, d)


def _add_days(y, m, d, days):
    from . import jdate
    return jdate.add_days(jdate.fmt(y, m, d), int(days))


def issue_license(private_key_raw, **kw):
    """صدور لایسنس امضاشده با کلید خصوصی ریشه.

    خروجی: dict شامل payload، sig، key (متن تک‌خطی) و file (محتوای فایل .key)
    """
    payload = build_payload(**kw)
    sig = sign_payload(payload, private_key_raw)
    return {"payload": payload, "sig": sig,
            "key": encode_license(payload, sig),
            "file": license_file_text(payload, sig, customer=payload.get("customer", ""))}
