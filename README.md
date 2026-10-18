<div align="center">
  <img src="assets/logo.png" width="128" alt="Flow Bridge Logo" />
  <h1>Flow Bridge</h1>
  <p><strong>Universal macOS Dictation Clipboard Daemon & Menu Bar Hub</strong><br/>
  <em>Speak into Wispr Flow, Handy, or Detta — then press <code>⌘ + V</code> anywhere to paste.</em></p>

  <p>
    <a href="https://github.com/sandeepisconscious-create/flow-bridge/releases/download/v1.0.6/FlowBridge-Installer.dmg">
      <img src="https://img.shields.io/badge/Download-macOS%20DMG%20(v1.0.6)-007AFF?style=for-the-badge&logo=apple&logoColor=white" alt="Download macOS DMG" />
    </a>
  </p>
</div>

---

## 💡 What is Flow Bridge? (In Plain English)

Have you ever used a voice dictation app on your Mac (**Wispr Flow**, **Handy**, or **Detta**) to talk into **Google AI Studio, ChatGPT, Claude, Cursor, VS Code, Slack, or Terminal**, only for your spoken words to **vanish** or fail to paste?

**Flow Bridge solves this permanently at the operating system level.**

Whenever you finish dictating:
1. Flow Bridge catches your spoken words directly from your app's local database in real time.
2. It immediately copies your transcribed text to the macOS clipboard (`NSPasteboard`).
3. You press **`⌘ + V`** (Command + V) anywhere you want, and your text appears every single time.

No browser extensions. No focus-loss bugs. It sits silently in your macOS top menu bar, ready whenever you need it.

---

## ⚡ Problems & Pain Points Flow Bridge Solves

If you arrived here searching for fixes to any of these issues, Flow Bridge is the direct solution:

- ❌ **Wispr Flow / Handy not pasting into ChatGPT, Claude, or Google AI Studio**: Complex reactive web editors (ProseMirror, Draft.js, Angular, React virtual DOM) often drop input focus when a dictation floating popup closes, causing synthetic paste events to be swallowed or ignored.
- ❌ **Cursor, VS Code, and Terminal ignoring voice paste**: Desktop Electron apps and terminal windows often reject synthetic accessibility paste events triggered by background apps. Flow Bridge bypasses synthetic typing completely by writing straight to the OS clipboard.
- ❌ **Lost voice text on blur**: If you speak and accidentally click away, your dictation saves to the local database but is never inserted into the active window. Flow Bridge ensures your speech is always waiting on `⌘ + V`.
- ❌ **Overwritten clipboard race conditions**: Dictation apps frequently attempt to restore previous clipboard contents after simulating a paste. Flow Bridge employs an anti-race settle-and-hold loop so your transcribed text cannot be prematurely wiped out.
- ❌ **Multi-app confusion**: If you switch between Wispr Flow, Handy, and Detta, Flow Bridge monitors all three concurrently and automatically synchronizes whichever engine you spoke into last.

---

## ✨ Features & Benefits

### 1. Universal `⌘ + V` Dictation Sync
Speak into any supported dictation app. When you're ready, simply click anywhere and press `⌘ + V`. It works reliably in every browser, text editor, terminal, and desktop app.

### 2. Native macOS Menu Bar App & Popover HUD
- A sleek blue microphone icon lives in your top macOS menu bar (next to your clock and Wi-Fi).
- Click the icon anytime to drop down an instant popover HUD showing your detected engines and recent transcripts.
- Minimizing or closing the window seamlessly tucks Flow Bridge into the menu bar without cluttering your Dock.

### 3. Detected Voice Engines Grid
Flow Bridge automatically detects and connects to installed voice dictation apps on your Mac:
- 🎙️ **Wispr Flow** (`flow.sqlite`)
- ✋ **Handy** (`com.pais.handy/history.db`)
- ⚡ **Detta** (`history.db`)

### 4. 10 Recent Dictations with 1-Click Copy
Accidentally overwrite your clipboard? Flow Bridge keeps your last 10 dictations in a clean, dark-mode list. Click the copy icon next to any previous transcript to re-copy it to your clipboard with instant visual feedback.

### 5. Standalone Desktop Window (No Browser Tab Needed)
Double-clicking Flow Bridge opens a clean native macOS desktop window powered by built-in WebKit (`WKWebView`). No need to navigate to localhost tabs in Chrome or Safari.

### 6. 100% Private & Offline
Flow Bridge runs entirely on your local machine. It connects only to local SQLite databases on your Mac's filesystem (`127.0.0.1`). No audio, no text, and no telemetry are ever transmitted to any external server.

---

## 🚀 How to Install

Choose whichever method you prefer:

### Method 1: Mac Drag-and-Drop Installer (Recommended)
1. Download **[FlowBridge-Installer.dmg (Latest v1.0.6)](https://github.com/sandeepisconscious-create/flow-bridge/releases/download/v1.0.6/FlowBridge-Installer.dmg)**.
2. Open the downloaded DMG and drag **FlowBridge** into your **Applications** folder.
3. **To open for the first time**:
   - Right-click (or Control-click) **`FlowBridge.app`** in Applications and select **Open** → then click **Open**.
   - *(Or double-click the `Open FlowBridge.command` helper right inside the DMG).*
4. A native window will open, and a blue microphone icon will appear in your top menu bar.

---

### Method 2: One-Line Terminal Command
Open **Terminal** on your Mac, paste this line, and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/sandeepisconscious-create/flow-bridge/main/install.sh | bash
```

> **What this does:** Automatically installs Flow Bridge to `~/.flow-bridge/` and configures a lightweight macOS `launchd` background service so it starts silently whenever your Mac boots.

*To uninstall anytime:*
```bash
curl -fsSL https://raw.githubusercontent.com/sandeepisconscious-create/flow-bridge/main/scripts/uninstall.sh | bash
```

---

## 📋 3-Step Quick Start

1. **Speak** into Wispr Flow, Handy, or Detta.
2. **Click** where you want your text (ChatGPT, Claude, Cursor, Terminal, etc.).
3. **Press `⌘ + V`**. Your speech pastes immediately.

---

## 📁 Supported Voice Engines

| Engine | Database Location | Status |
|---|---|---|
| **Wispr Flow** | `~/Library/Application Support/Wispr Flow/flow.sqlite` | ✅ Auto-detected |
| **Handy** | `~/Library/Application Support/com.pais.handy/history.db` | ✅ Auto-detected |
| **Detta** | `~/Library/Application Support/Detta/history.db` | ✅ Auto-detected |

*Have another SQLite or file-based dictation tool? Additional watchers can be added via the extensible `BaseDictationWatcher` interface in `flow_bridge.py`.*

---

## ❓ Frequently Asked Questions (FAQ)

#### Does Flow Bridge take up space in my Dock?
No. Flow Bridge runs as a background accessory app (`LSUIElement`). It stays in your top menu bar and does not clutter your Dock.

#### Does it send my voice or text anywhere?
**No. Never.** Flow Bridge runs 100% locally on your computer. Nothing ever leaves your Mac.

#### Can I re-copy something I dictated 10 minutes ago?
Yes. Click the blue microphone icon in your top menu bar or open the window. Your 10 most recent dictations are listed there with 1-click copy buttons.

#### Why does normal auto-paste fail in web AI apps?
Complex websites often drop cursor focus or ignore simulated accessibility keystrokes while voice popups blur and close. Flow Bridge bypasses web synthetic event trees completely by ensuring your transcribed words are already on the native macOS clipboard.

---

## 📄 License
MIT © Sandheep Rao
