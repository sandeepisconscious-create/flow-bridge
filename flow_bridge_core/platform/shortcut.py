"""
Low-latency OS Shortcut Key Hold Monitor.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from typing import Optional


class ShortcutWatcher:
    """Monitors push-to-talk shortcut keys (Fn/Globe, Ctrl, Option) using low-overhead OS queries."""

    _cg = None
    _objc = None
    _msgSend = None
    _NSEvent = None
    _flags_sel = None

    @classmethod
    def _init(cls) -> None:
        if cls._cg is None:
            try:
                cg_path = ctypes.util.find_library("CoreGraphics")
                if cg_path:
                    cls._cg = ctypes.cdll.LoadLibrary(cg_path)
                    cls._cg.CGEventSourceKeyState.restype = ctypes.c_bool
                    cls._cg.CGEventSourceKeyState.argtypes = [ctypes.c_int32, ctypes.c_uint16]
            except Exception:
                cls._cg = False

        if cls._objc is None:
            try:
                objc_path = ctypes.util.find_library("objc")
                appkit_path = ctypes.util.find_library("AppKit")
                if objc_path and appkit_path:
                    cls._objc = ctypes.cdll.LoadLibrary(objc_path)
                    ctypes.cdll.LoadLibrary(appkit_path)
                    cls._objc.objc_getClass.restype = ctypes.c_void_p
                    cls._objc.objc_getClass.argtypes = [ctypes.c_char_p]
                    cls._objc.sel_registerName.restype = ctypes.c_void_p
                    cls._objc.sel_registerName.argtypes = [ctypes.c_char_p]
                    cls._msgSend = ctypes.cast(
                        cls._objc.objc_msgSend,
                        ctypes.CFUNCTYPE(ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_void_p)
                    )
                    cls._NSEvent = cls._objc.objc_getClass(b"NSEvent")
                    cls._flags_sel = cls._objc.sel_registerName(b"modifierFlags")
            except Exception:
                cls._objc = False

    @classmethod
    def which_app_shortcut_held(cls) -> Optional[str]:
        """Returns the name of the app whose shortcut is currently held, or None."""
        cls._init()
        cg = cls._cg

        # Fast path: Check hardware keycodes directly via CoreGraphics (microsecond lookup)
        if cg:
            # 1. Wispr Flow: Fn / Globe key (keycode 63)
            if cg.CGEventSourceKeyState(0, 63) or cg.CGEventSourceKeyState(1, 63):
                return "Wispr Flow"

            # 2. Handy: Left Ctrl (keycode 59) or Right Ctrl (62)
            if (cg.CGEventSourceKeyState(0, 59) or cg.CGEventSourceKeyState(1, 59) or
                cg.CGEventSourceKeyState(0, 62) or cg.CGEventSourceKeyState(1, 62)):
                return "Handy"

            # 3. Detta / Generic: Option key (keycode 58, 61)
            if (cg.CGEventSourceKeyState(0, 58) or cg.CGEventSourceKeyState(1, 58) or
                cg.CGEventSourceKeyState(0, 61) or cg.CGEventSourceKeyState(1, 61)):
                return "Detta"

        # Secondary fallback: NSEvent modifierFlags if CG didn't register
        if cls._msgSend and cls._NSEvent and cls._flags_sel:
            try:
                flags = cls._msgSend(cls._NSEvent, cls._flags_sel)
                if flags & 0x800000:
                    return "Wispr Flow"
                if flags & 0x40000:
                    return "Handy"
                if flags & 0x80000:
                    return "Detta"
            except Exception:
                pass

        return None

    @classmethod
    def is_shortcut_held(cls) -> bool:
        """Returns True if any push-to-talk key is currently held down."""
        return cls.which_app_shortcut_held() is not None
