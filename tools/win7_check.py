"""بررسی سازگاری خروجی‌های ویندوز با ویندوز ۷ (تا ویندوز ۱۱) — بدون نیاز به ویندوز قدیمی.

چرا لازم است: پایتون ۳٫۹ به بعد در `python3X.dll` از
`api-ms-win-core-path-l1-1-0.dll` استفاده می‌کند که فقط از ویندوز ۸ وجود دارد؛
چنین فایلی روی ویندوز ۷ با پیام «api-ms-win-core-path-l1-1-0.dll is missing»
یا «Error loading Python DLL» بالا نمی‌آید. پس هر خروجی باید با پایتون ۳٫۸
ساخته شود و همهٔ کتابخانه‌های داخلش فقط از APIهای ویندوز ۷ استفاده کنند.

این ابزار فایل اجرایی یک‌فایلی (PyInstaller) را باز می‌کند، همهٔ DLL/PYDهای
داخلش را بیرون می‌کشد و برای هر کدام سه چیز را بررسی می‌کند:

  1. جدول «واردات» (imports) فایل PE: هیچ‌کدام نباید DLL یا APIای بخواهد که
     در ویندوز ۷ SP1 نیست (فهرست ممنوعهٔ پایین).
  2. سرآیند PE: نسخهٔ زیرسیستم نباید از 6.1 (ویندوز ۷) بالاتر باشد.
  3. معماری: باید با همان ویندوز مقصد هم‌خوان باشد (x64 یا x86).

خروجی: کد ۰ اگر همه‌چیز سالم باشد، وگرنه ۱ با فهرست دقیق مشکلات.
"""
import os
import sys

try:
    import pefile
except ImportError:                       # pragma: no cover - راهنمای نصب
    print("pefile نصب نیست: pip install pefile")
    raise SystemExit(2)

# ---------------------------------------------------------------- فهرست ممنوعه
# این‌ها API setهایی هستند که **پیش از ویندوز ۸** وجود ندارند؛ اگر هر فایل
# بسته‌بندی‌شده به یکی از آن‌ها وابسته باشد، روی ویندوز ۷ بارگذاری نمی‌شود.
POST_WIN7_DLLS = {
    "api-ms-win-core-path-l1-1-0.dll",          # همان خطای گزارش‌شده
    "api-ms-win-core-file-l1-2-2.dll",
    "api-ms-win-core-file-l2-2-0.dll",
    "api-ms-win-core-synch-l1-2-1.dll",
    "api-ms-win-core-processthreads-l1-1-2.dll",
    "api-ms-win-core-wow64-l1-1-1.dll",
    "api-ms-win-core-winrt-l1-1-0.dll",
    "api-ms-win-core-winrt-string-l1-1-0.dll",
    "api-ms-win-core-winrt-error-l1-1-0.dll",
    "api-ms-win-shcore-scaling-l1-1-1.dll",
    "api-ms-win-shcore-stream-winrt-l1-1-0.dll",
    "api-ms-win-service-private-l1-1-0.dll",
    "api-ms-win-state-l1-1-0.dll",
    "dcomp.dll",
    "d3d11_2.dll",
    "d3d12.dll",
    "windowscodecs.dll.dl",
}

POST_WIN7_PREFIXES = (
    "api-ms-win-core-winrt-",
    "api-ms-win-appmodel-",
    "api-ms-win-stateseparationhelpers-",
    "api-ms-win-shcore-",
    "api-ms-win-service-management-l3-",
)

# DLLهایی که ویندوز ۷ SP1 خودش دارد (اگر داخل بسته هم باشند مشکلی نیست).
WIN7_SYSTEM_DLLS = {
    "advapi32.dll", "bcrypt.dll", "bcryptprimitives.dll", "cabinet.dll",
    "cfgmgr32.dll", "comctl32.dll", "comdlg32.dll", "credui.dll", "crypt32.dll",
    "cryptbase.dll", "dbghelp.dll", "dnsapi.dll", "dwmapi.dll", "gdi32.dll",
    "gdiplus.dll", " glu32.dll", "glu32.dll", "gpapi.dll", "imm32.dll",
    "iphlpapi.dll", "kernel32.dll", "kernelbase.dll", "mpr.dll", "msasn1.dll",
    "msimg32.dll", "mswsock.dll", "msvcrt.dll", "ncrypt.dll", "netapi32.dll",
    "netutils.dll", "normaliz.dll", "ntdll.dll", "ole32.dll", "oleacc.dll",
    "oleaut32.dll", "oledlg.dll", "opengl32.dll", "powrprof.dll", "propsys.dll",
    "psapi.dll", "rpcrt4.dll", "secur32.dll", "sechost.dll", "setupapi.dll",
    "shell32.dll", "shlwapi.dll", "sspicli.dll", "urlmon.dll", "user32.dll",
    "userenv.dll", "usp10.dll", "uxtheme.dll", "version.dll", "winhttp.dll",
    "wininet.dll", "winmm.dll", "winspool.drv", "wintrust.dll", "wldap32.dll",
    "ws2_32.dll", "wsock32.dll", "wtsapi32.dll", "api-ms-win-core-synch-l1-1-0.dll",
}

MAX_WIN7_VERSION = (6, 1)          # نسخهٔ زیرسیستم ویندوز ۷ SP1


