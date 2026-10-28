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
from flow_bridge_core.storage import DictationStorage
from flow_bridge_core.watchers.engines import BaseDictationWatcher, DettaWatcher, GeminiWatcher, HandyWatcher, WisprFlowWatcher


class FlowBridgeDaemon:
    """Core daemon managing multi-app dictation polling and settle-and-hold clipboard sync."""

    def __init__(self, config: DaemonConfig):
        self.config = config
        self.version = CURRENT_VERSION
        self.storage = DictationStorage(config.dictations_db)
        self.gemini_watcher = GeminiWatcher(config.dictations_db, storage=self.storage)
        self.watchers: List[BaseDictationWatcher] = [
            WisprFlowWatcher(config.wispr_db),
            DettaWatcher(config.detta_db),
            HandyWatcher(config.handy_db),
            self.gemini_watcher,
        ]
        self._running = True
        self._paused = False
        self._cached_update_info: Optional[dict] = None
        self._last_update_check: float = 0.0
        self._last_self_copied_text: str = ""
        self._last_ptt_release: float = 0.0

        # Audio/Video pause state
        self._auto_paused_media = False
        self._server = None
        self._kq = None
        self._watched_fds: Dict[int, str] = {}
        self._lock_file = None

    def stop(self) -> None:
        """Signals the daemon loop to terminate cleanly."""
        self._running = False

    def _start_ptt_listener(self) -> None:
        """Monitors push-to-talk shortcut key hold state and pasteboard changes in a single unified loop.
        Instantly mutes macOS hardware audio output for the duration of speech and captures Gemini
        dictation output with minimal CPU wakeups (~0.0% idle CPU).
        """
        def unified_fast_loop():
            was_held = False
            last_held_app: Optional[str] = None
            held_start_time: float = 0.0
            last_change_count = PasteboardManager.get_change_count()
            last_recorded_text = ""

            while self._running:
                try:
                    # 1. Check push-to-talk shortcut key hold state
                    held_app = ShortcutWatcher.which_app_shortcut_held()
                    now = time.time()

                    if held_app and not was_held:
                        was_held = True
                        last_held_app = held_app
                        held_start_time = now
                        if self.config.auto_pause_media and not self.is_paused():
                            self._auto_paused_media = True
                            MediaController.pause()
                        if self.config.verbose:
                            print(f"[Flow Bridge] 🎙️ {held_app} shortcut held.")
                    elif held_app and was_held:
                        # Failsafe watchdog: If shortcut has been continuously held for >15s,
                        # force-unmute audio to prevent indefinite silence from lost keyup events
                        if (now - held_start_time) > 15.0 and self._auto_paused_media:
                            self._resume_media_safely()
                    elif not held_app and was_held:
                        # Double-check: ensure the key is truly released before clearing state
                        was_held = False
                        self._last_ptt_release = now
                        self._resume_media_safely()
                        if self.config.verbose:
                            print(f"[Flow Bridge] ▶️ {last_held_app} shortcut released.")

                    # 2. Check macOS pasteboard change count (0.01ms integer read)
                    curr_count = PasteboardManager.get_change_count()
                    if curr_count != last_change_count:
                        last_change_count = curr_count
                        clip_text = PasteboardManager.get_clipboard().strip()

                        if clip_text and clip_text != self._last_self_copied_text and clip_text != last_recorded_text:
                            gemini_available = self.gemini_watcher.is_available()
                            front = PasteboardManager.get_frontmost_app()
                            front_name = front.get("name", "").lower()
                            front_bid = front.get("bundle_id", "").lower()

                            is_gemini_front = ("gemini" in front_name) or ("gemini" in front_bid)
                            was_ptt_recent = (now - self._last_ptt_release) < 15.0

                            should_capture = gemini_available and (is_gemini_front or was_ptt_recent or len(clip_text) > 3)

                            if should_capture:
                                is_noise = (
                                    clip_text.startswith(("/", "http://", "https://", "file://", "git@")) or
                                    "\n" in clip_text and len(clip_text.splitlines()) > 5
                                )
                                if not is_noise:
                                    latest = self.storage.get_latest()
                                    if not latest or latest.get("text", "").strip() != clip_text:
                                        rec = self.gemini_watcher.record_dictation(clip_text, source="Gemini")
                                        if rec:
                                            last_recorded_text = clip_text
                                            self._last_self_copied_text = clip_text
                                            ts_str = datetime.fromtimestamp(rec.timestamp).strftime("%H:%M:%S")
                                            preview = (clip_text[:75] + "…") if len(clip_text) > 75 else clip_text
                                            print(f"[{ts_str}] 🎙️ [Gemini Synced -> Storage]: {preview}", flush=True)

                                            if self.config.show_notifications:
                                                Notifier.notify(
                                                    title="Flow Bridge",
                                                    subtitle="Gemini Dictation Synced",
                                                    message=clip_text
                                                )
                                            if self._auto_paused_media:
                                                self._resume_media_safely()
                except Exception as e:
                    if self.config.verbose:
                        print(f"[Flow Bridge] Listener warning: {e}", file=sys.stderr)

                # Adaptive sleep: 40ms when PTT is actively held or recently released, 80ms when completely idle
                if was_held or (time.time() - self._last_ptt_release) < 3.0:
                    time.sleep(0.04)
                else:
                    time.sleep(0.08)

        t = threading.Thread(target=unified_fast_loop, daemon=True)
        t.start()

    def _start_gemini_clipboard_listener(self) -> None:
        """Merged into _start_ptt_listener unified loop to eliminate redundant thread wakeups."""
        pass

    def _sync_external_watchers_to_storage(self) -> None:
        """Startup sync of existing dictation records from external engines into local storage."""
        for watcher in self.watchers:
            if watcher.source_name != "Gemini" and watcher.is_available():
                try:
                    records = watcher.get_history(limit=2000)
                    if records:
                        saved = self.storage.save_batch(records)
                        if self.config.verbose and saved > 0:
                            print(f"[Flow Bridge] Synced {saved} records from {watcher.source_name} to local storage.")
                except Exception as e:
                    if self.config.verbose:
                        print(f"[Flow Bridge] Sync warning for {watcher.source_name}: {e}")

        # Also migrate from legacy history.sqlite if it exists
        legacy_db = self.config.flow_bridge_db
        if os.path.exists(legacy_db):
            try:
                import sqlite3
                with sqlite3.connect(legacy_db, timeout=2.0) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT unique_id, source, timestamp, text FROM dictation_history")
                    legacy_records = [
                        DictationRecord(source_name=r[1], unique_id=r[0], timestamp=float(r[2]), text=r[3])
                        for r in cur.fetchall()
                    ]
                    if legacy_records:
                        self.storage.save_batch(legacy_records)
            except Exception:
                pass

    def _resume_media_safely(self) -> None:
        self._auto_paused_media = False
        MediaController.resume(force=True)
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
                
                # Sync new version files directly into ~/.flow-bridge
                APP_RES="/Applications/FlowBridge.app/Contents/Resources"
                TARGET_DIR="$HOME/.flow-bridge"
                if [ -d "$APP_RES" ]; then
                    cp -R "$APP_RES/flow_bridge_core" "$TARGET_DIR/" 2>/dev/null || true
                    cp -R "$APP_RES/ui" "$TARGET_DIR/" 2>/dev/null || true
                    cp -f "$APP_RES/flow_bridge.py" "$TARGET_DIR/" 2>/dev/null || true
                    chmod +x "$TARGET_DIR/flow_bridge.py" 2>/dev/null || true
                fi
                
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
        """Returns detection status and record count of all registered dictation engines."""
        return [
            {
                "name": w.source_name,
                "available": w.is_available(),
                "path": w.db_path,
                "count": self.storage.get_count(w.source_name)
            }
            for w in self.watchers
        ]

    def get_analytics_stats(self) -> dict:
        """Calculates total dictations, words spoken, and estimated typing hours saved from local storage."""
        return self.storage.get_stats()

    def get_paginated_history(self, limit: int = 50, offset: int = 0, engine: str = "", query: str = "") -> dict:
        """Returns paginated, searchable history across all or specific engines from local storage."""
        return self.storage.get_paginated(limit=limit, offset=offset, query=query, engine=engine)

    def get_recent_history(self, limit: int = 10) -> List[dict]:
        """Combines and returns the latest N dictations across all engines from local storage."""
        return self.storage.get_recent(limit=limit)

    def delete_dictation(self, unique_id: str) -> bool:
        """Deletes a single dictation by unique ID."""
        return self.storage.delete_by_id(unique_id)

    def delete_dictations_range(self, range_type: str, engine: str = "") -> int:
        """Deletes dictations matching a time-range filter."""
        return self.storage.delete_range(range_type=range_type, engine=engine)

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
        self._sync_external_watchers_to_storage()
        self._server = start_ui_server(self)
        self._start_ptt_listener()
        self._start_gemini_clipboard_listener()
        self._setup_kqueue_watchers()
        self.print_status()

        last_copied_id: Optional[str] = None
        newest_startup_ts: float = 0.0

        latest = self.storage.get_latest()
        if latest:
            newest_startup_ts = latest["timestamp"]
            last_copied_id = latest["id"]
            self._last_self_copied_text = latest["text"]

        if last_copied_id and self.config.verbose:
            print(f"[Flow Bridge] Initialized baseline record from storage: {last_copied_id}")

        last_fd_resync = time.time()

        while self._running:
            try:
                should_query = True
                if self._kq and len(self._watched_fds) > 0:
                    try:
                        events = self._kq.control(None, 8, 5.0)
                        if events:
                            time.sleep(0.04)
                        else:
                            # Timeout (5s) elapsed without any database/WAL modification
                            should_query = False
                    except InterruptedError:
                        continue
                    except Exception:
                        pass
                else:
                    time.sleep(self.config.poll_interval_sec)

                now = time.time()
                if now - last_fd_resync > 15.0:
                    self._resync_kqueue_descriptors()
                    last_fd_resync = now

                if not should_query:
                    continue

                candidates: List[DictationRecord] = []
                for watcher in self.watchers:
                    if watcher.source_name != "Gemini":
                        rec = watcher.get_latest()
                        if rec:
                            candidates.append(rec)

                if candidates:
                    candidates.sort(key=lambda r: r.timestamp, reverse=True)
                    winner = candidates[0]

                    if winner.unique_id != last_copied_id:
                        last_copied_id = winner.unique_id
                        self.storage.save_dictation(winner)
                        self._last_self_copied_text = winner.text

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
