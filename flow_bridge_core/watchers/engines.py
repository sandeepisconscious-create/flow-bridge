"""
Dictation Database Watchers for Wispr Flow, Google Gemini, Handy, and Detta.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from flow_bridge_core.models import DictationRecord


class BaseDictationWatcher(ABC):
    """Abstract base class for voice dictation database watchers with robust, ephemeral read-only connections."""

    def __init__(self, db_path: str, source_name: str):
        self.db_path = db_path
        self.source_name = source_name

    def is_available(self) -> bool:
        return os.path.exists(self.db_path)

    def _connect_ro(self) -> Optional[sqlite3.Connection]:
        if not self.is_available():
            return None
        try:
            return sqlite3.connect(
                f"file:{self.db_path}?mode=ro",
                uri=True,
                timeout=2.0
            )
        except Exception:
            return None

    @abstractmethod
    def get_latest(self) -> Optional[DictationRecord]:
        """Fetches the most recent non-empty transcript entry."""
        pass

    @abstractmethod
    def get_history(self, limit: int = 10, offset: int = 0, query: str = "") -> List[DictationRecord]:
        """Fetches transcript entries with pagination and optional search query."""
        pass

    def get_count(self) -> int:
        """Returns total number of dictation records stored for this engine."""
        return 0


class WisprFlowWatcher(BaseDictationWatcher):
    """Watches Wispr Flow's SQLite history database."""

    def __init__(self, db_path: str):
        super().__init__(db_path, "Wispr Flow")

    def get_latest(self) -> Optional[DictationRecord]:
        history = self.get_history(limit=1)
        return history[0] if history else None

    def get_count(self) -> int:
        conn = self._connect_ro()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM History WHERE formattedText IS NOT NULL AND length(trim(formattedText)) > 0")
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_history(self, limit: int = 10, offset: int = 0, query: str = "") -> List[DictationRecord]:
        conn = self._connect_ro()
        if not conn:
            return []
        records: List[DictationRecord] = []
        try:
            cursor = conn.cursor()
            sql = """
                SELECT transcriptEntityId, timestamp, formattedText 
                FROM History 
                WHERE formattedText IS NOT NULL AND length(trim(formattedText)) > 0
            """
            params: list = []
            if query:
                sql += " AND formattedText LIKE ?"
                params.append(f"%{query}%")
            sql += " ORDER BY rowid DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(sql, params)
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
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return records


class DettaWatcher(BaseDictationWatcher):
    """Watches Detta's SQLite history database."""

    def __init__(self, db_path: str):
        super().__init__(db_path, "Detta")

    def get_latest(self) -> Optional[DictationRecord]:
        history = self.get_history(limit=1)
        return history[0] if history else None

    def get_count(self) -> int:
        conn = self._connect_ro()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM entries WHERE text IS NOT NULL AND length(trim(text)) > 0")
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_history(self, limit: int = 10, offset: int = 0, query: str = "") -> List[DictationRecord]:
        conn = self._connect_ro()
        if not conn:
            return []
        records: List[DictationRecord] = []
        try:
            cursor = conn.cursor()
            sql = "SELECT id, ts, text FROM entries WHERE text IS NOT NULL AND length(trim(text)) > 0"
            params: list = []
            if query:
                sql += " AND text LIKE ?"
                params.append(f"%{query}%")
            sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(sql, params)
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
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return records


class HandyWatcher(BaseDictationWatcher):
    """Watches Handy's SQLite transcription database (com.pais.handy)."""

    def __init__(self, db_path: str):
        super().__init__(db_path, "Handy")

    def get_latest(self) -> Optional[DictationRecord]:
        history = self.get_history(limit=1)
        return history[0] if history else None

    def get_count(self) -> int:
        conn = self._connect_ro()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT count(*) FROM transcription_history 
                WHERE (transcription_text IS NOT NULL AND length(trim(transcription_text)) > 0)
                   OR (post_processed_text IS NOT NULL AND length(trim(post_processed_text)) > 0)
            """)
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_history(self, limit: int = 10, offset: int = 0, query: str = "") -> List[DictationRecord]:
        conn = self._connect_ro()
        if not conn:
            return []
        records: List[DictationRecord] = []
        try:
            cursor = conn.cursor()
            sql = """
                SELECT id, timestamp, transcription_text, post_processed_text 
                FROM transcription_history 
                WHERE (transcription_text IS NOT NULL AND length(trim(transcription_text)) > 0)
                   OR (post_processed_text IS NOT NULL AND length(trim(post_processed_text)) > 0)
            """
            params: list = []
            if query:
                sql += " AND (transcription_text LIKE ? OR post_processed_text LIKE ?)"
                params.extend([f"%{query}%", f"%{query}%"])
            sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            for row in rows:
                entry_id, raw_ts, trans_text, post_text = row
                text = post_text.strip() if post_text and post_text.strip() else (trans_text.strip() if trans_text else "")
                if not text:
                    continue

                ts_val = float(raw_ts)
                unix_ts = ts_val / 1000.0 if ts_val > 1e11 else ts_val

                records.append(DictationRecord(
                    source_name=self.source_name,
                    unique_id=f"handy_{entry_id}",
                    timestamp=unix_ts,
                    text=text
                ))
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return records


class GeminiWatcher(BaseDictationWatcher):
    """
    Watches Google Gemini macOS app dictations and persists transcripts to Flow Bridge local storage.
    """

    def __init__(self, db_path: str = "", storage=None):
        resolved_db = db_path or os.path.expanduser("~/.flow-bridge/dictations.sqlite")
        super().__init__(resolved_db, "Gemini")
        if storage is not None:
            self.storage = storage
        else:
            from flow_bridge_core.storage import DictationStorage
            self.storage = DictationStorage(resolved_db)

        self._counter: int = 0
        self._last_avail_check: float = 0.0
        self._cached_available: bool = False

    def is_available(self) -> bool:
        """Available if Gemini process is running or has stored records (zero subprocesses)."""
        now = time.time()
        if now - self._last_avail_check < 15.0:
            return self._cached_available
        self._last_avail_check = now
        try:
            if self.storage.get_count("Gemini") > 0:
                self._cached_available = True
                return True

            from flow_bridge_core.platform.pasteboard import PasteboardManager
            running = PasteboardManager.get_running_dictation_apps()
            self._cached_available = ("Gemini" in running)
        except Exception:
            self._cached_available = False
        return self._cached_available

    def record_dictation(self, text: str, source: str = "Gemini") -> Optional[DictationRecord]:
        """Records a finalized text string emitted by Gemini/voice into local storage."""
        clean_text = text.strip() if text else ""
        if not clean_text:
            return None
        self._counter += 1
        ts = time.time()
        uid = f"gemini_{int(ts)}_{self._counter}"
        rec = DictationRecord(
            source_name=source,
            unique_id=uid,
            timestamp=ts,
            text=clean_text
        )
        self.storage.save_dictation(rec)
        return rec

    def get_latest(self) -> Optional[DictationRecord]:
        history = self.get_history(limit=1)
        return history[0] if history else None

    def get_count(self) -> int:
        return self.storage.get_count("Gemini")

    def get_history(self, limit: int = 10, offset: int = 0, query: str = "") -> List[DictationRecord]:
        page = self.storage.get_paginated(limit=limit, offset=offset, query=query, engine="Gemini")
        return [
            DictationRecord(
                source_name=item["source"],
                unique_id=item["id"],
                timestamp=item["timestamp"],
                text=item["text"]
            )
            for item in page.get("items", [])
        ]
