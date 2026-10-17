"""انبار دادهٔ سرور لایسنس (SQLite).

همهٔ جدول‌ها اینجا ساخته می‌شوند و هیچ‌گاه دادهٔ حساس (کلید خصوصی، توکن) در
آن‌ها ذخیره نمی‌شود؛ فقط لایسنس‌های امضاشده و رخدادها.

نکتهٔ هم‌روندی: سرور Flask چندریسمانی است و نخِ بات هم در همان پروسه کار
می‌کند؛ بنابراین برای هر عملیات یک اتصال کوتاه‌مدت ساخته می‌شود (WAL) و
هیچ اتصال مشترکی بین نخ‌ها رد و بدل نمی‌شود.
"""
import json
import os
import sqlite3
import time
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    note TEXT DEFAULT '',
    max_devices INTEGER DEFAULT 1,
    chat_id INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    fingerprint TEXT UNIQUE NOT NULL,
    machine_code TEXT DEFAULT '',
    label TEXT DEFAULT '',
    chat_id INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',      -- pending|active|denied|revoked
    license_id INTEGER DEFAULT 0,
    requested_at TEXT DEFAULT '',
    activated_at TEXT DEFAULT '',
    last_seen TEXT DEFAULT '',
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER,
    fingerprint TEXT DEFAULT '',
    machine_code TEXT DEFAULT '',
    customer_id INTEGER,
    name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    note TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',      -- pending|approved|denied
    created_at TEXT,
    decided_at TEXT DEFAULT '',
    decided_by INTEGER DEFAULT 0,
    license_id INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lic_id TEXT,
    customer_id INTEGER,
    device_id INTEGER,
    fingerprint TEXT DEFAULT '',
    edition TEXT DEFAULT 'premium',
    features TEXT DEFAULT '',           -- JSON
    seats INTEGER DEFAULT 1,
    months INTEGER DEFAULT 12,
    issued TEXT DEFAULT '',
    expires TEXT DEFAULT '',
    key_text TEXT DEFAULT '',
    revoked INTEGER DEFAULT 0,
    revoked_at TEXT DEFAULT '',
    revoked_by INTEGER DEFAULT 0,
    note TEXT DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT, actor INTEGER, action TEXT, detail TEXT
);