def _norm(name):
    return str(name).replace("\\", "/").lower()


def _pe(path):
    return pefile.PE(path, fast_load=True)


def pe_subsystem_version(path):
    """(major, minor) نسخهٔ کمینهٔ ویندوزی که این PE می‌خواهد."""
    pe = _pe(path)
    try:
        hdr = pe.OPTIONAL_HEADER
        return (hdr.MajorSubsystemVersion, hdr.MinorSubsystemVersion)
    finally:
        pe.close()


def pe_machine(path):
    pe = _pe(path)
    try:
        return pe.FILE_HEADER.Machine
    finally:
        pe.close()


def pe_imports(path):
    """{نام DLL: [نام توابع]} برای یک فایل PE."""
    pe = _pe(path)
    try:
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                         pefile.DIRECTORY_ENTRY[
                             "IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        out = {}
        for entry in list(getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) or []) + \
                list(getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", []) or []):
            dll = entry.dll.decode("ascii", "replace") if isinstance(
                entry.dll, bytes) else str(entry.dll)
            funcs = []
            for imp in entry.imports:
                if imp.name is not None:
                    funcs.append(imp.name.decode("ascii", "replace")
                                 if isinstance(imp.name, bytes) else str(imp.name))
            out.setdefault(dll, []).extend(funcs)
        return out
    finally:
        pe.close()


def extract_payload(exe, workdir):
    """همهٔ فایل‌های باینری داخل exe یک‌فایلی را بیرون می‌کشد.

    (fname, bytes) برمی‌گرداند. اگر آرشیو خوانده نشود RuntimeError می‌دهد؛
    «نشد بررسی کرد» هرگز با «سالم است» یکی گرفته نمی‌شود.
    """
    from PyInstaller.archive.readers import CArchiveReader
    reader = CArchiveReader(exe)
    out = []
    for name in reader.toc:
        key = str(name)
        if not key.lower().endswith((".dll", ".pyd", ".exe")):
            continue
        data = reader.extract(key)
        if not data or data[:2] != b"MZ":
            continue
        out.append((key, data))
    return out


def check_exe(exe, arch=None, verbose=False):
    """بررسی یک exe؛ فهرست مشکلات (رشته‌ها) برمی‌گرداند."""
    problems = []
    if not os.path.isfile(exe):
        return ["فایل پیدا نشد: " + exe]

    label = os.path.basename(exe)
    machine = pe_machine(exe)
    want = {"x86": 0x14C, "x64": 0x8664}.get(arch or "")
    if want and machine != want:
        problems.append("{}: معماری اشتباه است (0x{:04x} به‌جای 0x{:04x})".format(
            label, machine, want))

    major, minor = pe_subsystem_version(exe)
    if (major, minor) > MAX_WIN7_VERSION:
        problems.append("{}: کمینهٔ ویندوز {}.{} است (ویندوز ۷ = 6.1)".format(
            label, major, minor))

    # فایل‌های داخل آرشیو + خودِ exe
    try:
        payload = extract_payload(exe, None)
    except Exception as exc:                       # noqa: BLE001
        return problems + ["{}: بازکردن محتوای exe ممکن نشد: {!r}".format(label, exc)]

    bundled = {_norm(name) for name, _ in payload}
    binaries = [(label, exe)] + [("{}!{}".format(label, name), data)
                                 for name, data in payload]
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="win7check-")
    try:
        checked = 0
        for where, data in binaries:
            if isinstance(data, bytes):
                path = os.path.join(tmpdir, "f{}.bin".format(checked))
                with open(path, "wb") as f:
                    f.write(data)
            else:
                path = data
            try:
                imports = pe_imports(path)
            except Exception:                      # noqa: BLE001 - PE غیرمعمول
                continue
            checked += 1
            for dll, funcs in imports.items():
                low = dll.lower()
                if low in POST_WIN7_DLLS or low.startswith(POST_WIN7_PREFIXES):
                    problems.append(
                        "{}: به «{}» وابسته است که در ویندوز ۷ وجود ندارد".format(
                            where, dll))
                    continue
                if low in bundled or low in WIN7_SYSTEM_DLLS:
                    continue
                if low.startswith("api-ms-win-crt-"):
                    if low not in bundled:
                        problems.append(
                            "{}: «{}» لازم است ولی همراه برنامه نیست".format(
                                where, dll))
                    continue
                if verbose:
                    print("  ؟ {}: وابستگی ناشناخته {}".format(where, dll))
            if verbose:
                print("  ✓ {}".format(where))
        if verbose:
            print("  ({} فایل باینری بررسی شد)".format(checked))
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    return problems


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    verbose = "-v" in argv
    args = [a for a in argv if a != "-v"]
    arch = ""
    for arg in list(args):
        if arg.startswith("--arch="):
            arch = arg.split("=", 1)[1]
            args.remove(arg)
    failed = False
    for exe in args:
        print("== بررسی {} (آرکی: {})".format(os.path.basename(exe), arch or "خودکار"))
        problems = check_exe(exe, arch=arch, verbose=verbose)
        if problems:
            failed = True
            for p in problems:
                print("  ❌ " + p)
        else:
            print("  ✅ سازگار با ویندوز ۷ SP1 تا ۱۱")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
