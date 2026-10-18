#!/usr/bin/env python3
"""
Flow Bridge: Unified Dictation Clipboard Sync Daemon
- Concurrently monitors BOTH Wispr Flow and Detta dictation databases.
- Compares timestamps in real time so whichever voice app you speak into last
  is instantly placed onto your macOS GUI session clipboard.
- Anti-race-condition settle & hold (NSPasteboard) so neither app's internal
  cleanup can overwrite your speech.
- 100% silent, modular, and auto-detecting.
"""

import os
import sys
import time
import sqlite3
import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class Config:
    wispr_db: str = os.path.expanduser("~/Library/Application Support/Wispr Flow/flow.sqlite")
    detta_db: str = os.path.expanduser("~/Library/Application Support/Detta/history.db")
    poll_interval_sec: float = 0.25
    settle_delay_sec: float = 0.35
    reassert_attempts: int = 3
    reassert_interval_sec: float = 0.15

class PasteboardManager:
    @staticmethod
    def set_clipboard(text: str) -> bool:
        """Sets clipboard using native macOS AppKit generalPasteboard, with pbcopy fallback."""
        try:
            escaped_text = text.replace('\\', '\\\\').replace('"', '\\"')
            script = f'''
            use framework "AppKit"
            set pb to current application's NSPasteboard's generalPasteboard()
            pb's clearContents()
            pb's setString:"{escaped_text}" forType:(current application's NSPasteboardTypeString)
            '''
            res = subprocess.run(['osascript', '-l', 'AppleScript', '-e', script], capture_output=True, timeout=2.0)
            if res.returncode == 0:
                return True
        except Exception:
            pass

        try:
            p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE, close_fds=True)
            p.communicate(input=text.encode('utf-8'), timeout=2.0)
            return p.returncode == 0
        except Exception as e:
            print(f"[Error] Failed to set clipboard: {e}", file=sys.stderr)
            return False

class WisprWatcher:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_latest(self) -> Tuple[Optional[str], Optional[float], Optional[str]]:
        """Returns (entity_id, unix_timestamp, text)"""
        if not os.path.exists(self.db_path):
            return None, None, None
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=1.0)
            c = conn.cursor()
            c.execute("""
                SELECT transcriptEntityId, timestamp, formattedText 
                FROM History 
                WHERE formattedText IS NOT NULL AND length(trim(formattedText)) > 0 
                ORDER BY rowid DESC LIMIT 1;
            """)
            row = c.fetchone()
            conn.close()
            if row:
                entity_id, ts_str, text = row
                if text and text.strip():
                    # Parse timestamp format like: '2026-10-18 05:08:10.924 +00:00'
                    try:
                        clean_ts = ts_str.split('+')[0].strip()
                        dt = datetime.fromisoformat(clean_ts).replace(tzinfo=timezone.utc)
                        unix_ts = dt.timestamp()
                    except Exception:
                        unix_ts = time.time()
                    return f"wispr_{entity_id}", unix_ts, text.strip()
        except Exception:
            pass
        return None, None, None

class DettaWatcher:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_latest(self) -> Tuple[Optional[str], Optional[float], Optional[str]]:
        """Returns (entry_id, unix_timestamp, text)"""
        if not os.path.exists(self.db_path):
            return None, None, None
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=1.0)
            c = conn.cursor()
            c.execute("""
                SELECT id, ts, text 
                FROM entries 
                WHERE text IS NOT NULL AND length(trim(text)) > 0 
                ORDER BY id DESC LIMIT 1;
            """)
            row = c.fetchone()
            conn.close()
            if row:
                entry_id, unix_ts, text = row
                if text and text.strip():
                    return f"detta_{entry_id}", float(unix_ts), text.strip()
        except Exception:
            pass
        return None, None, None

class UnifiedVoiceDaemon:
    def __init__(self, config: Config):
        self.config = config
        self.wispr = WisprWatcher(config.wispr_db)
        self.detta = DettaWatcher(config.detta_db)
        self.pb = PasteboardManager()

    def run(self):
        print("=" * 60)
        print("🎙️ Flow Bridge: Dual Dictation Hub Active")
        print(f"• Wispr Flow Watcher: {'Active' if os.path.exists(self.config.wispr_db) else 'Not Found'}")
        print(f"• Detta Watcher:      {'Active' if os.path.exists(self.config.detta_db) else 'Not Found'}")
        print("• Destination: macOS Native GUI Pasteboard (NSPasteboard)")
        print("=" * 60)

        # Initialize baseline state so existing old entries aren't copied at boot
        w_id, w_ts, _ = self.wispr.get_latest()
        d_id, d_ts, _ = self.detta.get_latest()

        last_copied_id = None
        if w_ts and d_ts:
            last_copied_id = w_id if w_ts >= d_ts else d_id
        elif w_ts:
            last_copied_id = w_id
        elif d_ts:
            last_copied_id = d_id

        while True:
            try:
                candidates = []

                w_id, w_ts, w_text = self.wispr.get_latest()
                if w_id and w_ts and w_text:
                    candidates.append((w_id, w_ts, w_text, "Wispr Flow"))

                d_id, d_ts, d_text = self.detta.get_latest()
                if d_id and d_ts and d_text:
                    candidates.append((d_id, d_ts, d_text, "Detta"))

                if candidates:
                    # Pick whichever candidate has the most recent timestamp
                    candidates.sort(key=lambda x: x[1], reverse=True)
                    newest_id, newest_ts, newest_text, app_source = candidates[0]

                    if newest_id != last_copied_id:
                        last_copied_id = newest_id

                        # 1. Immediate copy to macOS pasteboard
                        self.pb.set_clipboard(newest_text)

                        # 2. Wait for target app to finish internal paste simulation/cleanup
                        time.sleep(self.config.settle_delay_sec)

                        # 3. Re-assert and hold so the clipboard cannot be overridden
                        for _ in range(self.config.reassert_attempts):
                            self.pb.set_clipboard(newest_text)
                            time.sleep(self.config.reassert_interval_sec)

                        print(f"[{app_source} Synced]: {newest_text}")

                time.sleep(self.config.poll_interval_sec)
            except KeyboardInterrupt:
                print("\nDaemon stopped.")
                break
            except Exception as e:
                time.sleep(0.5)

if __name__ == '__main__':
    daemon = UnifiedVoiceDaemon(Config())
    daemon.run()
