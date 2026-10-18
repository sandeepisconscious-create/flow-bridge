"""
macOS Platform Abstractions: Native NSPasteboard & System Notifications.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
import sys
from typing import Optional


class PasteboardManager:
    """
    Manages the macOS system clipboard with in-process native AppKit NSPasteboard (0.1ms latency)
    and fallback to the standard pbcopy CLI binary.
    """

    _initialized: bool = False
    _pb: Optional[int] = None
    _clear_sel: Optional[int] = None
    _set_sel: Optional[int] = None
    _utf8_sel: Optional[int] = None
    _nsstring_cls: Optional[int] = None
    _type_str: Optional[int] = None
    _msg_void_void = None
    _msg_str_init = None
    _msg_bool_two = None

    @classmethod
    def _init_native(cls) -> None:
        if cls._initialized:
            return
        cls._initialized = True
        try:
            appkit_path = ctypes.util.find_library("AppKit")
            objc_path = ctypes.util.find_library("objc")
            if not appkit_path or not objc_path:
                return

            objc = ctypes.cdll.LoadLibrary(objc_path)
            appkit = ctypes.cdll.LoadLibrary(appkit_path)

            objc.objc_getClass.restype = ctypes.c_void_p
            objc.objc_getClass.argtypes = [ctypes.c_char_p]
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]

            cls._msg_void_void = ctypes.cast(
                objc.objc_msgSend,
                ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
            )
            cls._msg_str_init = ctypes.cast(
                objc.objc_msgSend,
                ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)
            )
            cls._msg_bool_two = ctypes.cast(
                objc.objc_msgSend,
                ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
            )

            ns_pb_cls = objc.objc_getClass(b"NSPasteboard")
            cls._nsstring_cls = objc.objc_getClass(b"NSString")
            cls._clear_sel = objc.sel_registerName(b"clearContents")
            cls._set_sel = objc.sel_registerName(b"setString:forType:")
            cls._utf8_sel = objc.sel_registerName(b"stringWithUTF8String:")

            gen_sel = objc.sel_registerName(b"generalPasteboard")
            cls._pb = cls._msg_void_void(ns_pb_cls, gen_sel)
            cls._type_str = ctypes.c_void_p.in_dll(appkit, "NSPasteboardTypeString").value
        except Exception:
            cls._pb = None

    @classmethod
    def set_clipboard(cls, text: str) -> bool:
        """Sets clipboard with near-zero overhead (~0.1ms)."""
        if not text:
            return False

        # 1. In-process native AppKit NSPasteboard (fastest: 0.1ms, zero subprocess creation)
        cls._init_native()
        if cls._pb:
            try:
                cls._msg_void_void(cls._pb, cls._clear_sel)
                ns_str = cls._msg_str_init(cls._nsstring_cls, cls._utf8_sel, text.encode("utf-8"))
                if cls._msg_bool_two(cls._pb, cls._set_sel, ns_str, cls._type_str):
                    return True
            except Exception:
                pass

        # 2. Standard CLI fallback (pbcopy)
        try:
            with subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, close_fds=True) as proc:
                proc.communicate(input=text.encode("utf-8"), timeout=2.0)
                return proc.returncode == 0
        except Exception as err:
            print(f"[Flow Bridge Error] Failed to set clipboard: {err}", file=sys.stderr)
            return False

    @staticmethod
    def get_clipboard() -> str:
        """Reads current clipboard contents using pbpaste."""
        try:
            with subprocess.Popen(["pbpaste"], stdout=subprocess.PIPE, close_fds=True) as proc:
                stdout, _ = proc.communicate(timeout=1.0)
                return stdout.decode("utf-8", errors="replace")
        except Exception:
            return ""


class Notifier:
    """Optional unobtrusive macOS system notification banner."""

    @staticmethod
    def notify(title: str, subtitle: str, message: str) -> None:
        clean_msg = message.replace('"', '\\"').replace("\n", " ")[:90]
        script = f'display notification "{clean_msg}" with title "{title}" subtitle "{subtitle}"'
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=1.5)
        except Exception:
            pass
