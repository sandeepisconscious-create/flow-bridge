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
        """Reads the user's actual configured push-to-talk key from Wispr Flow config."""
        now = time.time()
        if now - cls._last_config_check < 5.0:
            return
        cls._last_config_check = now

        config_path = os.path.expanduser("~/Library/Application Support/Wispr Flow/config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                shortcuts = cfg.get("prefs", {}).get("user", {}).get("shortcuts", {})
                for keycode_str, action in shortcuts.items():
                    if action == "ptt":
                        # If simple keycode like "63", parse it
                        if keycode_str.isdigit():
                            cls._wispr_ptt_key = int(keycode_str)
                            break
            except Exception:
                pass

    @classmethod
    def _get_running_dictation_apps(cls) -> Set[str]:
        """Detects which dictation apps are currently running in the background."""
        now = time.time()
        if now - cls._last_process_check < 3.0:
            return cls._cached_running_apps
        cls._last_process_check = now

        running = set()
        try:
            # Fast check of running processes
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
            # Fallback to Wispr Flow if check fails
            running.add("Wispr Flow")

        cls._cached_running_apps = running
        return running

    @classmethod
    def which_app_shortcut_held(cls) -> Optional[str]:
        """Returns the name of the app whose assigned shortcut is strictly held down, or None."""
        cls._init()
        cg = cls._cg
        if not cg:
            return None

        cls._refresh_wispr_config()
        active_apps = cls._get_running_dictation_apps()

        # 1. Wispr Flow: Only inspect if Wispr Flow is running and its exact assigned PTT key is held
        if "Wispr Flow" in active_apps or (not active_apps and "Gemini" not in active_apps):
            # StateSource 0 = CombinedSessionState, 1 = HIDSystemState
            if cg.CGEventSourceKeyState(0, cls._wispr_ptt_key) or cg.CGEventSourceKeyState(1, cls._wispr_ptt_key):
                return "Wispr Flow"

        # 2. Gemini: Defaults to Fn / Globe key (63) on macOS
        if "Gemini" in active_apps:
            if cg.CGEventSourceKeyState(0, 63) or cg.CGEventSourceKeyState(1, 63):
                return "Gemini"

        # 3. Handy: Only check if Handy is actually running
        if "Handy" in active_apps:
            if (cg.CGEventSourceKeyState(0, 59) or cg.CGEventSourceKeyState(1, 59) or
                cg.CGEventSourceKeyState(0, 62) or cg.CGEventSourceKeyState(1, 62)):
                return "Handy"

        # 4. Detta: Only check if Detta is actually running
        if "Detta" in active_apps:
            if (cg.CGEventSourceKeyState(0, 58) or cg.CGEventSourceKeyState(1, 58) or
                cg.CGEventSourceKeyState(0, 61) or cg.CGEventSourceKeyState(1, 61)):
                return "Detta"

        return None

    @classmethod
    def is_shortcut_held(cls) -> bool:
        """Returns True if the assigned push-to-talk key of an active dictation app is currently held down."""
        return cls.which_app_shortcut_held() is not None

