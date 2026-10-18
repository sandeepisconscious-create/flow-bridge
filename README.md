<div align="center">
  <img src="assets/logo.png" width="120" alt="Flow Bridge Logo" />
  <h1>Flow Bridge</h1>
  <p><strong>Universal Dictation Copy for Mac</strong><br/>
  <em>Speak into Wispr Flow, Handy, or Detta — then press <code>⌘ + V</code> anywhere to paste.</em></p>
</div>

---

## What is Flow Bridge? (In Plain English)

Have you ever used a voice dictation app on your Mac (like **Wispr Flow**, **Handy**, or **Detta**) to talk into **Google AI Studio, ChatGPT, Claude, Cursor, Slack, or Terminal**, only for your words to **vanish** or fail to paste?

**Flow Bridge fixes this.** 

Whenever you finish speaking into any of your dictation apps:
1. Flow Bridge catches your spoken words instantly.
2. It quietly copies them straight to your Mac clipboard.
3. You press **`⌘ + V`** (Command + V) anywhere you want, and your text appears every single time.

No browser extensions. No setup headaches. It just works in the background.

---

## 3-Step Quick Start

1. **Speak** into Wispr Flow, Handy, or Detta.
2. Click where you want your text (ChatGPT, Claude, Terminal, etc.).
3. Press **`⌘ + V`**. Your speech pastes immediately.

---

## 🚀 How to Install

Choose whichever is easier for you:

### Method 1: Double-Click Installer (Easiest)
1. Download **[FlowBridge-Installer.dmg](https://github.com/sandeepisconscious-create/flow-bridge/releases/download/v1.0.1/FlowBridge-Installer.dmg)** (or check [Releases](https://github.com/sandeepisconscious-create/flow-bridge/releases)).
2. Double-click the file and drag **FlowBridge** into your **Applications** folder.
3. Open **FlowBridge** once.
   *(Note: Since this is an open-source tool, if macOS asks to verify on first launch, simply right-click `FlowBridge.app` in Applications and choose **Open**).*

---

### Method 2: One-Line Terminal Command
Open **Terminal** on your Mac, copy-paste this line, and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/sandeepisconscious-create/flow-bridge/main/install.sh | bash
```

To remove Flow Bridge anytime:
```bash
curl -fsSL https://raw.githubusercontent.com/sandeepisconscious-create/flow-bridge/main/scripts/uninstall.sh | bash
```

---

## 🖥️ See Your Recent Dictations

Flow Bridge includes a clean, dark-mode dashboard right in your browser.

While Flow Bridge is running, open this link:
👉 **[http://127.0.0.1:49231](http://127.0.0.1:49231)**

Here you can:
- See which voice apps on your Mac are connected.
- View your **10 most recent dictations**.
- Click the copy button next to any past dictation to re-copy it with 1 click.

---

## 🎙️ Which Apps Does Flow Bridge Support?

| Voice App | What Flow Bridge Does | Status |
|---|---|---|
| **Wispr Flow** | Grabs speech from its local history database | ✅ Supported |
| **Handy** | Grabs speech from its local history database | ✅ Supported |
| **Detta** | Grabs speech from its local history database | ✅ Supported |

If you use multiple apps, Flow Bridge always picks whichever app you spoke into last!

---

## ❓ Frequently Asked Questions

#### Does it take up space in my Dock?
No. Flow Bridge runs silently in the background as a lightweight helper without cluttering your Dock.

#### Does it send my voice or text to any external server?
**No. Never.** Flow Bridge runs 100% locally on your Mac. Nothing ever leaves your computer.

#### Why does normal auto-paste fail in ChatGPT and Claude?
Complex websites often drop focus or ignore simulated keystrokes while voice popups are closing. Flow Bridge bypasses website tricks completely by putting your text straight into your Mac's native clipboard so **`⌘ + V`** works without fail.

---

## 📄 License
MIT © Sandheep Rao
