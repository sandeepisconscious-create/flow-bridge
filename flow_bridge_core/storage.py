"""
Unified Local Storage Manager for Flow Bridge.
Permanently stores all dictations across all engines (Gemini, Wispr Flow, Handy, Detta)
in a dedicated, indexed, high-performance SQLite database.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from flow_bridge_core.models import DictationRecord


def format_date_label(timestamp: float) -> str:
    """Returns human-friendly date grouping like Today, Yesterday, or weekday name."""
    now = datetime.now()
    dt = datetime.fromtimestamp(timestamp)
    delta_days = (now.date() - dt.date()).days

    if delta_days == 0:
        return "Today"
    elif delta_days == 1:
        return "Yesterday"
    elif 1 < delta_days <= 6:
        return dt.strftime("%A")
    else:
        return dt.strftime("%B %d, %Y")


def format_time_str(timestamp: float) -> str:
    """Returns formatted 12-hour time string like '3:15pm'."""
    dt = datetime.fromtimestamp(timestamp)
    hour = dt.strftime("%I").lstrip("0") or "12"
    minute_ampm = dt.strftime(":%M%p").lower()
    return f"{hour}{minute_ampm}"


class DictationStorage:
    """
    Manages dedicated Flow Bridge local SQLite storage.
    Guarantees thread-safe connections with re-entrant mutex, fast indexed queries,
    and persistent history preservation independent of third-party apps.
    """

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or os.path.expanduser("~/.flow-bridge/dictations.sqlite")
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite schema, WAL journal mode, and performance indexes."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._lock:
            try:
                with sqlite3.connect(self.db_path, timeout=5.0) as conn:
                    conn.execute("PRAGMA journal_mode = WAL;")
                    conn.execute("PRAGMA synchronous = NORMAL;")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS dictations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            unique_id TEXT UNIQUE NOT NULL,
                            source TEXT NOT NULL,
                            timestamp REAL NOT NULL,
                            time_str TEXT NOT NULL,
                            date_label TEXT NOT NULL,
                            text TEXT NOT NULL,
                            word_count INTEGER NOT NULL,
                            char_count INTEGER NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_dictations_ts ON dictations(timestamp DESC)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_dictations_src_ts ON dictations(source, timestamp DESC)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_dictations_uid ON dictations(unique_id)")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS deleted_dictations (
                            unique_id TEXT PRIMARY KEY,
                            deleted_at REAL NOT NULL
                        )
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_deleted_uid ON deleted_dictations(unique_id)")
                    conn.commit()
            except Exception as e:
                print(f"[Flow Bridge Storage] Schema initialization warning: {e}")

    def _connect(self) -> Optional[sqlite3.Connection]:
        """Opens a fresh connection with timeout."""
        try:
            return sqlite3.connect(self.db_path, timeout=5.0)
        except Exception:
            return None

    def save_dictation(self, record: DictationRecord) -> bool:
        """
        Saves a single dictation record into local storage.
        Uses INSERT OR REPLACE to keep latest timestamp and attributes.
        """
        if not record or not record.text or not record.text.strip():
            return False

        clean_text = record.text.strip()
        words = len(clean_text.split())
        chars = len(clean_text)
        time_str = format_time_str(record.timestamp)
        date_label = format_date_label(record.timestamp)

        with self._lock:
            conn = self._connect()
            if not conn:
                return False
            try:
                with conn:
                    cur = conn.cursor()
                    cur.execute("SELECT 1 FROM deleted_dictations WHERE unique_id = ? LIMIT 1", (record.unique_id,))
                    if cur.fetchone():
                        return False

                    conn.execute("""
                        INSERT OR REPLACE INTO dictations (
                            unique_id, source, timestamp, time_str, date_label, text, word_count, char_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.unique_id,
                        record.source_name,
                        record.timestamp,
                        time_str,
                        date_label,
                        clean_text,
                        words,
                        chars
                    ))
                return True
            except Exception as e:
                print(f"[Flow Bridge Storage] Save error: {e}")
                return False
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def save_batch(self, records: List[DictationRecord]) -> int:
        """
        Bulk inserts historical dictation records with INSERT OR IGNORE.
        Skips any records that have been deleted by the user.
        Returns the number of records successfully written.
        """
        if not records:
            return 0

        rows = []
        for r in records:
            if not r or not r.text or not r.text.strip():
                continue
            clean_text = r.text.strip()
            rows.append((
                r.unique_id,
                r.source_name,
                r.timestamp,
                format_time_str(r.timestamp),
                format_date_label(r.timestamp),
                clean_text,
                len(clean_text.split()),
                len(clean_text)
            ))

        if not rows:
            return 0

        with self._lock:
            conn = self._connect()
            if not conn:
                return 0
            try:
                with conn:
                    cur = conn.cursor()
                    cur.execute("SELECT unique_id FROM deleted_dictations")
                    deleted_set = {r[0] for r in cur.fetchall()}
                    valid_rows = [r for r in rows if r[0] not in deleted_set]
                    if not valid_rows:
                        return 0

                    conn.executemany("""
                        INSERT OR IGNORE INTO dictations (
                            unique_id, source, timestamp, time_str, date_label, text, word_count, char_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, valid_rows)
                return len(valid_rows)
            except Exception as e:
                print(f"[Flow Bridge Storage] Batch save error: {e}")
                return 0
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_latest(self) -> Optional[dict]:
        """Returns the single most recent dictation from storage."""
        history = self.get_recent(limit=1)
        return history[0] if history else None

    def get_recent(self, limit: int = 50) -> List[dict]:
        """Returns the most recent dictations formatted for the UI feed."""
        with self._lock:
            conn = self._connect()
            if not conn:
                return []
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT unique_id, source, timestamp, time_str, date_label, text, word_count, char_count
                    FROM dictations
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                rows = cur.fetchall()
                result = []
                for row in rows:
                    uid, src, ts, time_str, date_label, text, wc, cc = row
                    result.append({
                        "id": str(uid),
                        "source": str(src),
                        "text": str(text),
                        "timestamp": float(ts),
                        "time": str(time_str),
                        "date_label": format_date_label(float(ts)),
                        "word_count": int(wc),
                        "char_count": int(cc)
                    })
                return result
            except Exception as e:
                print(f"[Flow Bridge Storage] get_recent error: {e}")
                return []
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_paginated(self, limit: int = 50, offset: int = 0, query: str = "", engine: str = "") -> dict:
        """Returns paginated, filtered dictation records with total counts."""
        with self._lock:
            conn = self._connect()
            if not conn:
                return {"items": [], "total": 0, "limit": limit, "offset": offset, "has_more": False}

            try:
                cur = conn.cursor()

                where_clauses = []
                params: list = []

                if engine and engine.lower() != "all":
                    where_clauses.append("LOWER(source) = LOWER(?)")
                    params.append(engine)

                if query:
                    where_clauses.append("text LIKE ?")
                    params.append(f"%{query}%")

                where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                cur.execute(f"SELECT count(*) FROM dictations {where_sql}", params)
                total = cur.fetchone()[0]

                query_params = list(params) + [limit, offset]
                cur.execute(f"""
                    SELECT unique_id, source, timestamp, time_str, date_label, text, word_count, char_count
                    FROM dictations
                    {where_sql}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, query_params)

                rows = cur.fetchall()
                items = []
                for row in rows:
                    uid, src, ts, time_str, date_label, text, wc, cc = row
                    items.append({
                        "id": str(uid),
                        "source": str(src),
                        "text": str(text),
                        "timestamp": float(ts),
                        "time": str(time_str),
                        "date_label": format_date_label(float(ts)),
                        "word_count": int(wc),
                        "char_count": int(cc)
                    })

                return {
                    "items": items,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": (offset + len(items)) < total
                }
            except Exception as e:
                print(f"[Flow Bridge Storage] Pagination error: {e}")
                return {"items": [], "total": 0, "limit": limit, "offset": offset, "has_more": False}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_count(self, engine: str = "") -> int:
        """Returns total records stored overall or for a specific engine."""
        with self._lock:
            conn = self._connect()
            if not conn:
                return 0
            try:
                cur = conn.cursor()
                if engine and engine.lower() != "all":
                    cur.execute("SELECT count(*) FROM dictations WHERE LOWER(source) = LOWER(?)", (engine,))
                else:
                    cur.execute("SELECT count(*) FROM dictations")
                row = cur.fetchone()
                return row[0] if row else 0
            except Exception:
                return 0
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_stats(self) -> dict:
        """Calculates total dictations, words spoken, hours saved, and engine distribution."""
        with self._lock:
            conn = self._connect()
            if not conn:
                return {"total_transcripts": 0, "total_words": 0, "hours_saved": 0.0, "engines": {}}

            try:
                cur = conn.cursor()
                cur.execute("SELECT count(*), coalesce(sum(word_count), 0) FROM dictations")
                total_transcripts, total_words = cur.fetchone()

                cur.execute("SELECT source, count(*) FROM dictations GROUP BY source")
                engines = {row[0]: row[1] for row in cur.fetchall()}

                # 40 WPM average typing speed
                hours_saved = round((total_words / 40.0) / 60.0, 1)

                return {
                    "total_transcripts": total_transcripts,
                    "total_words": total_words,
                    "hours_saved": hours_saved,
                    "engines": engines
                }
            except Exception:
                return {"total_transcripts": 0, "total_words": 0, "hours_saved": 0.0, "engines": {}}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def delete_by_id(self, unique_id: str) -> bool:
        """Deletes a single dictation by unique_id and marks it in deleted_dictations."""
        if not unique_id:
            return False
        with self._lock:
            conn = self._connect()
            if not conn:
                return False
            try:
                with conn:
                    conn.execute("DELETE FROM dictations WHERE unique_id = ?", (unique_id,))
                    conn.execute("INSERT OR REPLACE INTO deleted_dictations (unique_id, deleted_at) VALUES (?, ?)", (unique_id, time.time()))
                return True
            except Exception as e:
                print(f"[Flow Bridge Storage] Delete error: {e}")
                return False
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def delete_range(self, range_type: str, engine: str = "") -> int:
        """
        Deletes dictations matching a time-range filter and marks them in deleted_dictations.
        range_type options:
          - 'last_24_hours': records within the last 24 hours (timestamp >= now - 86400)
          - 'last_2_days': records within the last 48 hours (timestamp >= now - 172800)
          - 'last_7_days': records within the last 7 days (timestamp >= now - 604800)
          - 'older_than_2_days': records older than 48 hours (timestamp < now - 172800)
          - 'older_than_7_days': records older than 7 days (timestamp < now - 604800)
          - 'older_than_30_days': records older than 30 days (timestamp < now - 2592000)
          - 'all': delete all records
        engine: optional engine filter ('all' or specific engine name)
        """
        now = time.time()
        where_clauses = []
        params = []

        if range_type == 'last_24_hours':
            where_clauses.append("timestamp >= ?")
            params.append(now - 86400.0)
        elif range_type == 'last_2_days':
            where_clauses.append("timestamp >= ?")
            params.append(now - 172800.0)
        elif range_type == 'last_7_days':
            where_clauses.append("timestamp >= ?")
            params.append(now - 604800.0)
        elif range_type == 'older_than_2_days':
            where_clauses.append("timestamp < ?")
            params.append(now - 172800.0)
        elif range_type == 'older_than_7_days':
            where_clauses.append("timestamp < ?")
            params.append(now - 604800.0)
        elif range_type == 'older_than_30_days':
            where_clauses.append("timestamp < ?")
            params.append(now - 2592000.0)
        elif range_type == 'all':
            pass
        else:
            return 0

        if engine and engine.lower() != 'all':
            where_clauses.append("LOWER(source) = LOWER(?)")
            params.append(engine)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        with self._lock:
            conn = self._connect()
            if not conn:
                return 0
            try:
                with conn:
                    cur = conn.cursor()
                    cur.execute(f"SELECT unique_id FROM dictations {where_sql}", params)
                    uids = [r[0] for r in cur.fetchall()]
                    if not uids:
                        return 0

                    conn.execute(f"DELETE FROM dictations {where_sql}", params)
                    tombstones = [(uid, now) for uid in uids]
                    conn.executemany("INSERT OR REPLACE INTO deleted_dictations (unique_id, deleted_at) VALUES (?, ?)", tombstones)
                    return len(uids)
            except Exception as e:
                print(f"[Flow Bridge Storage] Delete range error: {e}")
                return 0
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
