"""کلاینت سبک API بات پیام‌رسان بله (سازگار با شکل API تلگرام).

مستندات بله: https://docs.bale.ai/ — نشانی فراخوانی‌ها:
    https://tapi.bale.ai/bot<TOKEN>/<METHOD>

تنها از کتابخانهٔ استاندارد استفاده می‌شود تا نصب روی سرور بدون وابستگی
اضافی انجام شود. لایهٔ انتقال (transport) قابل تزریق است تا در آزمون‌ها
بدون تماس واقعی با شبکه، رفتار بات بررسی شود.
"""
import json
import socket
import time
import urllib.error
import urllib.request


class BaleError(Exception):
    """خطای فراخوانی API بله."""

    def __init__(self, method, description, code=None, retry_after=None):
        super().__init__("{}: {}".format(method, description))
        self.method = method
        self.description = description
        self.code = code
        self.retry_after = retry_after


def urllib_transport(url, payload, timeout):
    """انتقال پیش‌فرض: POST با بدنهٔ JSON."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, socket.timeout, OSError, ValueError) as exc:
        # ValueError = نشانی نامعتبر (مثلاً BALE_API_BASE بدون http)
        raise BaleError("http", "ارتباط با سرور بله برقرار نشد: {!r}".format(exc))


def chunks(text, size=3500):
    """تقسیم متن بلند به تکه‌های مجاز (سقف بله ۴۰۹۶ نویسه است)."""
    text = text or ""
    if len(text) <= size:
        return [text]
    out = []
    while text:
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = size
        out.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return out


class Bale:
    def __init__(self, token, api_base="https://tapi.bale.ai", transport=None,
                 timeout=40):
        self.token = (token or "").strip()
        self.api_base = (api_base or "https://tapi.bale.ai").rstrip("/")
        self.transport = transport or urllib_transport
        self.timeout = timeout
        self.calls = 0

    @property
    def base_url(self):
        return "{}/bot{}".format(self.api_base, self.token)

    # ------------------------------------------------------------- فراخوانی
    def call(self, method, params=None, timeout=None):
        if not self.token:
            raise BaleError(method, "توکن بات تنظیم نشده است")
        url = "{}/{}".format(self.base_url, method)
        self.calls += 1
        code, raw = self.transport(url, params or {}, timeout or self.timeout)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise BaleError(method, "پاسخ نامعتبر از سرور بله (کد {})".format(code))
        if not isinstance(data, dict):
            raise BaleError(method, "ساختار پاسخ بله درست نیست")
        if not data.get("ok"):
            desc = str(data.get("description") or data.get("error") or "خطای نامشخص")
            retry = None
            params_out = data.get("parameters")
            if isinstance(params_out, dict):
                retry = params_out.get("retry_after")
            raise BaleError(method, desc, code=data.get("error_code") or code,
                            retry_after=retry)
        return data.get("result")

    # -------------------------------------------------------------- متدها
    def get_me(self):
        return self.call("getMe")

    def get_updates(self, offset=None, timeout=None, limit=20):
        params = {"limit": limit, "timeout": timeout or 0}
        if offset:
            params["offset"] = offset
        return self.call("getUpdates", params,
                         timeout=(timeout or 0) + 15) or []

    def send_message(self, chat_id, text, reply_markup=None):
        out = []
        for part in chunks(text):
            params = {"chat_id": chat_id, "text": part}
            if reply_markup:
                params["reply_markup"] = reply_markup
            out.append(self.call("sendMessage", params))
        return out[-1] if out else None

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        params = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return self.call("editMessageText", params)

    def answer_callback_query(self, callback_id, text="", show_alert=False):
        return self.call("answerCallbackQuery", {
            "callback_query_id": callback_id, "text": text,
            "show_alert": bool(show_alert)})

    def set_my_commands(self, commands):
        return self.call("setMyCommands", {"commands": commands})


def keyboard(rows):
    """صفحه‌کلید درون‌خطی: rows فهرست ردیف‌ها، هر ردیف فهرست (متن، داده)."""
    return {"inline_keyboard": [
        [{"text": label, "callback_data": data} for label, data in row]
        for row in rows if row]}


def poll_forever(api, on_updates, log=print, stop=None, idle_sleep=1.0):
    """حلقهٔ نظرسنجی طولانی؛ تا زمانی که `stop` نداده باشد ادامه می‌یابد."""
    offset = None
    backoff = 2.0
    while True:
        if stop is not None and stop():
            return
        try:
            updates = api.get_updates(offset=offset, timeout=25)
            backoff = 2.0
        except BaleError as exc:
            log("[poll] خطا: {}".format(exc))
            wait = exc.retry_after or backoff
            time.sleep(min(float(wait), 30))
            backoff = min(backoff * 2, 30)
            continue
        except Exception as exc:                # noqa: BLE001 - هیچ خطایی نباید حلقه را بکشد
            log("[poll] خطای غیرمنتظره: {!r}".format(exc))
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        if not updates:
            time.sleep(idle_sleep)
            continue
        for upd in updates:
            try:
                uid = int(upd.get("update_id") or 0)
                offset = uid + 1
            except (TypeError, ValueError):
                pass
            try:
                on_updates(upd)
            except Exception as exc:            # noqa: BLE001
                log("[handle] خطا در پردازش به‌روزرسانی: {!r}".format(exc))
