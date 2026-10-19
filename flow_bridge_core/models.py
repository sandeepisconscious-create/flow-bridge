"""
Flow Bridge Core Models and Shared Constants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

CURRENT_VERSION = "1.1.2"
GITHUB_REPO = "sandeepisconscious-create/flow-bridge"
DEFAULT_UI_PORT = 49231
LOCK_FILE_PATH = os.path.expanduser("~/.flow_bridge.lock")


@dataclass(frozen=True)
class DictationRecord:
    """Represents a finalized or active transcription entry captured from a voice engine."""
    source_name: str
    unique_id: str
    timestamp: float
    text: str


@dataclass
class DaemonConfig:
    """Runtime configuration options for Flow Bridge."""
    wispr_db: str = os.path.expanduser("~/Library/Application Support/Wispr Flow/flow.sqlite")
    detta_db: str = os.path.expanduser("~/Library/Application Support/Detta/history.db")
    handy_db: str = os.path.expanduser("~/Library/Application Support/com.pais.handy/history.db")
    poll_interval_sec: float = 0.25
    settle_delay_sec: float = 0.35
    reassert_attempts: int = 3
    reassert_interval_sec: float = 0.15
    auto_pause_media: bool = True
    hide_apps_to_menu_bar: bool = True
    show_notifications: bool = False
    verbose: bool = False
