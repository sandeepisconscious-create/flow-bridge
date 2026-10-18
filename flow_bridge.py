#!/usr/bin/env python3
"""
Flow Bridge: Universal Voice Dictation Clipboard Sync Daemon
- Concurrently monitors Wispr Flow, Detta, and extensible local voice dictation databases.
- Auto-detects newly transcribed speech across voice apps with millisecond timestamps.
- Instantly places the latest dictation onto the macOS GUI session clipboard (NSPasteboard).
- Employs anti-race settle & hold protection so neither app's internal cleanup / simulated paste can overwrite or discard your transcript.
- Supports native macOS notifications, custom poll intervals, launchd service generation, and CLI diagnostics.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import fcntl
import json
import os
import select
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Set, Tuple

CURRENT_VERSION = "1.0.9"
GITHUB_REPO = "sandeepisconscious-create/flow-bridge"

LOCK_FILE_PATH = os.path.expanduser("~/.flow_bridge.lock")


@dataclass(frozen=True)
class DictationRecord:
    source_name: str
    unique_id: str
    timestamp: float
    text: str


@dataclass
class DaemonConfig:
    wispr_db: str = os.path.expanduser("~/Library/Application Support/Wispr Flow/flow.sqlite")
    detta_db: str = os.path.expanduser("~/Library/Application Support/Detta/history.db")
    handy_db: str = os.path.expanduser("~/Library/Application Support/com.pais.handy/history.db")
    poll_interval_sec: float = 0.25
    settle_delay_sec: float = 0.35
    reassert_attempts: int = 3
    reassert_interval_sec: float = 0.15
    show_notifications: bool = False
    verbose: bool = False


class PasteboardManager:
    """Manages the macOS system clipboard with in-process native AppKit NSPasteboard (0.1ms) and CLI fallbacks."""

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


class BaseDictationWatcher(ABC):
    """Abstract base class for voice dictation database watchers."""

    def __init__(self, db_path: str, source_name: str):
        self.db_path = db_path
        self.source_name = source_name
        self._conn: Optional[sqlite3.Connection] = None

    def is_available(self) -> bool:
        return os.path.exists(self.db_path)

    def _get_connection(self) -> Optional[sqlite3.Connection]:
        if not self.is_available():
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
            return None

        if self._conn is None:
            try:
                self._conn = sqlite3.connect(
                    f"file:{self.db_path}?mode=ro",
                    uri=True,
                    timeout=0.5,
                    check_same_thread=False
                )
                self._conn.execute("PRAGMA query_only = ON;")
                self._conn.execute("PRAGMA synchronous = OFF;")
            except Exception:
                self._conn = None
        return self._conn

    @abstractmethod
    def get_latest(self) -> Optional[DictationRecord]:
        """Fetches the most recent non-empty transcript entry."""
        pass

    @abstractmethod
    def get_history(self, limit: int = 10) -> List[DictationRecord]:
        """Fetches the latest N transcript entries."""
        pass


class WisprFlowWatcher(BaseDictationWatcher):
    """Watches Wispr Flow's SQLite history database."""

    def __init__(self, db_path: str):
        super().__init__(db_path, "Wispr Flow")

    def get_latest(self) -> Optional[DictationRecord]:
        history = self.get_history(limit=1)
        return history[0] if history else None

    def get_history(self, limit: int = 10) -> List[DictationRecord]:
        conn = self._get_connection()
        if not conn:
            return []
        records: List[DictationRecord] = []
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT transcriptEntityId, timestamp, formattedText 
                FROM History 
                WHERE formattedText IS NOT NULL AND length(trim(formattedText)) > 0 
                ORDER BY rowid DESC LIMIT {limit};
            """)
            rows = cursor.fetchall()
            for row in rows:
                entity_id, ts_str, text = row
                if not text or not text.strip():
                    continue
                try:
                    clean_ts = ts_str.split("+")[0].strip()
                    dt = datetime.fromisoformat(clean_ts).replace(tzinfo=timezone.utc)
                    unix_ts = dt.timestamp()
                except Exception:
                    unix_ts = time.time()

                records.append(DictationRecord(
                    source_name=self.source_name,
                    unique_id=f"wispr_{entity_id}",
                    timestamp=unix_ts,
                    text=text.strip()
                ))
        except Exception:
            # Reconnect on next attempt in case WAL journal was reset
            self._conn = None
        return records


class DettaWatcher(BaseDictationWatcher):
    """Watches Detta's SQLite history database."""

    def __init__(self, db_path: str):
        super().__init__(db_path, "Detta")

    def get_latest(self) -> Optional[DictationRecord]:
        history = self.get_history(limit=1)
        return history[0] if history else None

    def get_history(self, limit: int = 10) -> List[DictationRecord]:
        conn = self._get_connection()
        if not conn:
            return []
        records: List[DictationRecord] = []
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, ts, text 
                FROM entries 
                WHERE text IS NOT NULL AND length(trim(text)) > 0 
                ORDER BY id DESC LIMIT {limit};
            """)
            rows = cursor.fetchall()
            for row in rows:
                entry_id, unix_ts, text = row
                if not text or not text.strip():
                    continue
                records.append(DictationRecord(
                    source_name=self.source_name,
                    unique_id=f"detta_{entry_id}",
                    timestamp=float(unix_ts),
                    text=text.strip()
                ))
        except Exception:
            self._conn = None
        return records


class HandyWatcher(BaseDictationWatcher):
    """Watches Handy's SQLite transcription database (com.pais.handy)."""

    def __init__(self, db_path: str):
        super().__init__(db_path, "Handy")

    def get_latest(self) -> Optional[DictationRecord]:
        history = self.get_history(limit=1)
        return history[0] if history else None

    def get_history(self, limit: int = 10) -> List[DictationRecord]:
        conn = self._get_connection()
        if not conn:
            return []
        records: List[DictationRecord] = []
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, timestamp, transcription_text, post_processed_text 
                FROM transcription_history 
                WHERE (transcription_text IS NOT NULL AND length(trim(transcription_text)) > 0)
                   OR (post_processed_text IS NOT NULL AND length(trim(post_processed_text)) > 0)
                ORDER BY id DESC LIMIT {limit};
            """)
            rows = cursor.fetchall()
            for row in rows:
                entry_id, raw_ts, trans_text, post_text = row
                text = post_text.strip() if post_text and post_text.strip() else (trans_text.strip() if trans_text else "")
                if not text:
                    continue

                # Handy timestamp is standard epoch (seconds or ms)
                ts_val = float(raw_ts)
                unix_ts = ts_val / 1000.0 if ts_val > 1e11 else ts_val

                records.append(DictationRecord(
                    source_name=self.source_name,
                    unique_id=f"handy_{entry_id}",
                    timestamp=unix_ts,
                    text=text
                ))
        except Exception:
            self._conn = None
        return records


class FlowBridgeDaemon:
    """Core daemon managing multi-app dictation polling and settle-and-hold clipboard sync."""

    def __init__(self, config: DaemonConfig):
        self.config = config
        self.watchers: List[BaseDictationWatcher] = [
            WisprFlowWatcher(config.wispr_db),
            DettaWatcher(config.detta_db),
            HandyWatcher(config.handy_db),
        ]
        self._running = True
        self._paused = False
        self._cached_update_info: Optional[dict] = None
        self._last_update_check: float = 0.0

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
        # Cache results for 10 minutes unless forced
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
                            # Compare semantic versions
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
        except Exception as e:
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

            # Mount DMG, copy app to /Applications, unmount
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

        return [
            {
                "id": r.unique_id,
                "source": r.source_name,
                "text": r.text,
                "timestamp": r.timestamp,
                "time": datetime.fromtimestamp(r.timestamp).strftime("%I:%M:%S %p")
            }
            for r in top
        ]

    def _start_ui_server(self, port: int = 49231) -> None:
        """Starts a lightweight local HTTP server for the shadcn dashboard UI."""
        daemon_self = self
        ui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")

        class UIHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Keep terminal output completely silent and clean

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    html_file = os.path.join(ui_dir, "index.html")
                    if os.path.exists(html_file):
                        with open(html_file, "rb") as f:
                            content = f.read()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(content)
                        return
                elif self.path in ("/assets/logo.png", "/logo.png", "/favicon.ico", "/favicon.png", "/apple-touch-icon.png"):
                    target_file = logo_path
                    if self.path in ("/favicon.ico", "/favicon.png"):
                        fav = os.path.join(ui_dir, "favicon.png")
                        if os.path.exists(fav):
                            target_file = fav
                    if os.path.exists(target_file):
                        with open(target_file, "rb") as f:
                            content = f.read()
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        self.wfile.write(content)
                        return
                elif self.path == "/api/state":
                    data = {
                        "version": CURRENT_VERSION,
                        "paused": daemon_self.is_paused(),
                        "apps": daemon_self.get_app_status(),
                        "history": daemon_self.get_recent_history(limit=25),
                        "update": daemon_self.check_for_update()
                    }
                    body = json.dumps(data).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                elif self.path == "/api/toggle-pause":
                    new_state = daemon_self.set_paused(not daemon_self.is_paused())
                    body = json.dumps({"paused": new_state}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                elif self.path == "/api/check-update":
                    info = daemon_self.check_for_update(force=True)
                    body = json.dumps(info).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                elif self.path == "/api/auto-update":
                    res = daemon_self.perform_auto_update()
                    body = json.dumps(res).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                    return

                self.send_response(404)
                self.end_headers()

        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), UIHandler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            if self.config.verbose:
                print(f"[Flow Bridge] Dashboard UI running at http://127.0.0.1:{port}")
        except Exception:
            pass

    def _acquire_single_instance_lock(self) -> None:
        """Ensures only a single instance of Flow Bridge runs at any given time."""
        try:
            self._lock_file = open(LOCK_FILE_PATH, "a+")
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.seek(0)
            self._lock_file.truncate()
            self._lock_file.write(f"{os.getpid()}\n")
            self._lock_file.flush()
        except (IOError, BlockingIOError):
            # Another instance is already running; read its PID
            try:
                with open(LOCK_FILE_PATH, "r") as f:
                    old_pid = int(f.read().strip())
                if old_pid != os.getpid():
                    print(f"[Flow Bridge] Replacing existing instance (PID: {old_pid})...")
                    os.kill(old_pid, signal.SIGTERM)
                    time.sleep(0.4)
                    # Retry acquiring lock
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
            self._watched_fds: Dict[int, str] = {}
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

        # Close and clear stale descriptors
        for fd, path in list(self._watched_fds.items()):
            if path not in current_paths:
                try:
                    os.close(fd)
                except Exception:
                    pass
                del self._watched_fds[fd]

        # Register new descriptors
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
        self._start_ui_server()
        self._setup_kqueue_watchers()
        self.print_status()

        # Seed initial state with existing records so historical entries are not copied at startup
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
                # 1. Low-latency / zero-CPU event wait: Sleep until macOS kernel fires VNODE write event
                if self._kq and len(self._watched_fds) > 0:
                    # Deep-sleep in kernel until transaction commit, or fallback wake after 0.5s
                    try:
                        events = self._kq.control(None, 8, 0.5)
                    except InterruptedError:
                        continue
                    except Exception:
                        events = []
                else:
                    time.sleep(self.config.poll_interval_sec)

                # Periodic descriptor refresh (in case an app created a new WAL file or directory)
                now = time.time()
                if now - last_fd_resync > 5.0:
                    self._resync_kqueue_descriptors()
                    last_fd_resync = now

                # 2. Check latest records across active watchers
                candidates: List[DictationRecord] = []
                for watcher in self.watchers:
                    rec = watcher.get_latest()
                    if rec:
                        candidates.append(rec)

                if candidates:
                    # Sort descending so the most recent voice utterance wins
                    candidates.sort(key=lambda r: r.timestamp, reverse=True)
                    winner = candidates[0]

                    if winner.unique_id != last_copied_id:
                        last_copied_id = winner.unique_id

                        if not self.is_paused():
                            # 1. Immediate primary clipboard sync (~0.1ms via native ctypes NSPasteboard)
                            PasteboardManager.set_clipboard(winner.text)

                            # 2. Wait out target app's internal synthetic paste and cleanup routine
                            if self.config.settle_delay_sec > 0:
                                time.sleep(self.config.settle_delay_sec)

                            # 3. Anti-race-condition settle & hold: Re-assert clipboard
                            for _ in range(self.config.reassert_attempts):
                                PasteboardManager.set_clipboard(winner.text)
                                if self.config.reassert_interval_sec > 0:
                                    time.sleep(self.config.reassert_interval_sec)

                            # Log sync event
                            timestamp_str = datetime.fromtimestamp(winner.timestamp).strftime("%H:%M:%S")
                            preview = (winner.text[:75] + "…") if len(winner.text) > 75 else winner.text
                            print(f"[{timestamp_str}] 🎙️ [{winner.source_name} Synced -> Clipboard]: {preview}", flush=True)

                            if self.config.show_notifications:
                                Notifier.notify(
                                    title="Flow Bridge",
                                    subtitle=f"{winner.source_name} Synced",
                                    message=winner.text
                                )
                        elif self.config.verbose:
                            print(f"[Flow Bridge] Skipped sync because Flow Bridge is paused: {winner.unique_id}")

            except KeyboardInterrupt:
                break
            except Exception as err:
                if self.config.verbose:
                    print(f"[Flow Bridge Warning]: {err}", file=sys.stderr)
                time.sleep(0.5)

        # Cleanup kqueue descriptors
        if hasattr(self, "_watched_fds"):
            for fd in self._watched_fds:
                try:
                    os.close(fd)
                except Exception:
                    pass
        print("[Flow Bridge] Daemon stopped.")


def generate_launchd_plist() -> str:
    """Generates a macOS launchd user agent plist for running Flow Bridge on login."""
    script_path = os.path.abspath(__file__)
    python_path = sys.executable
    home = os.path.expanduser("~")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.flowbridge.clipboard.sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{home}/Library/Logs/flow_bridge.log</string>
    <key>StandardErrorPath</key>
    <string>{home}/Library/Logs/flow_bridge_error.log</string>
    <key>WorkingDirectory</key>
    <string>{os.path.dirname(script_path)}</string>
</dict>
</plist>
"""


