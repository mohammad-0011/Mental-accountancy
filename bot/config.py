"""تنظیمات سرور لایسنس و بات بله.

همهٔ مقادیر از متغیرهای محیطی خوانده می‌شوند و در صورت نبودشان از فایل
`.env` کنار همین ماژول (یا از پیش‌فرض‌های امن) استفاده می‌شود. هیچ رمزی
داخل کد نوشته نشده است تا بشود بدون تغییر سورس، توکن را عوض کرد.

روی سرویس میزبانی (justrunmy.app) مقادیر را در بخش Environment Variables
بگذارید؛ همان نام‌های فایل `.env.example`.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
KEYS_DIR = os.path.join(BASE_DIR, "keys")
DATA_DIR = os.path.join(BASE_DIR, "data")


def load_env_file(path=ENV_PATH):
    """خواندن سادهٔ فایل .env (خطوط KEY=VALUE) بدون وابستگی بیرونی.

    متغیرهای محیطی موجود هرگز بازنویسی نمی‌شوند (اولویت با محیط).
    """
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def env(key, default=""):
    return (os.environ.get(key) or default).strip()


def env_int(key, default=0):
    try:
        return int(env(key) or default)
    except (TypeError, ValueError):
        return default


def env_bool(key, default=False):
    val = env(key).lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def parse_ids(raw):
    """«123, 456» → {123, 456} (کاراکترهای جداکنندهٔ رایج پذیرفته می‌شوند)."""
    out = set()
    for part in (raw or "").replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


def _read_key_file(name):
    try:
        with open(os.path.join(KEYS_DIR, name), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


class Config:
    """تنظیمات فعال؛ یک‌بار در شروع برنامه ساخته می‌شود."""

    def __init__(self, load_env=True):
        if load_env:
            load_env_file()

        # ---------------------------------------------------------- بات بله
        # توکن بات از BotFather بله. هرگز داخل کد نوشته نمی‌شود.
        self.bot_token = env("BALE_BOT_TOKEN") or env("BOT_TOKEN")
        self.api_base = env("BALE_API_BASE", "https://tapi.bale.ai").rstrip("/")
        self.poll_timeout = max(5, env_int("POLL_TIMEOUT", 25))
        self.admin_ids = parse_ids(env("ADMIN_CHAT_IDS"))
        self.startup_ping = env_bool("STARTUP_PING", False)

        # ------------------------------------------------------------ لایسنس
        # کلید خصوصی ریشه: اولویت با متغیر محیطی (روی میزبان امن‌تر است).
        from sabalic import licensing

        self.private_key_text = env("SABA_ROOT_PRIVATE_KEY") or _read_key_file(
            "root_private.key")
        self.public_key_text = env("SABA_ROOT_PUBLIC_KEY") or _read_key_file(
            "root_public.key")
        self.private_key = None
        self.public_key = None
        try:
            if self.private_key_text:
                self.private_key = licensing._b64d(self.private_key_text)
            if self.public_key_text:
                self.public_key = licensing._b64d(self.public_key_text)
        except Exception:                       # noqa: BLE001 - کلید خراب = کلید نبودن
            self.private_key = None
            self.public_key = None

        # --------------------------------------------------- پیش‌فرض صدور
        self.default_edition = env("DEFAULT_EDITION", "premium").lower()
        if self.default_edition not in ("base", "premium"):
            self.default_edition = "premium"
        self.default_months = env_int("DEFAULT_MONTHS", 12)
        # مدت پیش‌فرض به «روز» (۳۶۵ = یک سال). صفر یعنی بدون انقضا.
        self.default_days = max(0, env_int("DEFAULT_DAYS", 365))
        self.default_seats = env_int("DEFAULT_SEATS", 3)
        # چند روز بی‌اتصال بودن مجاز است پیش از آنکه لایسنس «کهنه» شود.
        self.grace_days = max(1, env_int("GRACE_DAYS", 15))
        # کلید نرم‌افزاری کلاینت (دروازهٔ نرم، نه مرز امنیتی واقعی).
        self.client_token = env("CLIENT_TOKEN")
        # توکن مدیر: فقط برنامهٔ فروشنده آن را دارد و با آن درخواست‌های
        # لایسنس را از داخل برنامه تأیید/رد می‌کند. خالی = این در از برنامه
        # بسته است و تأیید تنها از بات بله انجام می‌شود.
        self.admin_token = env("SABA_ADMIN_TOKEN")
        # سقف درخواست هر نشانی IP در ساعت (ضد حملهٔ ساده)
        self.rate_limit = max(5, env_int("RATE_LIMIT_PER_HOUR", 60))

        # ------------------------------------------------------------ عمومی
        self.db_path = env("BOT_DB_PATH") or os.path.join(DATA_DIR, "bot.db")
        self.public_url = env("PUBLIC_URL").rstrip("/")
        self.owner_name = env("OWNER_NAME", "فروشنده")
        # کدهای نسخه/قابلیت‌ها از هستهٔ مشترک می‌آید (نه کپی دستی)
        self.app_id = licensing.APP_ID

    # ------------------------------------------------------------- بررسی‌ها
    def missing(self):
        """فهرست چیزهایی که برای کار کردن سرور لازم است و نیست."""
        problems = []
        if not self.bot_token:
            problems.append("BALE_BOT_TOKEN (توکن بات بله) تنظیم نشده است")
        if not self.private_key:
            problems.append("کلید خصوصی ریشه پیدا نشد (keys/root_private.key "
                            "یا SABA_ROOT_PRIVATE_KEY)")
        if not self.public_key:
            problems.append("کلید عمومی ریشه پیدا نشد (keys/root_public.key)")
        if self.private_key and self.public_key:
            from sabalic import licensing
            try:
                derived = licensing.public_key_from_private(self.private_key)
            except Exception:                   # noqa: BLE001
                derived = b""
            if derived != self.public_key:
                problems.append("کلید خصوصی و عمومی با هم نمی‌خوانند")
        if not self.admin_ids:
            problems.append("ADMIN_CHAT_IDS خالی است؛ هیچ‌کس نمی‌تواند لایسنس "
                            "صادر کند (با /whoami شناسهٔ خود را بگیرید)")
        return problems

    def is_admin(self, chat_id):
        try:
            return int(chat_id) in self.admin_ids
        except (TypeError, ValueError):
            return False


CONFIG = Config(load_env=False)


def get_config(reload_env=True):
    """تنظیمات جاری؛ در آزمون‌ها با reload_env=False از فایل .env صرف‌نظر می‌کند."""
    global CONFIG
    if reload_env:
        CONFIG = Config(load_env=True)
    return CONFIG
