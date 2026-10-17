"""منطق بات بله: تأیید درخواست فعال‌سازی، صدور و لغو لایسنس.

جریان کار:
    ۱) مشتری در برنامه روی «درخواست فعال‌سازی» می‌زند؛ برنامه کد دستگاه را
       به سرور می‌فرستد و سرور به همهٔ مدیران پیام با دکمهٔ «تأیید» می‌دهد.
    ۲) مدیر نسخه/مدت/تعداد کاربر را با دکمه‌ها انتخاب می‌کند و لایسنس صادر
       می‌شود (امضای Ed25519 با کلید خصوصی ریشه).
    ۳) برنامهٔ مشتری همان لایسنس را خودکار دریافت و فعال می‌کند.

هیچ کاربری به‌جز شناسه‌های داخل ADMIN_CHAT_IDS نمی‌تواند لایسنس صادر یا لغو
کند. مشتری می‌تواند درخواست بدهد و وضعیت خودش را ببیند.
"""
import json
import traceback
from datetime import datetime

from bale import BaleError, keyboard
from sabalic import jdate, licensing

HELP_ADMIN = """راهنمای مدیر (صادرکنندهٔ لایسنس):

/inbox — درخواست‌های در انتظار تأیید
/req <شماره> — جزئیات یک درخواست
/customers — فهرست مشتریان
/customer <شماره> — جزئیات مشتری و دستگاه‌هایش
/devices — دستگاه‌های ثبت‌شده
/licenses — لایسنس‌های صادرشده
/revoke <شناسهٔ لایسنس> — لغو لایسنس (برنامهٔ مشتری در نخستین بررسی قفل می‌شود)
/add نام | تلفن — افزودن مشتری دستی
/limit <شمارهٔ مشتری> <تعداد> — سقف دستگاه‌های مجاز مشتری
/msg <شمارهٔ مشتری> متن — پیام به مشتری
/stats — آمار سرور
/server — وضعیت سرور و تنظیمات
/whoami — شناسهٔ گفت‌وگوی شما
/cmd — به‌روزرسانی فهرست دستورها در بات"""

HELP_USER = """سلام! برای فعال‌سازی سیستم حسابداری Mental:

۱) برنامه را باز کنید؛ کد رایانه (مثل DE50-D8C7-814F-60F7-BFD1) را در صفحهٔ
   فعال‌سازی می‌بینید.
۲) همان کد را اینجا بفرستید یا دستور /activate را بزنید.
۳) پس از تأیید فروشنده، برنامه خودش فعال می‌شود.

دستورها:
/activate — ثبت درخواست فعال‌سازی
/status — وضعیت درخواست و لایسنس شما
/key — دریافت دوبارهٔ متن لایسنس
/help — همین راهنما

پشتیبانی: برنامه را ببندید و باز کنید و اگر فعال نشد، همین‌جا پیام بگذارید."""

EDITIONS = (("premium", "پرمیوم"), ("base", "پایه"))
MONTHS_CHOICES = (1, 3, 6, 12, 24, 36, 0)
DAYS_CHOICES = (30, 90, 180, 365, 0)
SEAT_CHOICES = (1, 2, 3, 5, 10, 100)


def months_label(months):
    return "بدون انقضا" if not months else "{} ماه".format(months)


def days_label(days):
    return "بدون انقضا" if not days else "{} روز".format(days)


def duration_label(row):
    """مدت اعتبار یک ردیف لایسنس/درخواست: روز اگر داشته باشد، وگرنه ماه."""
    row = row or {}
    days = int(row.get("days") or 0)
    if days:
        return days_label(days)
    return months_label(int(row.get("months") or 0))


def edition_label(edition):
    return dict(EDITIONS).get(edition, edition)


def looks_like_code(text):
    norm = licensing.normalize_machine(text)
    return norm.isalnum() and len(norm) in (20, 64)


