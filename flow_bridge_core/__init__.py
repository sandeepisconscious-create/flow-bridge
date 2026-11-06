"""
Flow Bridge package initialization.
"""

from flow_bridge_core.daemon import FlowBridgeDaemon
from flow_bridge_core.models import CURRENT_VERSION, DaemonConfig, DictationRecord
from flow_bridge_core.platform.pasteboard import Notifier, PasteboardManager
from flow_bridge_core.platform.shortcut import ShortcutWatcher

__version__ = CURRENT_VERSION
__all__ = [
    "CURRENT_VERSION",
    "DaemonConfig",
    "DictationRecord",
    "FlowBridgeDaemon",
    "Notifier",
    "PasteboardManager",
    "ShortcutWatcher",
]
