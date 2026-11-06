<div align="center">
  <img src="assets/logo.png" width="110" alt="Flow Bridge Logo" />
  <h1>Flow Bridge</h1>
  <p><strong>Universal macOS Dictation Clipboard Daemon & History Hub</strong><br/>
  <em>Speak into Wispr Flow, Google Gemini, Handy, or Detta — then press <code>⌘ + V</code> anywhere to paste.</em></p>

  <p>
    <a href="https://github.com/sandeepisconscious-create/flow-bridge/releases/download/v1.0.0/FlowBridge-Installer.dmg">
      <img src="https://img.shields.io/badge/Download-macOS%20DMG%20(v1.0.0)-007AFF?style=for-the-badge&logo=apple&logoColor=white" alt="Download macOS DMG" />
    </a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/macOS-12.0%2B%20(Apple%20Silicon%20%26%20Intel)-black?style=flat-square&logo=apple&logoColor=white" alt="macOS Version" />
    <img src="https://img.shields.io/badge/Privacy-100%25%20Local%20Offline-success?style=flat-square&logo=shield" alt="100% Offline" />
    <img src="https://img.shields.io/badge/CPU-0.0%25%20Idle%20(kqueue)-blueviolet?style=flat-square" alt="kqueue" />
    <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License" />
  </p>
</div>

---

## 💡 What is Flow Bridge?

Dictation tools often fail to paste into complex web apps (ChatGPT, Claude, Google AI Studio) or developer environments (Cursor, VS Code, Terminal) because reactive web editors swallow synthetic paste events or drop focus.

**Flow Bridge fixes this at the system clipboard level:**
1. **Speak** into Wispr Flow, Google Gemini, Handy, or Detta.
2. Flow Bridge instantly captures and syncs the transcript to the macOS clipboard (`NSPasteboard`).
3. **Press `⌘ + V`** anywhere to paste reliably every time.

All dictations are saved to a private, local SQLite database (`~/.flow-bridge/dictations.sqlite`) so you never lose your speech.

---

## ✨ Features

- **Guaranteed `⌘ + V` Paste**: Bypasses synthetic keystrokes by writing directly to the macOS pasteboard in <0.2ms.
- **Universal Multi-Engine Support**: Automatically syncs whichever app you used last:
  - **Wispr Flow**
  - **Google Gemini** (macOS Native App — Stream to Cursor)
  - **Handy**
  - **Detta**
- **Menu Bar HUD + Full Desktop Studio**:
  - **Menu Bar Popover**: Quick toggle for universal sync, recent dictations, and 1-click copy.
  - **Desktop Window**: Searchable history, engine health indicators, and productivity stats.
- **Customizable History Deletion**:
  - Delete individual dictations or clear by timeframe (Past 24 Hours, 2 Days, 7 Days, or All Time).
  - Tombstone tracking prevents third-party apps from re-importing deleted records.
- **Zero Idle CPU (`kqueue`)**: Uses kernel-level file monitoring (`kqueue` VNODE) to sleep at 0.0% CPU when not transcribing.
- **100% Local & Private**: No analytics, no telemetry, no cloud servers. Everything stays on your Mac.

---

## 🚀 Installation

### Option 1: macOS Drag-and-Drop Installer (Recommended)
1. Download **[FlowBridge-Installer.dmg](https://github.com/sandeepisconscious-create/flow-bridge/releases/download/v1.0.0/FlowBridge-Installer.dmg)**.
2. Open the DMG and drag **FlowBridge** to your **Applications** folder.
3. Launch FlowBridge. *(If Gatekeeper prompts on first launch, click Open Anyway in System Settings → Privacy & Security)*.

### Option 2: One-Line Terminal Command
```bash
curl -fsSL https://raw.githubusercontent.com/sandeepisconscious-create/flow-bridge/main/install.sh | bash
```
> Installs Flow Bridge to `~/.flow-bridge/` and sets up a lightweight background service (`launchd`).

To uninstall anytime:
```bash
curl -fsSL https://raw.githubusercontent.com/sandeepisconscious-create/flow-bridge/main/scripts/uninstall.sh | bash
```

---

## 📁 Supported Engines

| Engine | Integration | Detection |
|---|---|:---:|
| **Wispr Flow** | `~/Library/Application Support/Wispr Flow/flow.sqlite` | ✅ Automatic |
| **Google Gemini** | Native App (`com.google.GeminiMacOS`) | ✅ Automatic |
| **Handy** | `~/Library/Application Support/com.pais.handy/history.db` | ✅ Automatic |
| **Detta** | `~/Library/Application Support/Detta/history.db` | ✅ Automatic |

---

## ❓ FAQ

#### Does Flow Bridge run in the background?
Yes, it lives quietly in your macOS menu bar as an accessory app with zero dock clutter.

#### Does it ever mute audio or control media?
No. Flow Bridge focuses strictly on universal clipboard synchronization and transcript history. It does not alter your volume, audio, or media playback.

#### Does any voice data leave my computer?
No. Flow Bridge operates completely offline and reads only local application databases on your Mac.

---

## 📄 License

MIT License. Copyright (c) 2026 Sandheep Rao.
