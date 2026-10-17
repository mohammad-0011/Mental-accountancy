"""کلاینت لایسنس آنلاین: گفت‌وگو با سرور لایسنس (بات بله سمت سرور).

تنها برای *گرفتن* و *بررسی* لایسنس است؛ اعتبار لایسنس همیشه با امضای
Ed25519 و کلید عمومی داخل برنامه بررسی می‌شود. یعنی حتی اگر کسی پاسخ سرور
را دست‌کاری کند (حملهٔ میانی)، نمی‌تواند لایسنس جعلی جا بزند — فقط شاید
بتواند بررسی را قطع کند.
"""
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

APP_HEADER = "X-Saba-Client"
ADMIN_HEADER = "X-Saba-Admin"
DEFAULT_TIMEOUT = 20


class CloudError(Exception):
    """خطای گفت‌وگو با سرور لایسنس (شبکه یا پاسخ نادرست)."""

    def __init__(self, message, kind="error"):
        super().__init__(message)
        self.kind = kind          # network | http | data | config
        self.message = message


def _ssl_context(insecure=False):
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


class CloudClient:
    """فراخوانی نشانی‌های /api/v1 سرور لایسنس."""

    def __init__(self, base_url, client_token="", timeout=DEFAULT_TIMEOUT,
                 insecure=False, admin_token=""):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.client_token = (client_token or "").strip()
        self.admin_token = (admin_token or "").strip()
        self.timeout = timeout
        self.insecure = insecure

    # ---------------------------------------------------------------- پایه
    def _call(self, path, params=None, payload=None, method=None, admin=False):
        if not self.base_url:
            raise CloudError("نشانی سرور لایسنس تنظیم نشده است.", "config")
        if not self.base_url.lower().startswith(("http://", "https://")):
            raise CloudError("نشانی سرور لایسنس باید با http:// یا https:// "
                             "شروع شود (مقدار فعلی: {}).".format(self.base_url),
                             "config")
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None
        headers = {"Accept": "application/json"}
        if self.client_token:
            headers[APP_HEADER] = self.client_token
        if admin and self.admin_token:
            headers[ADMIN_HEADER] = self.admin_token
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            req = urllib.request.Request(
                url, data=data, headers=headers,
                method=method or ("POST" if data else "GET"))
            with urllib.request.urlopen(
                    req, timeout=self.timeout,
                    context=_ssl_context(self.insecure)) as resp:
                raw = resp.read()
                status = resp.getcode()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except (urllib.error.URLError, socket.timeout, ssl.SSLError,
                OSError, ValueError) as exc:
            # ValueError هم گرفته می‌شود: نشانی نامعتبر (مثلاً بدون http)
            raise CloudError("ارتباط با سرور لایسنس برقرار نشد: {}".format(
                getattr(exc, "reason", exc)), "network")
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise CloudError("پاسخ سرور لایسنس خوانده نشد (کد {}).".format(status),
                             "data")
        if not isinstance(body, dict):
            raise CloudError("پاسخ سرور لایسنس درست نیست.", "data")
        if status >= 400 or not body.get("ok"):
            raise CloudError(str(body.get("error") or
                                 "خطای سرور لایسنس (کد {})".format(status)),
                             "http" if status >= 400 else "data")
        return body

    # ------------------------------------------------------------ نشانی‌ها
    def info(self):
        return self._call("/api/v1/info")

    def request_activation(self, fingerprint, machine_code, name="", phone="",
                           note=""):
        return self._call("/api/v1/request", payload={
            "fingerprint": fingerprint, "machine_code": machine_code,
            "name": name, "phone": phone, "note": note})

    def status(self, fingerprint, machine_code=""):
        return self._call("/api/v1/status", params={
            "fingerprint": fingerprint, "machine_code": machine_code})

    def checkin(self, fingerprint, machine_code="", lic_id=""):
        return self._call("/api/v1/checkin", payload={
            "fingerprint": fingerprint, "machine_code": machine_code,
            "lic_id": lic_id})

    # ------------------------------------------------------ پنل فروشنده
    # این دو نشانی فقط با توکن مدیر کار می‌کنند؛ همان‌ها که بات بله هم
    # می‌بیند. تأیید از برنامه و تأیید از بات در سرور یکی می‌شوند.
    def admin_requests(self):
        return self._call("/api/v1/admin/requests", admin=True)

    def admin_decide(self, request_id, action, edition="", seats=0, days=None,
                     note=""):
        payload = {"request_id": int(request_id), "action": action,
                   "edition": edition, "seats": seats, "note": note}
        if days is not None:
            payload["days"] = int(days)
        return self._call("/api/v1/admin/decide", payload=payload, admin=True)
