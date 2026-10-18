# Flow Bridge 🎙️

**Universal macOS Dictation Clipboard Sync Daemon**

Flow Bridge solves the voice-to-text dictation problem across all desktop and web apps (Google AI Studio, ChatGPT, Claude, Cursor, Antigravity, Terminal, Slack, etc.) by reading directly from voice app databases at the OS level and synchronizing your speech onto the macOS GUI clipboard (`NSPasteboard`).

---

## 💡 Why This Replaces Browser Input Hacks

Modern web apps use complex Virtual DOMs (Angular, React, ProseMirror, CodeMirror) that frequently reject synthetic DOM events, drop focus during voice-capture window blur, or lose text during state reconciliation.

**Flow Bridge bypasses the browser completely:**
1. Concurrently listens to local voice app databases (Wispr Flow, Detta) with millisecond timestamp comparison.
2. Whichever voice tool you speak into last is instantly written to your system clipboard.
3. **Anti-Race-Condition Settle & Hold**: Voice tools often restore old clipboard contents after simulating pastes. Flow Bridge waits for the app's internal routine to settle, then re-asserts your speech so `⌘ + V` **always** pastes your actual spoken transcript.

---

## ⚡ Quick Start

### 1. Run in Foreground
```bash
./wispr_clipboard_sync.py
```
*(Or `python3 wispr_clipboard_sync.py`)*

### 2. Run with Native macOS Notifications
```bash
./wispr_clipboard_sync.py --notify
```

### 3. Run Automatically in Background on Boot (`launchd`)
To install Flow Bridge as a background macOS service that starts silently whenever you log in:
```bash
./wispr_clipboard_sync.py --install-service
```
To uninstall the service at any time:
```bash
./wispr_clipboard_sync.py --uninstall-service
```

---

## ⚙️ CLI Options

| Flag | Default | Description |
|---|---|---|
| `--poll` | `0.25` | Polling frequency in seconds |
| `--settle` | `0.35` | Settle delay before re-assertion |
| `--reassert` | `3` | Number of re-assertion hold attempts |
| `--notify` | `False` | Display native macOS notification on sync |
| `--verbose` | `False` | Print verbose debug logs |
| `--install-service` | — | Install as macOS background launchd service |
| `--uninstall-service`| — | Uninstall macOS background launchd service |
| `--test-clipboard` | — | Test writing and reading from NSPasteboard |

---

## 📁 Supported Voice Apps
- **Wispr Flow**: `~/Library/Application Support/Wispr Flow/flow.sqlite`
- **Detta**: `~/Library/Application Support/Detta/history.db`
- Extensible architecture via `BaseDictationWatcher` for additional local voice engines.

---

## 📄 License
MIT