CREATE TABLE IF NOT EXISTS states (
    chat_id INTEGER PRIMARY KEY,
    step TEXT DEFAULT '',
    payload TEXT DEFAULT '',
    updated_at REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS leases (
    name TEXT PRIMARY KEY,
    owner TEXT DEFAULT '',
    expires REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT DEFAULT '',
    at REAL DEFAULT 0
);
"""

# ستون‌هایی که بعد از نسخهٔ نخست اضافه شده‌اند؛ برای پایگاه‌دادهٔ موجود
# خودکار اضافه می‌شوند تا نصب‌های قدیمی هم بدون کار دستی کار کنند.
MIGRATIONS = (
    ("licenses", "days", "INTEGER DEFAULT 0"),
    ("requests", "decided_via", "TEXT DEFAULT ''"),
    ("requests", "decided_note", "TEXT DEFAULT ''"),
)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Store:
    def __init__(self, path):
        self.path = path
        folder = os.path.dirname(os.path.abspath(path))
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.init()

    # --------------------------------------------------------------- ابزارها
    def conn(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error:
            pass
        return c

    def init(self):
        c = self.conn()
        try:
            c.executescript(SCHEMA)
            c.commit()
        finally:
            c.close()
        self._migrate()

    def _migrate(self):
        """افزودن ستون‌های تازه به پایگاه‌داده‌های موجود.

        بی‌خطر و تکرارشدنی است: هر ستون یک بار بررسی و در صورت نبودن اضافه
        می‌شود؛ داده‌های موجود دست‌نخورده می‌مانند. نام جدول/ستون از ثابت‌های
        همین ماژول می‌آید (ورودی کاربر نیست).
        """
        for table, column, ddl in MIGRATIONS:
            c = self.conn()
            try:
                cols = [r["name"] for r in
                        c.execute("PRAGMA table_info({})".format(table))]
                if column not in cols:
                    c.execute("ALTER TABLE {} ADD COLUMN {} {}".format(
                        table, column, ddl))
                    c.commit()
            except sqlite3.Error:
                pass
            finally:
                c.close()

    def _all(self, sql, params=()):
        c = self.conn()
        try:
            return [dict(r) for r in c.execute(sql, params).fetchall()]
        finally:
            c.close()

    def _one(self, sql, params=()):
        rows = self._all(sql, params)
        return rows[0] if rows else None

    def _exec(self, sql, params=()):
        c = self.conn()
        try:
            cur = c.execute(sql, params)
            c.commit()
            return cur.lastrowid
        finally:
            c.close()

    def scalar(self, sql, params=(), default=0):
        row = self._one(sql, params)
        if not row:
            return default
        val = list(row.values())[0]
        return default if val is None else val

    # --------------------------------------------------------------- مشتریان
    def customer_add(self, name, phone="", note="", max_devices=1, chat_id=0):
        return self._exec(
            "INSERT INTO customers(name, phone, note, max_devices, chat_id, "
            "active, created_at) VALUES(?,?,?,?,?,1,?)",
            (name, phone, note, int(max_devices), int(chat_id or 0), now()))

    def customer_get(self, cid):
        return self._one("SELECT * FROM customers WHERE id=?", (cid,))

    def customer_update(self, cid, **fields):
        allowed = ("name", "phone", "note", "max_devices", "chat_id", "active")
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return
        keys = list(data)
        sql = "UPDATE customers SET {} WHERE id=?".format(
            ", ".join("{}=?".format(k) for k in keys))
        self._exec(sql, [data[k] for k in keys] + [cid])

    def customer_find(self, name="", phone=""):
        """جست‌وجوی مشتری با نام یا تلفن (برای جلوگیری از رکورد تکراری)."""
        if phone and name:
            row = self._one("SELECT * FROM customers WHERE phone=? AND name=?",
                            (phone, name))
            if row:
                return row
        if phone:
            row = self._one("SELECT * FROM customers WHERE phone=?", (phone,))
            if row:
                return row
        if name:
            return self._one("SELECT * FROM customers WHERE name=?", (name,))
        return None

    def customers(self, limit=200):
        return self._all("SELECT * FROM customers ORDER BY id DESC LIMIT ?", (limit,))

    # ---------------------------------------------------------------- دستگاه‌ها
    def device_by_fingerprint(self, fp):
        return self._one("SELECT * FROM devices WHERE fingerprint=?", (fp,))

    def device_lookup_any(self, code):
        """یافتن دستگاه با اثر انگشت کامل یا کد کوتاه ۲۰ نویسه‌ای.

        مشتری ممکن است فقط کد کوتاه را از روی صفحهٔ برنامه بخواند؛ در آن حالت
        اثر انگشت کامل ذخیره‌شده با کد کوتاه تطبیق داده می‌شود (لایهٔ حفاظتی
        یکسان است: ۸۰ بیت نخست اثر انگشت).
        """
        code = (code or "").strip().lower()
        if not code:
            return None
        device = self.device_by_fingerprint(code)
        if device:
            return device
        return self._one(
            "SELECT * FROM devices WHERE fingerprint LIKE ? "
            "OR ? LIKE fingerprint || '%' ORDER BY id LIMIT 1",
            (code + "%", code))

    def devices(self, limit=100):
        return self._all("SELECT * FROM devices ORDER BY id DESC LIMIT ?", (limit,))

    def device_get(self, did):
        return self._one("SELECT * FROM devices WHERE id=?", (did,))

    def device_add(self, fingerprint, machine_code, customer_id=None, label="",
                   chat_id=0, status="pending", note=""):
        return self._exec(
            "INSERT INTO devices(customer_id, fingerprint, machine_code, label, "
            "chat_id, status, requested_at, note) VALUES(?,?,?,?,?,?,?,?)",
            (customer_id, fingerprint, machine_code, label, int(chat_id or 0),
             status, now(), note))

    def device_update(self, did, **fields):
        allowed = ("customer_id", "machine_code", "label", "chat_id", "status",
                   "license_id", "requested_at", "activated_at", "last_seen", "note")
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return
        keys = list(data)
        sql = "UPDATE devices SET {} WHERE id=?".format(
            ", ".join("{}=?".format(k) for k in keys))
        self._exec(sql, [data[k] for k in keys] + [did])

    def devices_of(self, customer_id):
        return self._all("SELECT * FROM devices WHERE customer_id=? ORDER BY id",
                         (customer_id,))

    def devices_by_chat(self, chat_id):
        return self._all("SELECT * FROM devices WHERE chat_id=? ORDER BY id",
                         (int(chat_id),))

    def device_set_status(self, did, status):
        fields = {"status": status}
        if status == "active":
            fields["activated_at"] = now()
        self.device_update(did, **fields)

    def active_devices_of(self, customer_id):
        return self._all("SELECT * FROM devices WHERE customer_id=? AND "
                         "status='active'", (customer_id,))

    # --------------------------------------------------------------- درخواست‌ها
    def request_add(self, device_id, fingerprint, machine_code, customer_id,
                    name, phone, note=""):
        """درخواست تازه؛ اگر درخواست در انتظار برای همین دستگاه هست، همان برمی‌گردد."""
        pending = self._one("SELECT * FROM requests WHERE fingerprint=? AND "
                            "status='pending' ORDER BY id DESC LIMIT 1", (fingerprint,))
        if pending:
            self._exec("UPDATE requests SET name=?, phone=?, note=? WHERE id=?",
                       (name or pending["name"], phone or pending["phone"],
                        note or pending["note"], pending["id"]))
            return self._one("SELECT * FROM requests WHERE id=?", (pending["id"],))
        rid = self._exec(
            "INSERT INTO requests(device_id, fingerprint, machine_code, "
            "customer_id, name, phone, note, status, created_at) "
            "VALUES(?,?,?,?,?,?,?, 'pending', ?)",
            (device_id, fingerprint, machine_code, customer_id, name, phone, note, now()))
        return self._one("SELECT * FROM requests WHERE id=?", (rid,))

    def request_get(self, rid):
        return self._one("SELECT * FROM requests WHERE id=?", (rid,))

    def requests_pending(self, limit=20):
        return self._all("SELECT * FROM requests WHERE status='pending' "
                         "ORDER BY id LIMIT ?", (limit,))

    def requests_of(self, fingerprint, limit=5):
        return self._all("SELECT * FROM requests WHERE fingerprint=? "
                         "ORDER BY id DESC LIMIT ?", (fingerprint, limit))

    def request_decide(self, rid, status, decided_by=0, license_id=0, via="",
                       note=""):
        """ثبت نتیجهٔ بررسی درخواست. `via` می‌گوید از بات بوده یا از برنامه."""
        self._exec("UPDATE requests SET status=?, decided_at=?, decided_by=?, "
                   "license_id=?, decided_via=?, decided_note=? WHERE id=?",
                   (status, now(), int(decided_by or 0), int(license_id or 0),
                    str(via or ""), str(note or "")[:200], rid))

    # ---------------------------------------------------------------- لایسنس‌ها
    def license_add(self, **fields):
        cols = ("lic_id", "customer_id", "device_id", "fingerprint", "edition",
                "features", "seats", "months", "days", "issued", "expires",
                "key_text", "note")
        data = {k: fields.get(k) for k in cols}
        data["created_at"] = now()
        keys = list(data)
        sql = "INSERT INTO licenses({}) VALUES({})".format(
            ", ".join(keys), ", ".join(["?"] * len(keys)))
        return self._exec(sql, [data[k] for k in keys])

    def license_get(self, lid):
        return self._one("SELECT * FROM licenses WHERE id=?", (lid,))

    def license_by_lic_id(self, lic_id):
        return self._one("SELECT * FROM licenses WHERE lic_id=?", (lic_id,))

    def licenses(self, limit=200):
        return self._all("SELECT * FROM licenses ORDER BY id DESC LIMIT ?", (limit,))

    def licenses_of_customer(self, customer_id):
        return self._all("SELECT * FROM licenses WHERE customer_id=? ORDER BY id "
                         "DESC", (customer_id,))

    def licenses_of_fingerprint(self, fingerprint):
        return self._all("SELECT * FROM licenses WHERE fingerprint=? ORDER BY id "
                         "DESC", (fingerprint,))

    def license_revoke(self, lid, by=0):
        self._exec("UPDATE licenses SET revoked=1, revoked_at=?, revoked_by=? "
                   "WHERE id=?", (now(), int(by or 0), lid))

    def license_count(self):
        return self.scalar("SELECT COUNT(*) AS n FROM licenses")

    # ---------------------------------------------------------------- رخدادها
    def audit(self, actor, action, detail=""):
        self._exec("INSERT INTO audit(at, actor, action, detail) VALUES(?,?,?,?)",
                   (now(), int(actor or 0) if str(actor).lstrip("-").isdigit() else 0,
                    action, detail))

    def audits(self, limit=50):
        return self._all("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))

    # ------------------------------------------------------- وضعیت گفت‌وگوی بات
    def state_get(self, chat_id):
        return self._one("SELECT * FROM states WHERE chat_id=?", (int(chat_id),))

    def state_set(self, chat_id, step, payload=None):
        self._exec(
            "INSERT INTO states(chat_id, step, payload, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET step=excluded.step, "
            "payload=excluded.payload, updated_at=excluded.updated_at",
            (int(chat_id), step, json.dumps(payload or {}, ensure_ascii=False),
             time.time()))

    def state_clear(self, chat_id):
        self._exec("DELETE FROM states WHERE chat_id=?", (int(chat_id),))

    # ------------------------------------------------------- قفل نخِ نظرسنجی
    def lease_acquire(self, name, owner, ttl=45):
        """قفل زمان‌دار؛ برای اینکه فقط یک پروسه نظرسنجی بات را انجام دهد."""
        now_t = time.time()
        row = self._one("SELECT * FROM leases WHERE name=?", (name,))
        if row and row["owner"] != owner and row["expires"] > now_t:
            return False
        self._exec(
            "INSERT INTO leases(name, owner, expires) VALUES(?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET owner=excluded.owner, "
            "expires=excluded.expires", (name, owner, now_t + ttl))
        return True

    def lease_release(self, name, owner):
        self._exec("DELETE FROM leases WHERE name=? AND owner=?", (name, owner))

    # ---------------------------------------------------- محدودیت نرخ درخواست
    def rate_allow(self, ip, limit, window=3600):
        now_t = time.time()
        self._exec("DELETE FROM hits WHERE at<?", (now_t - window,))
        count = self.scalar("SELECT COUNT(*) AS n FROM hits WHERE ip=? AND at>=?",
                            (ip, now_t - window))
        if count >= limit:
            return False
        self._exec("INSERT INTO hits(ip, at) VALUES(?,?)", (ip, now_t))
        return True

    # ----------------------------------------------------------------- آمار
    def stats(self):
        return {
            "customers": self.scalar("SELECT COUNT(*) AS n FROM customers"),
            "devices_active": self.scalar(
                "SELECT COUNT(*) AS n FROM devices WHERE status='active'"),
            "devices_pending": self.scalar(
                "SELECT COUNT(*) AS n FROM devices WHERE status='pending'"),
            "licenses": self.license_count(),
            "licenses_revoked": self.scalar(
                "SELECT COUNT(*) AS n FROM licenses WHERE revoked=1"),
            "requests_pending": self.scalar(
                "SELECT COUNT(*) AS n FROM requests WHERE status='pending'"),
        }
