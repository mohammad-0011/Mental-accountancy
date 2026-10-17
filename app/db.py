"""لایه داده: ساخت پایگاه‌داده SQLite، جدول‌ها و دادهٔ اولیه.

تمام تاریخ‌ها به‌صورت رشته شمسی «۱۴۰۵/۰۷/۲۲» ذخیره می‌شوند.
"""
import os
import sqlite3
import hashlib
import binascii
from datetime import datetime


def money(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0

from . import jdate

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    full_name TEXT DEFAULT '',
    role TEXT DEFAULT 'user',
    active INTEGER DEFAULT 1,
    created_at TEXT,
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    note TEXT DEFAULT '',
    perms TEXT DEFAULT '',          -- JSON ویژگی‌های مجاز کاربر
    last_login TEXT DEFAULT '',
    last_ip TEXT DEFAULT '',
    failed_attempts INTEGER DEFAULT 0,
    locked_until TEXT DEFAULT '',
    created_by TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT, username TEXT, action TEXT, detail TEXT
);

-- دفتر لایسنس‌های صادرشده (فقط در برنامهٔ مدیر استفاده می‌شود)
CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lic_id TEXT,                    -- شناسهٔ خوانا مثل SB-1405-0007
    customer TEXT DEFAULT '',
    edition TEXT DEFAULT 'premium',
    features TEXT DEFAULT '',       -- JSON فهرست قابلیت‌ها
    seats INTEGER DEFAULT 1,
    machine TEXT DEFAULT '*',       -- اثر انگشت دستگاه یا * (آزاد)
    issued TEXT DEFAULT '',
    expires TEXT DEFAULT '',
    note TEXT DEFAULT '',
    key_text TEXT DEFAULT '',
    created_at TEXT
);

-- رویدادهای مربوط به لایسنس روی همین دستگاه
CREATE TABLE IF NOT EXISTS license_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT, action TEXT, detail TEXT
);

CREATE TABLE IF NOT EXISTS parties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT NOT NULL,
    party_type TEXT DEFAULT 'customer',
    national_id TEXT DEFAULT '',
    economic_code TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    mobile TEXT DEFAULT '',
    address TEXT DEFAULT '',
    city TEXT DEFAULT '',
    opening_balance REAL DEFAULT 0,
    credit_limit REAL DEFAULT 0,
    note TEXT DEFAULT '',
    active INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS product_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT DEFAULT '',
    is_default INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    barcode TEXT DEFAULT '',
    name TEXT NOT NULL,
    group_id INTEGER,
    unit_id INTEGER,
    brand TEXT DEFAULT '',
    battery_type TEXT DEFAULT '',
    amperage TEXT DEFAULT '',
    capacity_ah REAL DEFAULT 0,
    warranty_months INTEGER DEFAULT 0,
    purchase_price REAL DEFAULT 0,
    sale_price REAL DEFAULT 0,
    wholesale_price REAL DEFAULT 0,
    reorder_level REAL DEFAULT 0,
    is_battery INTEGER DEFAULT 1,
    is_scrap INTEGER DEFAULT 0,
    note TEXT DEFAULT '',
    active INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS stock_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    product_id INTEGER NOT NULL,
    warehouse_id INTEGER,
    qty_in REAL DEFAULT 0,
    qty_out REAL DEFAULT 0,
    unit_cost REAL DEFAULT 0,
    ref_type TEXT,
    ref_id INTEGER,
    description TEXT DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT,
    kind TEXT NOT NULL,
    date TEXT,
    party_id INTEGER,
    warehouse_id INTEGER,
    subtotal REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax_rate REAL DEFAULT 9,
    tax REAL DEFAULT 0,
    total REAL DEFAULT 0,
    paid_cash REAL DEFAULT 0,
    paid_card REAL DEFAULT 0,
    paid_cheque REAL DEFAULT 0,
    cost_total REAL DEFAULT 0,
    status TEXT DEFAULT 'final',
    note TEXT DEFAULT '',
    username TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    product_id INTEGER,
    description TEXT DEFAULT '',
    serial TEXT DEFAULT '',
    warranty_months INTEGER DEFAULT 0,
    qty REAL DEFAULT 0,
    unit_price REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax_rate REAL DEFAULT 9,
    tax REAL DEFAULT 0,
    total REAL DEFAULT 0,
    cost_price REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cheques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT,
    ctype TEXT DEFAULT 'receivable',
    party_id INTEGER,
    bank TEXT DEFAULT '',
    branch TEXT DEFAULT '',
    account TEXT DEFAULT '',
    amount REAL DEFAULT 0,
    issue_date TEXT,
    due_date TEXT,
    status TEXT DEFAULT 'in_hand',
    is_guarantee INTEGER DEFAULT 0,
    note TEXT DEFAULT '',
    username TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT,
    date TEXT,
    party_id INTEGER,
    kind TEXT DEFAULT 'receive',
    amount REAL DEFAULT 0,
    method TEXT DEFAULT 'cash',
    cheque_id INTEGER,
    ref_invoice TEXT DEFAULT '',
    description TEXT DEFAULT '',
    username TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT NOT NULL UNIQUE,
    atype TEXT DEFAULT 'asset'
);

