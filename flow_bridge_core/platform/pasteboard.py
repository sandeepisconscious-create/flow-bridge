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
            cls._msg_ptr_ptr = ctypes.cast(
                objc.objc_msgSend,
                ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
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
            cls._get_sel = objc.sel_registerName(b"stringForType:")
            cls._utf8_str_sel = objc.sel_registerName(b"UTF8String")
            cls._change_count_sel = objc.sel_registerName(b"changeCount")
            cls._msg_int_void = ctypes.cast(
                objc.objc_msgSend,
                ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)
            )

            ws_cls = objc.objc_getClass(b"NSWorkspace")
            cls._ws = cls._msg_void_void(ws_cls, objc.sel_registerName(b"sharedWorkspace"))
            cls._frontmost_sel = objc.sel_registerName(b"frontmostApplication")
            cls._running_apps_sel = objc.sel_registerName(b"runningApplications")
            cls._count_sel = objc.sel_registerName(b"count")
            cls._obj_at_idx_sel = objc.sel_registerName(b"objectAtIndex:")
            cls._loc_name_sel = objc.sel_registerName(b"localizedName")
            cls._bid_sel = objc.sel_registerName(b"bundleIdentifier")
            cls._pool_cls = objc.objc_getClass(b"NSAutoreleasePool")
            cls._alloc_sel = objc.sel_registerName(b"alloc")
            cls._init_sel = objc.sel_registerName(b"init")
            cls._drain_sel = objc.sel_registerName(b"drain")
            cls._msg_ulong_void = ctypes.cast(
                objc.objc_msgSend,
                ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)
            )
            cls._msg_ptr_ulong = ctypes.cast(
                objc.objc_msgSend,
                ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
            )
        except Exception:
            cls._pb = None

    @classmethod
    def _create_pool(cls) -> Optional[int]:
        if getattr(cls, "_pool_cls", None) and cls._msg_void_void:
            try:
                p = cls._msg_void_void(cls._pool_cls, cls._alloc_sel)
                return cls._msg_void_void(p, cls._init_sel) if p else None
            except Exception:
                return None
        return None

    @classmethod
    def _drain_pool(cls, pool: Optional[int]) -> None:
        if pool and cls._msg_void_void and getattr(cls, "_drain_sel", None):
            try:
                cls._msg_void_void(pool, cls._drain_sel)
            except Exception:
                pass

    @classmethod
    def set_clipboard(cls, text: str) -> bool:
        """Sets clipboard with near-zero overhead (~0.1ms)."""
        if not text:
            return False

        # 1. In-process native AppKit NSPasteboard (fastest: 0.1ms, zero subprocess creation)
        cls._init_native()
        if cls._pb:
            pool = cls._create_pool()
            try:
                cls._msg_void_void(cls._pb, cls._clear_sel)
                ns_str = cls._msg_str_init(cls._nsstring_cls, cls._utf8_sel, text.encode("utf-8"))
                if cls._msg_bool_two(cls._pb, cls._set_sel, ns_str, cls._type_str):
                    return True
            except Exception:
                pass
            finally:
                cls._drain_pool(pool)

        # 2. Standard CLI fallback (pbcopy)
        try:
            with subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, close_fds=True) as proc:
                proc.communicate(input=text.encode("utf-8"), timeout=2.0)
                return proc.returncode == 0
        except Exception as err:
            print(f"[Flow Bridge Error] Failed to set clipboard: {err}", file=sys.stderr)
            return False

    @classmethod
    def get_clipboard(cls) -> str:
        """Reads current clipboard contents in-process (~0.1ms) with pbpaste fallback."""
        cls._init_native()
        if cls._pb and hasattr(cls, "_msg_ptr_ptr") and cls._msg_ptr_ptr:
            pool = cls._create_pool()
            try:
                ns_str = cls._msg_ptr_ptr(cls._pb, cls._get_sel, cls._type_str)
                if ns_str:
                    cstr = ctypes.cast(cls._msg_void_void(ns_str, cls._utf8_str_sel), ctypes.c_char_p).value
                    if cstr:
                        return cstr.decode("utf-8", errors="replace")
            except Exception:
                pass
            finally:
                cls._drain_pool(pool)

        try:
            with subprocess.Popen(["pbpaste"], stdout=subprocess.PIPE, close_fds=True) as proc:
                stdout, _ = proc.communicate(timeout=1.0)
                return stdout.decode("utf-8", errors="replace")
        except Exception:
            return ""

    @classmethod
    def get_change_count(cls) -> int:
        """Returns the system pasteboard changeCount (0.01ms latency)."""
        cls._init_native()
        if cls._pb and hasattr(cls, "_msg_int_void") and cls._msg_int_void:
            try:
                return int(cls._msg_int_void(cls._pb, cls._change_count_sel))
            except Exception:
                pass
        return 0

    @classmethod
    def get_frontmost_app(cls) -> dict:
        """Returns name and bundle identifier of the active frontmost macOS application (~0.05ms)."""
        cls._init_native()
        if cls._ws and hasattr(cls, "_msg_void_void") and cls._msg_void_void:
            pool = cls._create_pool()
            try:
                app = cls._msg_void_void(cls._ws, cls._frontmost_sel)
                if app:
                    name_ns = cls._msg_void_void(app, cls._loc_name_sel)
                    name_str = ""
                    if name_ns:
                        cstr = ctypes.cast(cls._msg_void_void(name_ns, cls._utf8_str_sel), ctypes.c_char_p).value
                        name_str = cstr.decode("utf-8", errors="replace") if cstr else ""

                    bid_ns = cls._msg_void_void(app, cls._bid_sel)
                    bid_str = ""
                    if bid_ns:
                        cstr2 = ctypes.cast(cls._msg_void_void(bid_ns, cls._utf8_str_sel), ctypes.c_char_p).value
                        bid_str = cstr2.decode("utf-8", errors="replace") if cstr2 else ""

                    return {"name": name_str, "bundle_id": bid_str}
            except Exception:
                pass
            finally:
                cls._drain_pool(pool)
        return {"name": "", "bundle_id": ""}

    @classmethod
    def get_running_dictation_apps(cls) -> set[str]:
        """Returns set of active dictation app names in-process via NSWorkspace (~0.05ms, zero subprocesses)."""
        cls._init_native()
        running: set[str] = set()
        if cls._ws and getattr(cls, "_msg_ulong_void", None) and getattr(cls, "_msg_ptr_ulong", None):
            pool = cls._create_pool()
            try:
                apps = cls._msg_void_void(cls._ws, cls._running_apps_sel)
                if apps:
                    count = cls._msg_ulong_void(apps, cls._count_sel)
                    for i in range(count):
                        app = cls._msg_ptr_ulong(apps, cls._obj_at_idx_sel, i)
                        if not app:
                            continue
                        n_ns = cls._msg_void_void(app, cls._loc_name_sel)
                        b_ns = cls._msg_void_void(app, cls._bid_sel)
                        name_s = ""
                        bid_s = ""
                        if n_ns:
                            c1 = ctypes.cast(cls._msg_void_void(n_ns, cls._utf8_str_sel), ctypes.c_char_p).value
                            if c1:
                                name_s = c1.decode("utf-8", errors="ignore").lower()
                        if b_ns:
                            c2 = ctypes.cast(cls._msg_void_void(b_ns, cls._utf8_str_sel), ctypes.c_char_p).value
                            if c2:
                                bid_s = c2.decode("utf-8", errors="ignore").lower()
                        combined = f"{name_s} {bid_s}"
                        if "wispr" in combined:
                            running.add("Wispr Flow")
                        if "handy" in combined:
                            running.add("Handy")
                        if "detta" in combined:
                            running.add("Detta")
                        if "gemini" in combined:
                            running.add("Gemini")
                return running
            except Exception:
                pass
            finally:
                cls._drain_pool(pool)
        return running


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
