#!/usr/bin/env python3
"""
Wispr Flow Resilient Clipboard Sync Daemon
- Watches Wispr Flow SQLite database for finalized transcripts.
- Uses native macOS AppKit NSPasteboard (GUI WindowServer level) + pbcopy fallback.
- Overcomes Wispr Flow's race condition by re-asserting the clipboard after Wispr's
  internal auto-paste/restore cycle finishes.
- Modular, configurable, clean.
"""

import os
import sys
import time
import sqlite3
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class Config:
    db_path: str = os.path.expanduser("~/Library/Application Support/Wispr Flow/flow.sqlite")
    poll_interval_sec: float = 0.25
    # Delay after detecting new transcript to let Wispr Flow finish its own simulated
    # paste and restore routine, then lock the text onto the clipboard
    wispr_settle_delay_sec: float = 0.35
    # Number of re-assertions to ensure clipboard stays held
    reassert_attempts: int = 3
    reassert_interval_sec: float = 0.15

class PasteboardManager:
    """Manages writing directly to the macOS GUI pasteboard."""

    @staticmethod
    def set_clipboard(text: str) -> bool:
        """Sets clipboard using native macOS AppKit generalPasteboard, falls back to pbcopy."""
        # 1. Primary: Native AppKit NSPasteboard via AppleScript bridge
        # This binds directly to the active GUI session pasteboard
        try:
            # Escape backslashes and double quotes for AppleScript
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

        # 2. Fallback: pbcopy
        try:
            p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE, close_fds=True)
            p.communicate(input=text.encode('utf-8'), timeout=2.0)
            return p.returncode == 0
        except Exception as e:
            print(f"[Error] Failed to set clipboard: {e}", file=sys.stderr)
            return False

class WisprDatabaseWatcher:
    """Watches Wispr Flow SQLite database for new finalized entries."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def fetch_latest_finalized(self) -> Tuple[Optional[str], Optional[str]]:
        if not os.path.exists(self.db_path):
            return None, None

        try:
            uri = f"file:{self.db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT transcriptEntityId, formattedText 
                FROM History 
                WHERE formattedText IS NOT NULL AND length(trim(formattedText)) > 0 
                ORDER BY rowid DESC LIMIT 1;
            """)
            row = cursor.fetchone()
            conn.close()
            if row:
                entity_id, text = row
                if text and text.strip():
                    return entity_id, text.strip()
        except Exception:
            # Handles transient locks while Wispr writes WAL frames
            pass

        return None, None

class ClipboardSyncDaemon:
    def __init__(self, config: Config):
        self.config = config
        self.watcher = WisprDatabaseWatcher(config.db_path)
        self.pb = PasteboardManager()

    def run(self):
        print("=" * 60)
        print("🚀 Wispr Flow Native Clipboard Sync Daemon Active")
        print(f"Monitoring DB: {self.config.db_path}")
        print("Mode: Silent, Race-Condition Resilient (AppKit NSPasteboard)")
        print("=" * 60)

        # Initialize with current latest ID so old transcripts aren't re-copied on startup
        last_seen_id, _ = self.watcher.fetch_latest_finalized()

        while True:
            try:
                curr_id, text = self.watcher.fetch_latest_finalized()
                if curr_id and curr_id != last_seen_id:
                    last_seen_id = curr_id

                    # 1. Immediate initial copy
                    self.pb.set_clipboard(text)

                    # 2. Settle delay: let Wispr Flow finish its own simulated paste and restore attempt
                    time.sleep(self.config.wispr_settle_delay_sec)

                    # 3. Re-assert clipboard so Wispr's clipboard restoration does NOT overwrite it
                    for _ in range(self.config.reassert_attempts):
                        self.pb.set_clipboard(text)
                        time.sleep(self.config.reassert_interval_sec)

                    print(f"[Synced & Held to Clipboard]: {text}")

                time.sleep(self.config.poll_interval_sec)
            except KeyboardInterrupt:
                print("\nDaemon stopped.")
                break
            except Exception as e:
                time.sleep(0.5)

if __name__ == '__main__':
    daemon = ClipboardSyncDaemon(Config())
    daemon.run()
