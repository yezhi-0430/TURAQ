"""Bounded PDF text extraction in a disposable subprocess; never executes PDF actions."""

import io
import json
import os
import re
import sys

from pypdf import PdfReader

_job_handle = None
MAX_PAGES = 1500
# Only these messages are shown to users; anything else stays generic.
SAFE_ERRORS = (
    "PDF无效或超过20MiB",
    "加密PDF暂不支持",
    f"PDF超过{MAX_PAGES}页解析上限",
    "PDF页内容超过解析上限",
    "未提取到文字，可能为扫描件；OCR尚未接通",
)
_WIDE_SPACE = re.compile(r" {3,}")
_TRAILING = re.compile(r"[ 	]+$", re.M)


def compact(text):
    """Collapse layout padding so large reports stay within output/cache caps."""
    return _TRAILING.sub("", _WIDE_SPACE.sub("  ", text))


def limit_process_memory():
    """Apply a hard child-process memory ceiling before decompressing any PDF streams."""
    ceiling = 768 * 1024 * 1024
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
        return
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [
            ("user", ctypes.c_int64),
            ("job", ctypes.c_int64),
            ("flags", wintypes.DWORD),
            ("min_ws", ctypes.c_size_t),
            ("max_ws", ctypes.c_size_t),
            ("processes", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", ctypes.c_uint64 * 6),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t),
            ("peak_job", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    global _job_handle
    _job_handle = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x100
    limits.process_memory = ceiling
    if (
        not _job_handle
        or not kernel.SetInformationJobObject(
            _job_handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        )
        or not kernel.AssignProcessToJobObject(_job_handle, kernel.GetCurrentProcess())
    ):
        raise OSError("Unable to establish PDF process memory limit")


def extract(data):
    if len(data) > 20 * 1024 * 1024 or not data.startswith(b"%PDF-"):
        raise ValueError("PDF无效或超过20MiB")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError("加密PDF暂不支持")
    if len(reader.pages) > MAX_PAGES:
        raise ValueError(f"PDF超过{MAX_PAGES}页解析上限")
    pages, warnings = [], []
    for index, page in enumerate(reader.pages):
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > 8 * 1024 * 1024:
            raise ValueError("PDF页内容超过解析上限")
        # Blank pages (no content stream) make pypdf's layout mode raise KeyError.
        text = (
            page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False) or ""
            if contents is not None
            else ""
        )
        pages.append(dict(page=index + 1, text=compact(text)))
    if not any(p["text"].strip() for p in pages):
        raise ValueError("未提取到文字，可能为扫描件；OCR尚未接通")
    return dict(pages=pages, warnings=warnings)


if __name__ == "__main__":
    try:
        limit_process_memory()
        result = extract(sys.stdin.buffer.read(20 * 1024 * 1024 + 1))
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) and str(exc) in SAFE_ERRORS else ""
        error = message or "PDF text extraction failed"
        sys.stdout.buffer.write(json.dumps(dict(error=error), ensure_ascii=False).encode("utf-8"))
        sys.exit(1)
