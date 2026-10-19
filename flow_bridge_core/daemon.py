"""
Core Flow Bridge Daemon.
"""

from __future__ import annotations

import fcntl
import json
import os
import select
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Set

from flow_bridge_core.audio.media import MediaController
from flow_bridge_core.models import CURRENT_VERSION, GITHUB_REPO, LOCK_FILE_PATH, DaemonConfig, DictationRecord
from flow_bridge_core.platform.pasteboard import Notifier, PasteboardManager
from flow_bridge_core.platform.shortcut import ShortcutWatcher
from flow_bridge_core.server import start_ui_server
from flow_bridge_core.watchers.engines import BaseDictationWatcher, DettaWatcher, HandyWatcher, WisprFlowWatcher


class FlowBridgeDaemon:
    """Core daemon managing multi-app dictation polling and settle-and-hold clipboard sync."""

    def __init__(self, config: DaemonConfig):
        self.config = config
        self.version = CURRENT_VERSION
        self.watchers: List[BaseDictationWatcher] = [
            WisprFlowWatcher(config.wispr_db),
            DettaWatcher(config.detta_db),
            HandyWatcher(config.handy_db),
        ]
        self._running = True
        self._paused = False
        self._cached_update_info: Optional[dict] = None
        self._last_update_check: float = 0.0

        # Audio/Video pause state
        self._auto_paused_media = False
        self._server = None
        self._kq = None
        self._watched_fds: Dict[int, str] = {}
        self._lock_file = None

    def stop(self):
        """Signals the daemon loop to terminate cleanly."""
        self._running = False

    def _app_has_native_mute(self, app_name: str) -> bool:
        """Checks if the given dictation engine has a built-in mute/pause feature enabled."""
        if app_name == "Wispr Flow":
            try:
                cfg_path = os.path.expanduser("~/Library/Application Support/Wispr Flow/config.json")
                if os.path.exists(cfg_path):
                    with open(cfg_path, "r") as f:
                        data = json.load(f)
                    user_prefs = data.get("prefs", {}).get("user", {})
                    return bool(user_prefs.get("shouldMuteAudio") or user_prefs.get("shouldPauseAudio"))
            except Exception:
                pass
            return False

        elif app_name == "Handy":
            try:
                cfg_path = os.path.expanduser("~/Library/Application Support/com.pais.handy/settings_store.json")
                if os.path.exists(cfg_path):
                    with open(cfg_path, "r") as f:
                        data = json.load(f)
                    return bool(data.get("settings", {}).get("mute_while_recording"))
            except Exception:
                pass
            return False

        return False

    def _start_ptt_listener(self) -> None:
        """Monitors push-to-talk shortcut key hold state across dictation apps.
        Instantly mutes macOS hardware audio output for the duration of speech with minimal CPU wakeups.
        """
        def ptt_loop():
            was_held = False

            while self._running:
                if self.config.auto_pause_media and not self.is_paused():
                    held_app = ShortcutWatcher.which_app_shortcut_held()
                    if held_app and not was_held:
                        was_held = True
                        self._auto_paused_media = True
                        MediaController.pause()
                        if self.config.verbose:
                            print(f"[Flow Bridge] 🎙️ {held_app} shortcut held -> Muted audio.")
                    elif not held_app and was_held:
                        was_held = False
                        self._resume_media_safely()
                else:
                    if was_held:
                        was_held = False
                        self._resume_media_safely()
                # 80ms sleep (~12 Hz) is completely responsive while reducing CPU wakeups by 82%
                time.sleep(0.08)

        t = threading.Thread(target=ptt_loop, daemon=True)
        t.start()

        # Dock tucking thread: deactivated to preserve third-party Electron status item window hierarchies
        pass

    def _resume_media_safely(self) -> None:
        if self._auto_paused_media:
            MediaController.resume()
            self._auto_paused_media = False
            if self.config.verbose:
                print("[Flow Bridge] ▶️ Shortcut released / dictation ended -> Unmuted audio.")

    def set_paused(self, paused: bool) -> bool:
        self._paused = paused
        if self.config.verbose:
            print(f"[Flow Bridge] Sync {'PAUSED' if self._paused else 'RESUMED'}")
        return self._paused

    def is_paused(self) -> bool:
        return self._paused

    def check_for_update(self, force: bool = False) -> dict:
        """Queries GitHub Releases API for new version."""
        now = time.time()
        if not force and self._cached_update_info and (now - self._last_update_check < 600):
            return self._cached_update_info

        try:
            import urllib.request
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "FlowBridge-Updater"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    latest_tag = data.get("tag_name", "").lstrip("v")
                    html_url = data.get("html_url", "")
                    assets = data.get("assets", [])
                    dmg_download = ""
                    for asset in assets:
                        if asset.get("name", "").endswith(".dmg"):
                            dmg_download = asset.get("browser_download_url", "")
                            break

                    has_update = False
                    if latest_tag:
                        try:
                            curr_parts = [int(p) for p in CURRENT_VERSION.split(".")]
                            late_parts = [int(p) for p in latest_tag.split(".")]
                            has_update = late_parts > curr_parts
                        except Exception:
                            has_update = latest_tag != CURRENT_VERSION

                    self._cached_update_info = {
                        "current_version": CURRENT_VERSION,
                        "latest_version": latest_tag,
                        "has_update": has_update,
                        "release_url": html_url,
                        "download_url": dmg_download,
                        "checked_at": datetime.now().strftime("%I:%M %p")
                    }
                    self._last_update_check = now
                    return self._cached_update_info
        except Exception:
            pass

        return {
            "current_version": CURRENT_VERSION,
            "latest_version": CURRENT_VERSION,
            "has_update": False,
            "checked_at": datetime.now().strftime("%I:%M %p")
        }

    def perform_auto_update(self) -> dict:
        """Downloads latest DMG and automatically installs it."""
        info = self.check_for_update(force=True)
        dmg_url = info.get("download_url")
        if not dmg_url:
            return {"success": False, "error": "No DMG download URL found"}

        try:
            import urllib.request
            tmp_dmg = "/tmp/FlowBridge-Latest.dmg"
            urllib.request.urlretrieve(dmg_url, tmp_dmg)

            cmd = f"""
            MOUNT=$(hdiutil attach "{tmp_dmg}" -nobrowse -noautoopen | grep -o '/Volumes/Flow Bridge.*' | head -n 1)
            if [ -n "$MOUNT" ]; then
                cp -R "$MOUNT/FlowBridge.app" /Applications/
                xattr -cr /Applications/FlowBridge.app 2>/dev/null || true
                hdiutil detach "$MOUNT" -force 2>/dev/null || true
            fi
            rm -f "{tmp_dmg}"
            """
            subprocess.run(cmd, shell=True, check=True)
            return {"success": True, "message": f"Updated to v{info.get('latest_version')}!"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _setup_signal_handlers(self) -> None:
        def handle_stop(signum, frame):
            self._running = False
            MediaController.resume()
            print("\n[Flow Bridge] Gracefully stopping daemon...", flush=True)

        signal.signal(signal.SIGINT, handle_stop)
        signal.signal(signal.SIGTERM, handle_stop)

    def print_status(self) -> None:
        print("=" * 66)
        print("🎙️  Flow Bridge: Universal Voice Dictation Clipboard Hub")
        print("=" * 66)
        for watcher in self.watchers:
            status = "🟢 Active" if watcher.is_available() else "⚪ Not Found"
            print(f" • {watcher.source_name:<14}: {status} ({watcher.db_path})")
        print(f" • Polling Interval: {self.config.poll_interval_sec}s")
        print(f" • Settle & Hold   : {self.config.settle_delay_sec}s delay + {self.config.reassert_attempts}x reasserts")
        print(f" • Notifications   : {'Enabled' if self.config.show_notifications else 'Disabled'}")
        print("=" * 66)

    def get_app_status(self) -> List[dict]:
        """Returns detection status of all registered dictation engines."""
        return [
            {"name": w.source_name, "available": w.is_available(), "path": w.db_path}
            for w in self.watchers
        ]

    def get_recent_history(self, limit: int = 10) -> List[dict]:
        """Combines and returns the latest N dictations across all detected engines."""
        all_records: List[DictationRecord] = []
        for watcher in self.watchers:
            all_records.extend(watcher.get_history(limit=limit))

        all_records.sort(key=lambda r: r.timestamp, reverse=True)
        top = all_records[:limit]

        def format_time_compact(ts: float) -> str:
            dt = datetime.fromtimestamp(ts)
            # e.g. 6:53pm (lowercase, no leading zero on hour)
            hour = dt.strftime("%I").lstrip("0") or "12"
            minute = dt.strftime("%M")
            ampm = dt.strftime("%p").lower()
            return f"{hour}:{minute}{ampm}"

        return [
            {
                "id": r.unique_id,
                "source": r.source_name,
                "text": r.text,
                "timestamp": r.timestamp,
                "time": format_time_compact(r.timestamp)
            }
            for r in top
        ]

    def _acquire_single_instance_lock(self) -> None:
        """Ensures only a single instance of Flow Bridge runs concurrently."""
        try:
            self._lock_file = open(LOCK_FILE_PATH, "a+")
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.seek(0)
            self._lock_file.truncate()
            self._lock_file.write(f"{os.getpid()}\n")
            self._lock_file.flush()
        except (IOError, BlockingIOError):
            try:
                with open(LOCK_FILE_PATH, "r") as f:
                    old_pid = int(f.read().strip())
                if old_pid != os.getpid():
                    print(f"[Flow Bridge] Replacing existing instance (PID: {old_pid})...")
                    os.kill(old_pid, signal.SIGTERM)
                    time.sleep(0.4)
                    fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._lock_file.seek(0)
                    self._lock_file.truncate()
                    self._lock_file.write(f"{os.getpid()}\n")
                    self._lock_file.flush()
            except Exception:
                print("[Flow Bridge] Another instance is already running. Exiting.")
                sys.exit(0)

    def _setup_kqueue_watchers(self) -> None:
        """Sets up macOS kernel kqueue event filters on databases, WAL files, and parent dirs."""
        if not hasattr(select, "kqueue"):
            return

        try:
            self._kq = select.kqueue()
            self._watched_fds = {}
            self._resync_kqueue_descriptors()
        except Exception as e:
            if self.config.verbose:
                print(f"[Flow Bridge] kqueue init warning: {e}", file=sys.stderr)
            self._kq = None

    def _resync_kqueue_descriptors(self) -> None:
        """Dynamically registers or re-registers vnodes for all active databases, wal logs, and directories."""
        if not self._kq:
            return

        current_paths: Set[str] = set()
        for watcher in self.watchers:
            db = watcher.db_path
            parent = os.path.dirname(db)
            wal = f"{db}-wal"
            for p in (parent, db, wal):
                if os.path.exists(p):
                    current_paths.add(p)

        existing_paths = set(self._watched_fds.values())
        if current_paths == existing_paths:
            return

        for fd, path in list(self._watched_fds.items()):
            if path not in current_paths:
                try:
                    os.close(fd)
                except Exception:
                    pass
                del self._watched_fds[fd]

        registered_paths = set(self._watched_fds.values())
        for path in current_paths - registered_paths:
            try:
                fd = os.open(path, os.O_RDONLY)
                flags = select.KQ_EV_ADD | select.KQ_EV_CLEAR
                fflags = (
                    select.KQ_NOTE_WRITE |
                    select.KQ_NOTE_EXTEND |
                    select.KQ_NOTE_ATTRIB |
                    select.KQ_NOTE_LINK |
                    select.KQ_NOTE_RENAME
                )
                ev = select.kevent(fd, filter=select.KQ_FILTER_VNODE, flags=flags, fflags=fflags)
                self._kq.control([ev], 0, 0)
                self._watched_fds[fd] = path
            except Exception:
                pass

    def run(self) -> None:
        self._acquire_single_instance_lock()
        self._setup_signal_handlers()
        self._server = start_ui_server(self)
        self._start_ptt_listener()
        self._setup_kqueue_watchers()
        self.print_status()

        last_copied_id: Optional[str] = None
        newest_startup_ts: float = 0.0

        for watcher in self.watchers:
            record = watcher.get_latest()
            if record and record.timestamp > newest_startup_ts:
                newest_startup_ts = record.timestamp
                last_copied_id = record.unique_id

        if last_copied_id and self.config.verbose:
            print(f"[Flow Bridge] Initialized baseline record: {last_copied_id}")

        last_fd_resync = time.time()

        while self._running:
            try:
                if self._kq and len(self._watched_fds) > 0:
                    try:
                        self._kq.control(None, 8, 0.5)
                    except InterruptedError:
                        continue
                    except Exception:
                        pass
                else:
                    time.sleep(self.config.poll_interval_sec)

                now = time.time()
                if now - last_fd_resync > 5.0:
                    self._resync_kqueue_descriptors()
                    last_fd_resync = now

                candidates: List[DictationRecord] = []
                for watcher in self.watchers:
                    rec = watcher.get_latest()
                    if rec:
                        candidates.append(rec)

                if candidates:
                    candidates.sort(key=lambda r: r.timestamp, reverse=True)
                    winner = candidates[0]

                    if winner.unique_id != last_copied_id:
                        last_copied_id = winner.unique_id

                        if not self.is_paused():
                            PasteboardManager.set_clipboard(winner.text)

                            if self.config.settle_delay_sec > 0:
                                time.sleep(self.config.settle_delay_sec)

                            for _ in range(self.config.reassert_attempts):
                                PasteboardManager.set_clipboard(winner.text)
                                if self.config.reassert_interval_sec > 0:
                                    time.sleep(self.config.reassert_interval_sec)

                            timestamp_str = datetime.fromtimestamp(winner.timestamp).strftime("%H:%M:%S")
                            preview = (winner.text[:75] + "…") if len(winner.text) > 75 else winner.text
                            print(f"[{timestamp_str}] 🎙️ [{winner.source_name} Synced -> Clipboard]: {preview}", flush=True)

                            if self.config.show_notifications:
                                Notifier.notify(
                                    title="Flow Bridge",
                                    subtitle=f"{winner.source_name} Synced",
                                    message=winner.text
                                )

                            if self._auto_paused_media:
                                self._resume_media_safely()
                        elif self.config.verbose:
                            print(f"[Flow Bridge] Skipped sync because Flow Bridge is paused: {winner.unique_id}")

            except KeyboardInterrupt:
                break
            except Exception as err:
                if self.config.verbose:
                    print(f"[Flow Bridge Warning]: {err}", file=sys.stderr)
                time.sleep(0.5)

        if hasattr(self, "_watched_fds"):
            for fd in self._watched_fds:
                try:
                    os.close(fd)
                except Exception:
                    pass

        MediaController.resume()
        print("[Flow Bridge] Daemon stopped.")
