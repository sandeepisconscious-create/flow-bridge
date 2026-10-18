# Input Field & Voice Dictation Fixer (Chrome Extension)
## Target: General Inputs + Google AI Studio & Wispr Flow Auto-Paste Healer

### Problem Statement
1. **General Web:** Input fields intermittently freeze, lose focus, or fail to sync with framework virtual DOMs (React, Vue, Angular).
2. **Google AI Studio + Wispr Flow:** 
   - Wispr Flow dictates and attempts to auto-paste into Google AI Studio (`aistudio.google.com`).
   - AI Studio's prompt editor (`ms-prompt-editor`, custom textareas, CodeMirror/ProseMirror wrappers) often drops focus or misses synthetic paste events while Wispr Flow is transcribing.
   - Result: Dictation fails to insert; user must manually copy and paste repeatedly.

---

### Phase 1: Project Scaffolding & Manifest V3 Setup
- **Goal:** Set up the Chrome Extension manifest, permissions, and directory layout.
- **Permissions Needed:**
  - `activeTab`, `scripting`, `storage`
  - `clipboardRead` (to seamlessly recover Wispr Flow transcripts when auto-paste fails)
  - Host permissions: `<all_urls>` with optimized triggers for `https://aistudio.google.com/*`
- **Output:**
  - `manifest.json`
  - `src/background/service_worker.js`
  - `src/content/` & `src/injected/` architecture

---

### Phase 2: Core Universal Input Healer (All Websites)
- **Goal:** Fix frozen fields and swallowed keystrokes across standard websites.
- **Components:**
  - **Focus Guard & Re-arm:** Prevents background scripts or popups from stealing focus; keeps cursor at the active insertion point.
  - **Native Setter Bypass:** Uses `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set` to force updates past React/Vue controlled state blockages.
  - **Synthetic Event Cascade:** Fires bubbling `beforeinput`, `input`, and `change` events.
  - **Overlay / Pointer Unblocker:** Strips accidental `pointer-events: none` and removes transparent blocking backdrops.

---

### Phase 3: Dedicated Google AI Studio Adapter
- **Goal:** Deep integration with Google AI Studio's prompt editor.
- **Components:**
  - **AI Studio Editor Targeter:** Accurately targets the prompt editor (`textarea.textarea`, `[contenteditable]`, and custom components within `ms-prompt-editor` / `ms-chunk-editor`).
  - **Focus Anchor:** Keeps the prompt box locked in focus so when Wispr Flow sends its simulated paste, the target is 100% active and receptive.
  - **Direct Text Injector:** Injects text using `document.execCommand('insertText')` or direct text node insertion with synthetic input event dispatching so AI Studio's internal model updates seamlessly.

---

### Phase 4: Wispr Flow "Smart Catch" & Clipboard Auto-Recovery
- **Goal:** Eliminate the need to ever manually copy-paste when Wispr Flow's auto-paste fails.
- **Components:**
  - **One-Tap Dictation Drop:** Dedicated hotkey (e.g. `F2` or `Cmd+Shift+V`) or automatic focus catch that reads the latest text from clipboard and smoothly injects it right at your cursor position in AI Studio.
  - **Duplicate Prevention:** Ensures the same transcript isn't pasted twice if Wispr Flow succeeded natively.
  - **Visual Notification:** A subtle, unobtrusive floating pill in the corner of AI Studio showing `"Wispr Flow text synced"` so you have instant feedback.

---

### Phase 5: Configuration UI & Preferences
- **Goal:** Simple popup to customize behavior.
- **Components:**
  - `src/popup/popup.html` and `popup.js`:
    - Toggle: **Google AI Studio Auto-Catch for Wispr Flow** (On/Off).
    - Toggle: **Universal Input Unfreezer** (On/Off).
    - Shortcut configuration info.
    - Live status badge indicating if the current tab's input is healthy.

---

### Phase 6: Local Test Suite & Real-World Validation
- **Goal:** Verify that both general input freezing and Google AI Studio Wispr Flow dictation work flawlessly.
- **Components:**
  - Local test harness for stuck inputs and synthetic event testing.
  - Live testing instructions on `aistudio.google.com`.