class Bot:
    def __init__(self, api, store, cfg, log=print):
        self.api = api
        self.store = store
        self.cfg = cfg
        self.log = log

    # ------------------------------------------------------------- ابزارها
    def _send(self, chat_id, text, markup=None):
        try:
            return self.api.send_message(chat_id, text, reply_markup=markup)
        except BaleError as exc:
            self.log("[send] {} → {}".format(chat_id, exc))
            return None

    def _edit(self, chat_id, message_id, text, markup=None):
        try:
            self.api.edit_message_text(chat_id, message_id, text, reply_markup=markup)
        except BaleError as exc:
            self.log("[edit] {}: {}".format(message_id, exc))

    def _answer(self, cb_id, text="", show_alert=False):
        try:
            self.api.answer_callback_query(cb_id, text, show_alert=show_alert)
        except BaleError as exc:
            # دکمه‌های قدیمی (بیش از چند دقیقه) دیگر قابل پاسخ نیستند؛
            # این خطا طبیعی است و نباید گزارش را پر کند.
            desc = (exc.description or "").lower()
            if "too old" in desc or "invalid" in desc:
                return
            self.log("[cb] {}".format(exc))

    def _notify_admins(self, text, markup=None):
        for admin in sorted(self.cfg.admin_ids):
            self._send(admin, text, markup)

    def _customer_chat(self, row):
        """شناسهٔ گفت‌وگوی مشتری (از دستگاه‌ها یا خود مشتری)."""
        if not row:
            return 0
        if row.get("chat_id"):
            return int(row["chat_id"])
        return 0

    # ------------------------------------------------------------- ورودی‌ها
    def handle(self, update):
        try:
            if "message" in update:
                self.on_message(update["message"])
            elif "callback_query" in update:
                self.on_callback(update["callback_query"])
        except Exception:                       # noqa: BLE001 - بات نباید بیفتد
            self.log("[handle] " + traceback.format_exc())

    def on_message(self, msg):
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        text = (msg.get("text") or "").strip()
        if chat_id is None or not text:
            return
        if text.startswith("/"):
            cmd, _, args = text.partition(" ")
            cmd = cmd.split("@")[0].lstrip("/").lower()
            self.on_command(int(chat_id), cmd, args.strip(), msg)
            return
        if looks_like_code(text):
            self.start_activation(int(chat_id), text)
            return
        state = self.store.state_get(chat_id)
        if state and state.get("step"):
            self.on_state(int(chat_id), state, text)
            return
        self._send(int(chat_id), HELP_USER)

    # ------------------------------------------------------------- دستورها
    def on_command(self, chat_id, cmd, args, msg):
        admin = self.cfg.is_admin(chat_id)
        user_cmds = {
            "start": lambda: self._send(chat_id, HELP_USER),
            "help": lambda: self._send(chat_id, HELP_ADMIN if admin else HELP_USER),
            "whoami": lambda: self._send(
                chat_id, "شناسهٔ گفت‌وگوی شما: {}\nنقش: {}".format(
                    chat_id, "مدیر (صادرکننده)" if admin else "کاربر")),
            "status": lambda: self.cmd_status(chat_id),
            "activate": lambda: self.start_activation(chat_id, args),
            "key": lambda: self.cmd_key(chat_id),
        }
        if cmd in user_cmds:
            user_cmds[cmd]()
            return
        if not admin:
            self._send(chat_id, "این دستور فقط برای مدیر سیستم است.\n\n" + HELP_USER)
            return
        handlers = {
            "inbox": lambda: self.cmd_inbox(chat_id),
            "pending": lambda: self.cmd_inbox(chat_id),
            "req": lambda: self.cmd_req(chat_id, args),
            "customers": lambda: self.cmd_customers(chat_id),
            "customer": lambda: self.cmd_customer(chat_id, args),
            "devices": lambda: self.cmd_devices(chat_id),
            "licenses": lambda: self.cmd_licenses(chat_id),
            "revoke": lambda: self.cmd_revoke(chat_id, args),
            "add": lambda: self.cmd_add(chat_id, args),
            "limit": lambda: self.cmd_limit(chat_id, args),
            "msg": lambda: self.cmd_msg(chat_id, args),
            "stats": lambda: self.cmd_stats(chat_id),
            "server": lambda: self.cmd_server(chat_id),
            "cmd": lambda: self.cmd_setcommands(chat_id),
        }
        fn = handlers.get(cmd)
        if fn is None:
            self._send(chat_id, "دستور ناشناخته.\n\n" + HELP_ADMIN)
            return
        fn()

    # ------------------------------------------------------ جریان فعال‌سازی
    def start_activation(self, chat_id, code_text):
        """شروع یا ادامهٔ درخواست فعال‌سازی برای یک کد دستگاه."""
        code_text = (code_text or "").strip()
        if not code_text:
            self.store.state_set(chat_id, "wait_code", {})
            self._send(chat_id, "کد رایانه را بفرستید (مثل "
                                "DE50-D8C7-814F-60F7-BFD1).\nاین کد در صفحهٔ "
                                "فعال‌سازی برنامه نمایش داده می‌شود.")
            return
        if not looks_like_code(code_text):
            self._send(chat_id, "این متن کد رایانه به نظر نمی‌رسد. کد ۲۰ نویسه‌ای "
                                "شامل حرف و رقم است (مثل DE50-D8C7-814F-60F7-BFD1).")
            return
        normalized = licensing.normalize_machine(code_text)
        device = self._device_lookup(normalized)
        if device and device.get("status") == "active" and device.get("license_id"):
            lic = self.store.license_get(device["license_id"])
            if lic and not lic.get("revoked"):
                self.store.device_update(device["id"], chat_id=chat_id)
                self._send(chat_id, "این رایانه از قبل فعال است. لایسنس:\n" +
                           (lic.get("lic_id") or ""))
                self.send_key(chat_id, lic)
                return
        if device and device.get("customer_id"):
            customer = self.store.customer_get(device["customer_id"]) or {}
            self.store.device_update(device["id"], chat_id=chat_id)
            self.create_request(device, customer)
            return
        self.store.state_set(chat_id, "wait_name",
                             {"code": normalized, "machine_code": normalized.upper()})
        self._send(chat_id, "کد دریافت شد.\nنام مشتری (نام فروشگاه) را بفرستید:")

    def on_state(self, chat_id, state, text):
        step = state.get("step")
        try:
            data = json.loads(state.get("payload") or "{}")
        except ValueError:
            data = {}
        if step == "wait_code":
            self.store.state_clear(chat_id)
            self.start_activation(chat_id, text)
            return
        if step == "wait_name":
            data["name"] = text.strip()[:80]
            self.store.state_set(chat_id, "wait_phone", data)
            self._send(chat_id, "شمارهٔ تماس را بفرستید (یا خط تیره «-» بگذارید):")
            return
        if step == "wait_phone":
            data["phone"] = "" if text.strip() in ("-", "—") else text.strip()[:30]
            self.store.state_clear(chat_id)
            self.finish_request(chat_id, data)
            return
        self.store.state_clear(chat_id)
        self._send(chat_id, HELP_USER)

    def finish_request(self, chat_id, data):
        code = data.get("code") or ""
        name = data.get("name") or "بدون نام"
        phone = data.get("phone") or ""
        customer = self.store.customer_find(name=name, phone=phone)
        if not customer:
            cid = self.store.customer_add(name, phone, note="ثبت از بات بله",
                                           max_devices=1, chat_id=chat_id)
            customer = self.store.customer_get(cid)
        else:
            self.store.customer_update(customer["id"], chat_id=chat_id)
        device = self._device_lookup(code)
        if not device:
            did = self.store.device_add(code, code.upper(), customer["id"],
                                        label="", chat_id=chat_id)
            device = self.store.device_get(did)
        else:
            self.store.device_update(device["id"], customer_id=customer["id"],
                                     chat_id=chat_id)
        self.create_request(device, customer)

    def _device_lookup(self, normalized):
        """جست‌وجوی دستگاه با اثر انگشت کامل یا کد کوتاه‌شده."""
        return self.store.device_lookup_any(normalized)

    def create_request(self, device, customer):
        req = self.store.request_add(
            device["id"], device["fingerprint"], device.get("machine_code") or
            device["fingerprint"].upper(), customer.get("id"),
            customer.get("name") or "", customer.get("phone") or "")
        self.store.audit(customer.get("chat_id"), "request",
                         "درخواست فعال‌سازی #{}".format(req["id"]))
        self._send(customer.get("chat_id") or device.get("chat_id") or 0,
                   "✅ درخواست فعال‌سازی شما ثبت شد (شمارهٔ {}).\n"
                   "پس از تأیید فروشنده، برنامه خودکار فعال می‌شود و همین‌جا هم "
                   "به شما خبر می‌دهیم.\nبا /status می‌توانید وضعیت را ببینید."
                   .format(req["id"]))
        text = ("🔔 درخواست فعال‌سازی #{}\n"
                "مشتری: {}\nتلفن: {}\nدستگاه: {}\nتاریخ: {}").format(
            req["id"], customer.get("name") or "—", customer.get("phone") or "—",
            req.get("machine_code") or device["fingerprint"][:20].upper(),
            req.get("created_at") or "")
        self._notify_admins(text, keyboard([[("✅ تأیید", "ap:{}".format(req["id"])),
                                             ("❌ رد", "dn:{}".format(req["id"]))]]))

    # ------------------------------------------------------- منوی تأیید مدیر
    def cmd_inbox(self, chat_id):
        rows = self.store.requests_pending(limit=10)
        if not rows:
            self._send(chat_id, "درخواست در انتظاری نیست. ✨")
            return
        for req in rows:
            device = self.store.device_get(req["device_id"]) or {}
            customer = self.store.customer_get(req["customer_id"]) or {}
            self._send(chat_id, self._req_text(req, device, customer),
                       keyboard([[("✅ تأیید", "ap:{}".format(req["id"])),
                                  ("❌ رد", "dn:{}".format(req["id"]))]]))

    @staticmethod
    def _req_text(req, device, customer):
        return ("🔔 درخواست #{}\nمشتری: {}\nتلفن: {}\nکد دستگاه: {}\n"
                "تاریخ: {}\n{}").format(
            req["id"], customer.get("name") or req.get("name") or "—",
            customer.get("phone") or req.get("phone") or "—",
            (req.get("machine_code") or device.get("machine_code") or "")[:29],
            req.get("created_at") or "",
            "توضیح: {}".format(req.get("note")) if req.get("note") else "")

    def cmd_req(self, chat_id, args):
        try:
            rid = int(args.split()[0])
        except (ValueError, IndexError):
            self._send(chat_id, "شمارهٔ درخواست را بدهید؛ مثال: /req 12")
            return
        req = self.store.request_get(rid)
        if not req:
            self._send(chat_id, "درخواستی با این شماره نیست.")
            return
        device = self.store.device_get(req["device_id"]) or {}
        customer = self.store.customer_get(req["customer_id"]) or {}
        self._send(chat_id, self._req_text(req, device, customer),
                   keyboard([[("✅ تأیید", "ap:{}".format(rid))]] if
                            req["status"] == "pending" else None))

    def plan_view(self, rid):
        req = self.store.request_get(rid)
        if not req:
            return "این درخواست پیدا نشد."
        device = self.store.device_get(req["device_id"]) or {}
        customer = self.store.customer_get(req["customer_id"]) or {}
        if req["status"] != "pending":
            return "این درخواست قبلاً بررسی شده است ({}).".format(req["status"])
        text = (self._req_text(req, device, customer) +
                "\n\nنسخهٔ لایسنس را انتخاب کنید:")
        markup = keyboard([
            [("💎 پرمیوم", "ape:{}:premium".format(rid)),
             ("🅱️ پایه", "ape:{}:base".format(rid))],
            [("❌ رد درخواست", "dn:{}".format(rid))],
        ])
        return text, markup

    def days_view(self, rid, edition):
        """گام مدت اعتبار: انتخاب با «روز» (نه ماه) — خواستهٔ فروشنده."""
        req = self.store.request_get(rid)
        if not req:
            return "این درخواست پیدا نشد."
        rows = [[(days_label(d), "apd:{}:{}:{}".format(rid, edition, d))
                 for d in DAYS_CHOICES[:3]]]
        rows.append([(days_label(d), "apd:{}:{}:{}".format(rid, edition, d))
                     for d in DAYS_CHOICES[3:]])
        rows.append([("↩️ بازگشت", "ap:{}".format(rid))])
        return ("درخواست #{} — نسخهٔ {}\nمدت اعتبار (روز) را انتخاب کنید:"
                .format(rid, edition_label(edition)), keyboard(rows))

    # نام قدیمی؛ برای سازگاری با فراخوانی‌های پیشین.
    months_view = days_view

    def seats_view(self, rid, edition, days, device_count=0):
        seats = self.cfg.default_seats if edition == "premium" else 1
        rows = [[(str(s) if s < 100 else "نامحدود", "aps:{}:{}:{}:{}".format(
            rid, edition, days, s)) for s in SEAT_CHOICES[:4]]]
        rows.append([(str(s) if s < 100 else "نامحدود", "aps:{}:{}:{}:{}".format(
            rid, edition, days, s)) for s in SEAT_CHOICES[4:]])
        rows.append([("↩️ بازگشت", "ape:{}:{}".format(rid, edition))])
        return ("درخواست #{} — {} / {}\nتعداد کاربران مجاز برنامه را انتخاب کنید "
                "(پیشنهاد: {}):".format(rid, edition_label(edition),
                                        days_label(days), seats),
                keyboard(rows))

    # ------------------------------------------------------------- صدور
    def issue_for_request(self, rid, edition, days, seats, admin_chat,
                          source="bot", admin_note=""):
        req = self.store.request_get(rid)
        if not req:
            return "درخواستی با این شماره نیست.", None
        if req["status"] != "pending":
            return "این درخواست قبلاً بررسی شده است ({}).".format(req["status"]), None
        device = self.store.device_get(req["device_id"]) or {}
        customer = self.store.customer_get(req["customer_id"]) or {}
        fingerprint = req.get("fingerprint") or device.get("fingerprint") or ""
        bound = fingerprint
        name = customer.get("name") or req.get("name") or "بدون نام"
        try:
            seats = int(seats)
        except (TypeError, ValueError):
            seats = self.cfg.default_seats
        days = int(days or 0)
        count = self.store.license_count() + 1
        lic_id = "SB-{}-{:04d}".format(
            jdate.today_str().replace("/", "")[:6], count)
        where = "برنامهٔ فروشنده" if source == "app" else "بات بله"
        note = "صادرشده از {}؛ درخواست #{}".format(where, rid)
        # `online: true` یعنی برنامهٔ مشتری باید دوره‌ای با سرور بررسی کند
        # (لغو از راه دور) و بعد از پایان مهلت بی‌اتصال قفل می‌شود.
        # مدت با «روز» تعیین می‌شود؛ صفر یعنی بدون انقضا.
        out = licensing.issue_license(
            self.cfg.private_key, customer=name, edition=edition,
            seats=seats, machine=bound, months=0, days=days or None,
            note=note, lic_id=lic_id, extra={"online": True})
        if not licensing.verify_signature(out["payload"], out["sig"],
                                         self.cfg.public_key):
            return "خطا: امضای لایسنس ساخته‌شده معتبر نیست؛ کلیدها بررسی شوند.", None
        payload = out["payload"]
        lic_row = self.store.license_add(
            lic_id=lic_id, customer_id=customer.get("id") or 0,
            device_id=device.get("id") or 0, fingerprint=bound, edition=edition,
            features=json.dumps(payload["features"], ensure_ascii=False),
            seats=payload["seats"], months=0, days=days,
            issued=payload["issued"], expires=payload["expires"],
            key_text=out["key"], note=note)
        self.store.device_set_status(device["id"], "active")
        self.store.device_update(device["id"], license_id=lic_row,
                                 activated_at=datetime.now().strftime(
                                     "%Y-%m-%d %H:%M:%S"))
        self.store.request_decide(rid, "approved", admin_chat, lic_row,
                                  via=source, note=admin_note)
        self.store.audit(admin_chat, "issue",
                         "{} برای {} ({})".format(lic_id, name, where))
        summary = ("✅ لایسنس صادر شد\n"
                   "شناسه: {}\nمشتری: {}\nنسخه: {}\nمدت: {}\nکاربران مجاز: {}\n"
                   "صدور: {}\nانقضا: {}\nدستگاه: {}").format(
            lic_id, name, edition_label(edition), days_label(days),
            payload["seats"], payload["issued"], payload["expires"] or "بدون انقضا",
            bound[:20].upper())
        chat = self._customer_chat(customer) or device.get("chat_id") or 0
        if chat:
            self._send(chat, "🎉 لایسنس شما صادر و تأیید شد!\n" + summary +
                       "\nبرنامه را باز کنید؛ خودکار فعال می‌شود. اگر باز بود یک‌بار "
                       "ببندید و باز کنید.")
            self.send_key(chat, {"key_text": out["key"], "lic_id": lic_id})
        return summary, {"license": lic_row, "key": out["key"],
                         "customer_chat": chat, "lic_id": lic_id,
                         "request_id": rid, "days": days,
                         "seats": payload["seats"], "edition": edition,
                         "expires": payload["expires"]}

    def send_key(self, chat_id, lic):
        key = (lic or {}).get("key_text") or ""
        if not key:
            return
        self._send(chat_id, "متن لایسنس (برای فعال‌سازی دستی در صفحهٔ فعال‌سازی):")
        self._send(chat_id, key)

    # --------------------------------------------------------------- دستورها
    def cmd_status(self, chat_id):
        devices = self.store.devices_by_chat(chat_id)
        if not devices:
            self._send(chat_id, "برای شما درخواستی ثبت نشده است. کد رایانه را "
                                "بفرستید یا /activate را بزنید.")
            return
        for device in devices:
            lic = self.store.license_get(device.get("license_id") or 0)
            if device["status"] == "active" and lic and not lic.get("revoked"):
                state = "✅ فعال"
            elif lic and lic.get("revoked"):
                state = "⛔ لغوشده"
            elif device["status"] == "pending":
                state = "⏳ در انتظار تأیید فروشنده"
            elif device["status"] == "denied":
                state = "❌ رد‌شده"
            else:
                state = "— " + str(device["status"])
            line = ("دستگاه {} ({})\nوضعیت: {}").format(
                device["id"], (device.get("machine_code") or "")[:20], state)
            if lic:
                line += "\nشناسهٔ لایسنس: {}\nنسخه: {}\nانقضا: {}".format(
                    lic["lic_id"], edition_label(lic["edition"]),
                    lic["expires"] or "بدون انقضا")
            self._send(chat_id, line)

    def cmd_key(self, chat_id):
        devices = self.store.devices_by_chat(chat_id)
        sent = False
        for device in devices:
            lic = self.store.license_get(device.get("license_id") or 0)
            if lic and not lic.get("revoked"):
                self.send_key(chat_id, lic)
                sent = True
        if not sent:
            self._send(chat_id, "لایسنسی برای شما ثبت نشده است. /status را بزنید.")

    def cmd_customers(self, chat_id):
        rows = self.store.customers(limit=40)
        if not rows:
            self._send(chat_id, "هنوز مشتری‌ای ثبت نشده است.")
            return
        lines = []
        for c in rows:
            n = len(self.store.active_devices_of(c["id"]))
            lines.append("#{} {} — {} | دستگاه فعال: {}/{}".format(
                c["id"], c["name"], c["phone"] or "—", n,
                c["max_devices"] if c["max_devices"] else "∞"))
        self._send(chat_id, "مشتریان:\n" + "\n".join(lines))

    def cmd_customer(self, chat_id, args):
        try:
            cid = int(args.split()[0])
        except (ValueError, IndexError):
            self._send(chat_id, "شمارهٔ مشتری را بدهید؛ مثال: /customer 3")
            return
        c = self.store.customer_get(cid)
        if not c:
            self._send(chat_id, "مشتری با این شماره نیست.")
            return
        lines = ["مشتری #{}".format(c["id"]), "نام: {}".format(c["name"]),
                 "تلفن: {}".format(c["phone"] or "—"),
                 "سقف دستگاه: {}".format(c["max_devices"] or "∞"),
                 "گفت‌وگو: {}".format(c["chat_id"] or "—")]
        for d in self.store.devices_of(cid):
            lic = self.store.license_get(d.get("license_id") or 0)
            lines.append("— دستگاه {} «{}» وضعیت {} | لایسنس {}".format(
                d["id"], (d.get("machine_code") or "")[:20], d["status"],
                (lic or {}).get("lic_id") or "—"))
        self._send(chat_id, "\n".join(lines))

    def cmd_devices(self, chat_id):
        rows = self.store.devices(limit=30)
        if not rows:
            self._send(chat_id, "دستگاهی ثبت نشده است.")
            return
        lines = ["#{} {} | مشتری {} | {}".format(
            d["id"], (d.get("machine_code") or d["fingerprint"][:20].upper()),
            d.get("customer_id") or "—", d["status"]) for d in rows]
        self._send(chat_id, "دستگاه‌ها:\n" + "\n".join(lines))

    def cmd_licenses(self, chat_id):
        rows = self.store.licenses(limit=25)
        if not rows:
            self._send(chat_id, "لایسنسی صادر نشده است.")
            return
        lines = []
        for lic in rows:
            lines.append("{} | {} | {} | {}→{} | {}".format(
                lic["lic_id"], lic["edition"], duration_label(lic),
                lic["issued"], lic["expires"] or "∞",
                "⛔ لغوشده" if lic["revoked"] else "فعال"))
        self._send(chat_id, "لایسنس‌ها:\n" + "\n".join(lines))

    def cmd_revoke(self, chat_id, args):
        lic_id = args.split()[0] if args.split() else ""
        if not lic_id:
            self._send(chat_id, "شناسهٔ لایسنس را بدهید؛ مثال: /revoke SB-140507-0003")
            return
        lic = self.store.license_by_lic_id(lic_id)
        if not lic:
            self._send(chat_id, "لایسنسی با این شناسه نیست.")
            return
        if lic["revoked"]:
            self._send(chat_id, "این لایسنس قبلاً لغو شده است.")
            return
        self._send(chat_id, "لایسنس {} برای مشتری #{} لغو شود؟\nبا لغو، برنامهٔ "
                            "مشتری در نخستین بررسی اینترنتی قفل می‌شود.".format(
                                lic_id, lic["customer_id"]),
                   keyboard([[("⛔ بله، لغو کن", "rv:{}".format(lic["id"])),
                              ("↩️ انصراف", "noop")]]))

    def do_revoke(self, lic_id_row, admin_chat):
        lic = self.store.license_get(lic_id_row)
        if not lic:
            return "لایسنس پیدا نشد."
        if lic["revoked"]:
            return "این لایسنس قبلاً لغو شده است."
        self.store.license_revoke(lic_id_row, admin_chat)
        self.store.audit(admin_chat, "revoke", lic["lic_id"])
        device = self.store.device_get(lic.get("device_id") or 0)
        if device:
            self.store.device_set_status(device["id"], "revoked")
        customer = self.store.customer_get(lic.get("customer_id") or 0) or {}
        chat = self._customer_chat(customer) or (device or {}).get("chat_id") or 0
        if chat:
            self._send(chat, "⚠️ لایسنس {} لغو شد. برای ادامهٔ استفاده با فروشنده "
                             "تماس بگیرید.".format(lic["lic_id"]))
        return "لایسنس {} لغو شد.".format(lic["lic_id"])

    def cmd_add(self, chat_id, args):
        if not args:
            self._send(chat_id, "قالب: /add نام مشتری | 09120000000")
            return
        name, _, phone = args.partition("|")
        name, phone = name.strip(), phone.strip()
        if not name:
            self._send(chat_id, "نام مشتری را وارد کنید.")
            return
        existing = self.store.customer_find(name=name, phone=phone)
        if existing:
            self._send(chat_id, "این مشتری از قبل هست: #{} {}".format(
                existing["id"], existing["name"]))
            return
        cid = self.store.customer_add(name, phone, note="ثبت دستی توسط مدیر")
        self.store.audit(chat_id, "add_customer", name)
        self._send(chat_id, "مشتری #{} «{}» ساخته شد.".format(cid, name))

    def cmd_limit(self, chat_id, args):
        parts = args.split()
        if len(parts) != 2:
            self._send(chat_id, "قالب: /limit 3 2")
            return
        try:
            cid, n = int(parts[0]), int(parts[1])
        except ValueError:
            self._send(chat_id, "هر دو مقدار باید عدد باشند.")
            return
        if not self.store.customer_get(cid):
            self._send(chat_id, "مشتری با این شماره نیست.")
            return
        self.store.customer_update(cid, max_devices=n)
        self.store.audit(chat_id, "limit", "customer {} → {}".format(cid, n))
        self._send(chat_id, "سقف دستگاه‌های مشتری #{} روی {} تنظیم شد.".format(
            cid, n or "بی‌نهایت"))

    def cmd_msg(self, chat_id, args):
        parts = args.split(None, 1)
        if len(parts) != 2:
            self._send(chat_id, "قالب: /msg 3 متن پیام")
            return
        try:
            cid = int(parts[0])
        except ValueError:
            self._send(chat_id, "شمارهٔ مشتری باید عدد باشد.")
            return
        customer = self.store.customer_get(cid)
        if not customer:
            self._send(chat_id, "مشتری با این شماره نیست.")
            return
        chat = self._customer_chat(customer)
        if not chat:
            for d in self.store.devices_of(cid):
                chat = chat or d.get("chat_id") or 0
        if not chat:
            self._send(chat_id, "این مشتری هنوز در بات گفت‌وگویی ندارد.")
            return
        self._send(chat, parts[1])
        self._send(chat_id, "پیام ارسال شد.")

    def cmd_stats(self, chat_id):
        s = self.store.stats()
        self._send(chat_id, "آمار سرور:\nمشتریان: {customers}\nدستگاه فعال: "
                            "{devices_active}\nدر انتظار: {devices_pending}\n"
                            "لایسنس: {licenses}\nلغوشده: {licenses_revoked}\n"
                            "درخواست باز: {requests_pending}".format(**s))

    def cmd_server(self, chat_id):
        c = self.cfg
        problems = c.missing()
        self._send(chat_id, "وضعیت سرور:\n"
                            "نشانی عمومی: {}\n"
                            "کلید خصوصی: {}\nکلید عمومی: {}\n"
                            "مدیران: {}\nمهلت بی‌اتصال (روز): {}\n"
                            "پیش‌فرض: {} / {} / {} کاربر\n"
                            "{}".format(
                                c.public_url or "—",
                                "✅" if c.private_key else "❌",
                                "✅" if c.public_key else "❌",
                                len(c.admin_ids), c.grace_days,
                                edition_label(c.default_edition),
                                days_label(c.default_days), c.default_seats,
                                "مشکلی نیست." if not problems
                                else "⚠️ " + "؛ ".join(problems)))

    def cmd_setcommands(self, chat_id):
        commands = [
            {"command": "inbox", "description": "درخواست‌های در انتظار تأیید"},
            {"command": "customers", "description": "فهرست مشتریان"},
            {"command": "licenses", "description": "لایسنس‌های صادرشده"},
            {"command": "revoke", "description": "لغو لایسنس"},
            {"command": "stats", "description": "آمار سرور"},
            {"command": "status", "description": "وضعیت درخواست من"},
            {"command": "activate", "description": "درخواست فعال‌سازی"},
            {"command": "help", "description": "راهنما"},
        ]
        try:
            self.api.set_my_commands(commands)
            self._send(chat_id, "فهرست دستورها در بات به‌روز شد.")
        except BaleError as exc:
            self._send(chat_id, "به‌روزرسانی دستورها ناموفق بود: {}".format(exc))

    # ------------------------------------------------------ فشار دکمه‌ها
    def on_callback(self, cb):
        data = (cb.get("data") or "").strip()
        cb_id = cb.get("id")
        msg = cb.get("message") or {}
        chat = (msg.get("chat") or {})
        chat_id = chat.get("id")
        message_id = msg.get("message_id")
        from_id = (cb.get("from") or {}).get("id")
        if chat_id is None or from_id is None:
            self._answer(cb_id, "درخواست نامعتبر")
            return
        if not self.cfg.is_admin(from_id):
            self._answer(cb_id, "فقط فروشنده می‌تواند لایسنس را تأیید کند")
            self._send(int(chat_id), "این دکمه فقط برای فروشنده کار می‌کند.")
            return
        parts = data.split(":")
        action = parts[0]
        try:
            if action == "noop":
                self._answer(cb_id, "")
                return
            if action == "ap":                       # انتخاب نسخه
                rid = int(parts[1])
                view = self.plan_view(rid)
                self._answer(cb_id, "")
                if isinstance(view, tuple):
                    self._edit(chat_id, message_id, view[0], view[1])
                else:
                    self._edit(chat_id, message_id, view)
                return
            if action == "ape":                      # انتخاب مدت (روز)
                rid, edition = int(parts[1]), parts[2]
                text, markup = self.days_view(rid, edition)
                self._answer(cb_id, "")
                self._edit(chat_id, message_id, text, markup)
                return
            # `apm` نام قدیمی همین گام است؛ برای دکمه‌های قدیمی نگه داشته شد.
            if action in ("apd", "apm"):               # انتخاب تعداد کاربر
                rid, edition, days = int(parts[1]), parts[2], int(parts[3])
                text, markup = self.seats_view(rid, edition, days)
                self._answer(cb_id, "")
                self._edit(chat_id, message_id, text, markup)
                return
            if action == "aps":                      # صدور نهایی
                rid, edition, days, seats = (int(parts[1]), parts[2],
                                             int(parts[3]), int(parts[4]))
                self._answer(cb_id, "در حال صدور…")
                summary, _info = self.issue_for_request(rid, edition, days,
                                                        seats, from_id)
                self._edit(chat_id, message_id, summary)
                return
            if action == "dn":                       # رد درخواست
                rid = int(parts[1])
                self._answer(cb_id, "رد شد")
                self.deny_request(rid, from_id, chat_id, message_id)
                return
            if action == "rv":                       # لغو لایسنس
                self._answer(cb_id, "لغو شد", show_alert=False)
                res = self.do_revoke(int(parts[1]), from_id)
                self._edit(chat_id, message_id, res)
                return
        except (IndexError, ValueError) as exc:
            self._answer(cb_id, "دادهٔ دکمه نامعتبر است")
            self.log("[cb] دادهٔ نامعتبر {!r}: {!r}".format(data, exc))
            return
        self._answer(cb_id, "این دکمه دیگر معتبر نیست")

    def deny_request(self, rid, admin_chat, chat_id, message_id):
        """رد درخواست از داخل بات؛ پیام همان درخواست ویرایش می‌شود."""
        _okay, text = self.deny(rid, admin_chat)
        self._edit(chat_id, message_id, text)

    def deny(self, rid, admin_chat=0, source="bot", admin_note=""):
        """هستهٔ رد درخواست (بات و برنامهٔ فروشنده از همین استفاده می‌کنند).

        خروجی: (انجام شد؟، متن نتیجه)
        """
        req = self.store.request_get(rid)
        if not req:
            return False, "درخواست پیدا نشد."
        if req["status"] != "pending":
            return False, "این درخواست قبلاً بررسی شده است."
        device = self.store.device_get(req["device_id"])
        self.store.request_decide(rid, "denied", admin_chat, via=source,
                                  note=admin_note)
        if device:
            self.store.device_set_status(device["id"], "denied")
        customer = self.store.customer_get(req["customer_id"]) or {}
        self.store.audit(admin_chat, "deny", "درخواست #{}".format(rid))
        chat = self._customer_chat(customer) or (device or {}).get("chat_id") or 0
        if chat:
            self._send(chat, "درخواست فعال‌سازی #{} تأیید نشد. برای اطلاعات بیشتر "
                             "با فروشنده تماس بگیرید.".format(rid))
        return True, "❌ درخواست #{} رد شد.".format(rid)