def install_service() -> None:
    """Installs and starts the launchd agent."""
    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    plist_path = os.path.join(plist_dir, "com.flowbridge.clipboard.sync.plist")
    os.makedirs(plist_dir, exist_ok=True)

    content = generate_launchd_plist()
    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(content)

    subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
    res = subprocess.run(["launchctl", "load", plist_path], capture_output=True, text=True)
    if res.returncode == 0:
        print(f"✅ Successfully installed and loaded Flow Bridge launchd agent:")
        print(f"   {plist_path}")
        print("   It will now automatically run silently in the background on startup.")
    else:
        print(f"⚠️ Installed plist to {plist_path}, but launchctl load returned: {res.stderr}")


def uninstall_service() -> None:
    """Unloads and removes the launchd agent."""
    plist_path = os.path.expanduser("~/Library/LaunchAgents/com.flowbridge.clipboard.sync.plist")
    if os.path.exists(plist_path):
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        os.remove(plist_path)
        print("✅ Successfully uninstalled Flow Bridge launchd agent.")
    else:
        print("ℹ️ No installed launchd agent found.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flow Bridge: Universal Voice Dictation Clipboard Sync Daemon",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--poll", type=float, default=0.25, help="Poll interval in seconds")
    parser.add_argument("--settle", type=float, default=0.35, help="Settle delay before re-assertion")
    parser.add_argument("--reassert", type=int, default=3, help="Number of re-assert attempts")
    parser.add_argument("--notify", action="store_true", help="Display native macOS notification on sync")
    parser.add_argument("--verbose", action="store_true", help="Print verbose debug logs")
    parser.add_argument("--install-service", action="store_true", help="Install as macOS background launchd service (runs on boot)")
    parser.add_argument("--uninstall-service", action="store_true", help="Uninstall macOS background launchd service")
    parser.add_argument("--test-clipboard", action="store_true", help="Test setting clipboard and exit")
    parser.add_argument("--dashboard", action="store_true", help="Open Flow Bridge shadcn/ui dashboard")

    args = parser.parse_args()

    if args.dashboard:
        # Start server if not running, then open dashboard
        subprocess.run(["open", "http://127.0.0.1:49231"])
        return

    if args.install_service:
        install_service()
        return

    if args.uninstall_service:
        uninstall_service()
        return

    if args.test_clipboard:
        test_str = "Flow Bridge Clipboard Test OK"
        success = PasteboardManager.set_clipboard(test_str)
        curr = PasteboardManager.get_clipboard()
        print(f"Set clipboard result: {success}, Current pasteboard content: '{curr}'")
        return

    config = DaemonConfig(
        poll_interval_sec=args.poll,
        settle_delay_sec=args.settle,
        reassert_attempts=args.reassert,
        show_notifications=args.notify,
        verbose=args.verbose
    )

    daemon = FlowBridgeDaemon(config)
    daemon.run()


if __name__ == "__main__":
    main()
