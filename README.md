# Flow Bridge (⚡ Input Healer & Wispr Flow Auto-Paster)

A lightweight dual-utility system designed to fix frozen web input fields and provide seamless Wispr Flow dictation integration across complex web applications like Google AI Studio, ChatGPT, Claude, and rich-text editors.

---

## 🌟 The Problem It Solves

1. **Wispr Flow Dictation Paste Issues:**
   - Modern single-page applications (like Google AI Studio, Angular/React interfaces) often reject or drop synthetic paste events from desktop voice-typing tools like Wispr Flow due to focus drift or virtual DOM event isolation.
2. **Input Freezing & Missed Keystrokes:**
   - Web inputs frequently drop focus, ignore initial keystrokes, or desync from reactive component state.

---

## 🚀 Architecture & Components

`flow-bridge` provides two coordinated solutions:

### 1. Wispr Flow Clipboard Sync Daemon (`wispr_clipboard_sync.py`)
- **Native macOS AppKit Pasteboard:** Writes directly to the macOS GUI session (`NSPasteboard.generalPasteboard()`), avoiding subprocess shell isolation.
- **Race-Condition Resilient:** Wispr Flow cleans up and restores previous clipboards after auto-paste attempts. This daemon listens to the local Wispr database WAL, settles for 350ms, and re-asserts the finalized transcript so `Cmd + V` **always** pastes your latest speech anywhere.
- **100% Silent:** Runs quietly in the background without intrusive banners or alerts.

### 2. Chrome Extension (`manifest.json` + `src/`)
- **Universal Input Healer:** Automatically detects frozen fields, clears CSS traps (`pointer-events: none`), and forces cursor re-focusing.
- **Google AI Studio Adapter:** Identifies prompt components (`ms-prompt-editor`, chunk textareas) and provides quick smart-paste triggers.
- **Shortcuts:**
  - `Cmd + Shift + V` (Mac) / `Ctrl + Shift + V` (Windows): Smart-paste dictation into active prompt.
  - `Alt + Shift + F`: Force-unfreeze current input field.

---

## 🛠️ Installation & Setup

### A. Run the Clipboard Sync Daemon
```bash
python3 wispr_clipboard_sync.py
```
*(To run in the background on startup, add to your user launchd or run via nohup).*

### B. Load the Chrome Extension
1. Open Google Chrome and go to `chrome://extensions/`.
2. Turn on **Developer mode** (top-right).
3. Click **Load unpacked** (top-left).
4. Select the `flow-bridge` directory:
   ```text
   /Users/sandeeprao/Documents/Code/flow-bridge
   ```
5. Pin the extension to your toolbar.

---

## 📄 License
MIT