CREATE TABLE IF NOT EXISTS journals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT,
    date TEXT,
    description TEXT DEFAULT '',
    ref_type TEXT DEFAULT '',
    ref_id INTEGER,
    username TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id INTEGER NOT NULL,
    account TEXT,
    debit REAL DEFAULT 0,
    credit REAL DEFAULT 0,
    description TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS party_tx (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    party_id INTEGER NOT NULL,
    ref_type TEXT,
    ref_id INTEGER,
    description TEXT DEFAULT '',
    debit REAL DEFAULT 0,
    credit REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS battery_serials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER,
    serial TEXT NOT NULL,
    party_id INTEGER,
    invoice_id INTEGER,
    sold_at TEXT,
    warranty_months INTEGER DEFAULT 0,
    warranty_end TEXT,
    status TEXT DEFAULT 'in_stock',
    note TEXT DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS scrap_batteries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    party_id INTEGER,
    product_id INTEGER,
    brand TEXT DEFAULT '',
    amperage TEXT DEFAULT '',
    battery_type TEXT DEFAULT '',
    qty REAL DEFAULT 1,
    weight_kg REAL DEFAULT 0,
    price_per_kg REAL DEFAULT 0,
    unit_price REAL DEFAULT 0,
    amount REAL DEFAULT 0,
    method TEXT DEFAULT 'cash',
    warehouse_id INTEGER,
    ref_invoice_id INTEGER,
    out_qty REAL DEFAULT 0,
    out_weight REAL DEFAULT 0,
    description TEXT DEFAULT '',
    username TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS scrap_sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    party_id INTEGER,
    qty REAL DEFAULT 0,
    weight_kg REAL DEFAULT 0,
    price_per_kg REAL DEFAULT 0,
    amount REAL DEFAULT 0,
    method TEXT DEFAULT 'cash',
    description TEXT DEFAULT '',
    username TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    body TEXT DEFAULT '',
    remind_at TEXT,
    done INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT,
    username TEXT,
    action TEXT,
    entity TEXT,
    entity_id INTEGER,
    detail TEXT
);
"""

DEFAULT_ACCOUNTS = [
    ("1010", "صندوق", "asset"),
    ("1020", "بانک", "asset"),
    ("1100", "حساب‌های دریافتنی", "asset"),
    ("1200", "موجودی کالا", "asset"),
    ("1300", "اسناد دریافتنی (چک)", "asset"),
    ("1400", "مالیات بر ارزش افزوده خرید", "asset"),
    ("2010", "حساب‌های پرداختنی", "liability"),
    ("2020", "اسناد پرداختنی (چک)", "liability"),
    ("2030", "مالیات بر ارزش افزوده پرداختنی", "liability"),
    ("3010", "سرمایه", "equity"),
    ("4010", "فروش کالا", "revenue"),
    ("4020", "فروش ضایعات باتری", "revenue"),
    ("4030", "برگشت از فروش", "revenue"),
    ("5010", "بهای تمام‌شده کالای فروش‌رفته", "expense"),
    ("5020", "خرید کالا", "expense"),
    ("5030", "هزینه‌های عملیاتی", "expense"),
    ("5040", "تخفیف فروش", "expense"),
]

DEFAULT_UNITS = ["عدد", "حلقه", "کیلوگرم", "متر", "بسته", "کارتن", "لیتر"]
DEFAULT_GROUPS = ["باتری خودرو", "باتری یو‌پی‌اس", "باتری موتور", "سایر کالاها"]


def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return binascii.hexlify(salt).decode() + "$" + binascii.hexlify(dk).decode()


def verify_password(password, stored):
    try:
        salt_hex, _ = stored.split("$", 1)
        salt = binascii.unhexlify(salt_hex)
    except (ValueError, binascii.Error):
        return False
    return hash_password(password, salt) == stored


class DB:
    def __init__(self, path):
        self.path = path
        fresh = not os.path.exists(path)
        folder = os.path.dirname(os.path.abspath(path))
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        if not fresh:
            self.ensure_columns()
        if fresh or not self.get_setting("installed"):
            self.seed()

    # ------------------------------------------------------------- مهاجرت
    # ستون‌هایی که در نسخه‌های قبلی نبودند؛ روی پایگاه‌دادهٔ موجود اضافه می‌شوند.
    ADDED_COLUMNS = {
        "users": {
            "email": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "note": "TEXT DEFAULT ''",
            "perms": "TEXT DEFAULT ''",
            "last_login": "TEXT DEFAULT ''",
            "last_ip": "TEXT DEFAULT ''",
            "failed_attempts": "INTEGER DEFAULT 0",
            "locked_until": "TEXT DEFAULT ''",
            "created_by": "TEXT DEFAULT ''",
        },
    }

    def ensure_columns(self):
        """افزودن ستون‌های جدید به پایگاه‌دادهٔ قدیمی بدون از دست رفتن داده."""
        changed = False
        for table, cols in self.ADDED_COLUMNS.items():
            existing = self.columns(table)
            for name, decl in cols.items():
                if name in existing:
                    continue
                self.conn.execute(
                    "ALTER TABLE {} ADD COLUMN {} {}".format(table, name, decl))
                changed = True
            if getattr(self, "_cols", None) is not None:
                self._cols.pop(table, None)
        if changed:
            self.conn.commit()
        # هر نصب باید حداقل یک مدیر فعال داشته باشد
        admins = self.scalar(
            "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1", (), 0)
        if not admins:
            self.conn.execute("UPDATE users SET role='admin' WHERE id="
                              "(SELECT MIN(id) FROM users)")
            self.conn.commit()

    # ------------------------------------------------------------------ utils
    def q(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        return cur

    def rows(self, sql, params=()):
        return [dict(r) for r in self.q(sql, params).fetchall()]

    def one(self, sql, params=()):
        r = self.q(sql, params).fetchone()
        return dict(r) if r else None

    def scalar(self, sql, params=(), default=0):
        r = self.q(sql, params).fetchone()
        if r is None or r[0] is None:
            return default
        return r[0]

    def columns(self, table):
        cache = getattr(self, "_cols", None)
        if cache is None:
            cache = self._cols = {}
        if table not in cache:
            cache[table] = {r[1] for r in self.conn.execute(
                "PRAGMA table_info({})".format(table)).fetchall()}
        return cache[table]

    def _clean(self, table, data):
        cols = self.columns(table)
        return {k: v for k, v in data.items() if k in cols}

    def insert(self, table, data):
        data = self._clean(table, data)
        keys = list(data.keys())
        sql = "INSERT INTO {} ({}) VALUES ({})".format(
            table, ", ".join(keys), ", ".join(["?"] * len(keys)))
        cur = self.conn.execute(sql, [data[k] for k in keys])
        self.conn.commit()
        return cur.lastrowid

    def update(self, table, row_id, data):
        data = self._clean(table, data)
        if not data:
            return
        keys = list(data.keys())
        sql = "UPDATE {} SET {} WHERE id=?".format(
            table, ", ".join("{}=?".format(k) for k in keys))
        self.conn.execute(sql, [data[k] for k in keys] + [row_id])
        self.conn.commit()

    def delete(self, table, row_id):
        self.conn.execute("DELETE FROM {} WHERE id=?".format(table), (row_id,))
        self.conn.commit()

    # --------------------------------------------------------------- settings
    def get_setting(self, key, default=""):
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else default

    def set_setting(self, key, value):
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
        self.conn.commit()

    def all_settings(self):
        d = {r["key"]: r["value"] for r in self.rows("SELECT * FROM settings")}
        return d

    # ------------------------------------------------------------------- seed
    def seed(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.insert("users", {
            "username": "admin", "password": hash_password("admin"),
            "full_name": "مدیر سیستم", "role": "admin", "active": 1,
            "created_at": now, "created_by": "نصب اولیه"})
        for code, name, atype in DEFAULT_ACCOUNTS:
            self.conn.execute(
                "INSERT OR IGNORE INTO accounts(code,name,atype) VALUES(?,?,?)",
                (code, name, atype))
        for u in DEFAULT_UNITS:
            self.conn.execute("INSERT OR IGNORE INTO units(name) VALUES(?)", (u,))
        for g in DEFAULT_GROUPS:
            self.conn.execute("INSERT OR IGNORE INTO product_groups(name) VALUES(?)", (g,))
        self.conn.execute(
            "INSERT INTO warehouses(name, location, is_default) VALUES(?,?,1)",
            ("انبار مرکزی", "انبار اصلی"))
        self.conn.execute(
            "INSERT INTO warehouses(name, location, is_default) VALUES(?,?,0)",
            ("انبار ضایعات", "باتری‌های فرسوده"))
        defaults = {
            "installed": "1",
            "company_name": "فروشگاه باتری",
            "company_phone": "",
            "company_address": "",
            "company_economic_code": "",
            "company_national_id": "",
            "currency": "ریال",
            "tax_rate": "9",
            "tax_enabled": "1",
            "fiscal_year_start": jdate.fmt(jdate.jalali_year(jdate.today_str()), 1, 1),
            "scrap_warehouse_id": "2",
            # پشتیبان‌گیری: پوشه، خودکار بودن و تعداد نسخه‌های نگه‌داشته‌شده
            "backup_dir": "",
            "backup_auto": "1",
            "backup_keep": "20",
            # لایسنس آنلاین (سرور لایسنس + بات بله)
            "license_server": "",
            "license_client_token": "",
            "license_check_hours": "6",
            "license_grace_days": "",
            "license_insecure": "",
        }
        for k, v in defaults.items():
            self.set_setting(k, v)
        self.conn.commit()

    # ------------------------------------------------------------------ stock
    def stock_of(self, product_id, warehouse_id=None):
        if warehouse_id:
            return self.scalar(
                "SELECT COALESCE(SUM(qty_in-qty_out),0) FROM stock_moves "
                "WHERE product_id=? AND warehouse_id=?", (product_id, warehouse_id), 0)
        return self.scalar(
            "SELECT COALESCE(SUM(qty_in-qty_out),0) FROM stock_moves WHERE product_id=?",
            (product_id,), 0)

    # ----------------------------------------------------------------- کاربران
    def active_user_count(self):
        return self.scalar("SELECT COUNT(*) FROM users WHERE active=1", (), 0)

    def user_by_name(self, username):
        return self.one("SELECT * FROM users WHERE username=?", (username,))

    def log_license_event(self, action, detail=""):
        self.insert("license_events", {
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action, "detail": detail})

    def scrap_stock(self):
        """موجودی انبار ضایعات: خریدها منهای مقداری که فروخته و خارج شده است."""
        r = self.one(
            "SELECT COALESCE(SUM(qty),0) AS qty, "
            "COALESCE(SUM(weight_kg),0) AS weight, "
            "COALESCE(SUM(out_qty),0) AS out_qty, "
            "COALESCE(SUM(out_weight),0) AS out_weight, "
            "COALESCE(SUM(amount),0) AS amount, "
            "COALESCE(SUM(amount*out_weight/NULLIF(weight_kg,0)),0) AS out_value "
            "FROM scrap_batteries")
        return {
            "qty": money(r["qty"] - r["out_qty"]) if r else 0,
            "weight": money(r["weight"] - r["out_weight"]) if r else 0,
            "value": money(r["amount"] - r["out_value"]) if r else 0,
        }
