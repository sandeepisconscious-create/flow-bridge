# Flow Bridge 🎙️

> **Universal macOS Dictation Clipboard Sync Daemon**  
> *Speak into your favorite voice tool (Wispr Flow, Detta) and press `⌘ + V` anywhere.*

[![macOS](https://img.shields.io/badge/Platform-macOS-black?logo=apple)](https://apple.com)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## ⚡ Quick Summary (TL;DR)

If you use voice dictation apps like **Wispr Flow** or **Detta**, you have likely experienced them failing to auto-paste into complex web and desktop apps (e.g., **Google AI Studio, ChatGPT, Claude, Cursor, Antigravity, Terminal, or Slack**). 

**Flow Bridge fixes this at the operating system level.** It runs silently in the background, monitors local dictation history databases in real time, and immediately puts your transcribed speech onto the macOS GUI clipboard (`NSPasteboard`).

Whenever an app refuses to auto-paste or drops focus, simply press **`⌘ + V`**—your spoken text will paste reliably every single time.

---

## 💡 Why This Works Where Other Solutions Fail

1. **Bypasses Browser Virtual DOM Blocks**: Complex web apps (Angular reactive forms, ProseMirror, React synthetic event trees) often reject synthetic paste events or drop keystrokes during voice-capture window blur. Flow Bridge bypasses the browser completely.
2. **Dual-App Timestamp Arbitration**: Concurrently listens to both Wispr Flow and Detta transaction logs. Whichever app you spoke into last automatically takes priority based on millisecond UTC timestamps.
3. **Anti-Race-Condition Settle & Hold**: Dictation tools frequently restore previous clipboard contents after simulating their paste attempt. Flow Bridge waits out the internal cleanup delay and re-asserts your transcribed speech so it cannot be overwritten.
4. **Works in Every Application**: Works universally across browsers, IDEs, code editors, communication tools, and terminal sessions.

---

## 🚀 Installation

Choose whichever method you prefer:

### Option 1: One-Line Terminal Command (Recommended)
Open Terminal and run:
```bash
curl -fsSL https://raw.githubusercontent.com/sandeepisconscious-create/flow-bridge/main/install.sh | bash
```
> **What this does:** Automatically installs Flow Bridge to `~/.flow-bridge` and configures a lightweight macOS `launchd` background service so it starts silently whenever you log in.

*To uninstall at any time:*
```bash
curl -fsSL https://raw.githubusercontent.com/sandeepisconscious-create/flow-bridge/main/scripts/uninstall.sh | bash
```

---

### Option 2: Mac Drag-and-Drop `.dmg` Installer
1. Download **`FlowBridge-Installer.dmg`** from [Releases](https://github.com/sandeepisconscious-create/flow-bridge/releases).
2. Open the `.dmg` and drag **`FlowBridge.app`** into your **Applications** folder.
3. Launch `FlowBridge.app` once. It automatically registers to run silently on startup.

> **Building the DMG locally:**
> ```bash
> ./scripts/build_mac_app.sh
> ```
> This creates a distributable `dist/FlowBridge-Installer.dmg`.

---

## 🛠️ CLI & Manual Usage

You can also run the daemon directly from the command line:

```bash
# Run in foreground
./flow_bridge.py

# Run with macOS notification banners on each sync
./flow_bridge.py --notify

# Test clipboard write/read integration
./flow_bridge.py --test-clipboard
```

### CLI Arguments

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

## 📁 Supported Voice Engines

| Engine | Database Location | Status |
|---|---|---|
| **Wispr Flow** | `~/Library/Application Support/Wispr Flow/flow.sqlite` | ✅ Auto-detected |
| **Detta** | `~/Library/Application Support/Detta/history.db` | ✅ Auto-detected |

*Have another voice dictation tool? Additional SQLite or file-based watchers can easily be added via the extensible `BaseDictationWatcher` interface.*

---

## 📄 License
MIT © Sandeep Rao
