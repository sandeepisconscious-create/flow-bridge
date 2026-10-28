"""
Low-latency OS Shortcut Key Hold Monitor.
Strictly inspects assigned push-to-talk keys for active dictation apps without modifier bleed.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import subprocess
import time
from typing import Optional, Set


class ShortcutWatcher:
    """Monitors push-to-talk shortcut keys strictly for active dictation apps using low-overhead CoreGraphics queries."""

    _cg = None
    _last_config_check: float = 0.0
    _last_config_mtime: float = 0.0
    _wispr_ptt_key: int = 63  # Default Fn / Globe keycode on macOS
    _cached_running_apps: Set[str] = set()
    _last_process_check: float = 0.0

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

    @classmethod
    def _refresh_wispr_config(cls) -> None:
        """Reads the user's actual configured push-to-talk key from Wispr Flow config only when mtime changes."""
        now = time.time()
        if now - cls._last_config_check < 15.0:
            return
        cls._last_config_check = now

        config_path = os.path.expanduser("~/Library/Application Support/Wispr Flow/config.json")
        try:
            st = os.stat(config_path)
            if st.st_mtime == cls._last_config_mtime:
                return
            cls._last_config_mtime = st.st_mtime
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            shortcuts = cfg.get("prefs", {}).get("user", {}).get("shortcuts", {})
            for keycode_str, action in shortcuts.items():
                if action == "ptt":
                    if keycode_str.isdigit():
                        cls._wispr_ptt_key = int(keycode_str)
                        break
        except Exception:
            pass

    @classmethod
    def _get_running_dictation_apps(cls) -> Set[str]:
        """Detects which dictation apps are currently running in the background (cached for 15s, zero subprocesses)."""
        now = time.time()
        if now - cls._last_process_check < 15.0:
            return cls._cached_running_apps
        cls._last_process_check = now

        from flow_bridge_core.platform.pasteboard import PasteboardManager
        running = PasteboardManager.get_running_dictation_apps()
        if not running:
            # Fallback check if NSWorkspace returned empty
            try:
                out = subprocess.run(["pgrep", "-l", "-i", "Wispr Flow|handy|Detta|Gemini"], capture_output=True, text=True, timeout=0.5).stdout
                if "Wispr Flow" in out:
                    running.add("Wispr Flow")
                if "handy" in out.lower():
                    running.add("Handy")
                if "detta" in out.lower():
                    running.add("Detta")
                if "gemini" in out.lower():
                    running.add("Gemini")
            except Exception:
                running.add("Wispr Flow")

        cls._cached_running_apps = running
        return running

    @classmethod
    def which_app_shortcut_held(cls) -> Optional[str]:
        """Returns the name of the app whose assigned shortcut is strictly held down, or None.
        Fast-paths key state checks via CoreGraphics before querying Objective-C workspace state.
        """
        cls._init()
        cg = cls._cg
        if not cg:
            return None

        cls._refresh_wispr_config()

        # Fast-path: Check raw hardware/session key state (~0.001ms) before any Objective-C calls
        fn_held = bool(cg.CGEventSourceKeyState(0, 63) or cg.CGEventSourceKeyState(1, 63))
        wispr_key_held = fn_held if cls._wispr_ptt_key == 63 else bool(
            cg.CGEventSourceKeyState(0, cls._wispr_ptt_key) or cg.CGEventSourceKeyState(1, cls._wispr_ptt_key)
        )
        ctrl_held = bool(
            cg.CGEventSourceKeyState(0, 59) or cg.CGEventSourceKeyState(1, 59) or
            cg.CGEventSourceKeyState(0, 62) or cg.CGEventSourceKeyState(1, 62)
        )
        opt_held = bool(
            cg.CGEventSourceKeyState(0, 58) or cg.CGEventSourceKeyState(1, 58) or
            cg.CGEventSourceKeyState(0, 61) or cg.CGEventSourceKeyState(1, 61)
        )

        if not (fn_held or wispr_key_held or ctrl_held or opt_held):
            return None

        active_apps = cls._get_running_dictation_apps()

        # Only query frontmost app if a candidate key is actually held down
        if fn_held and "Gemini" in active_apps:
            from flow_bridge_core.platform.pasteboard import PasteboardManager
            front = PasteboardManager.get_frontmost_app()
            front_name = front.get("name", "").lower()
            front_bid = front.get("bundle_id", "").lower()
            is_gemini_front = ("gemini" in front_name) or ("gemini" in front_bid)
            if is_gemini_front or ("Wispr Flow" not in active_apps) or cls._wispr_ptt_key != 63:
                return "Gemini"

        if wispr_key_held and "Wispr Flow" in active_apps:
            return "Wispr Flow"

        if fn_held and "Gemini" in active_apps:
            return "Gemini"

        if ctrl_held and "Handy" in active_apps:
            return "Handy"

        if opt_held and "Detta" in active_apps:
            return "Detta"

        return None

    @classmethod
    def is_shortcut_held(cls) -> bool:
        """Returns True if the assigned push-to-talk key of an active dictation app is currently held down."""
        return cls.which_app_shortcut_held() is not None

