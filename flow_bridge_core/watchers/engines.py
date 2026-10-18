"""
Dictation Database Watchers for Wispr Flow, Handy, and Detta.
"""

from __future__ import annotations

import os
import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from flow_bridge_core.models import DictationRecord


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
