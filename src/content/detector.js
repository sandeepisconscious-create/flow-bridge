// Input Detector & Keystroke Tracker Engine

const Detector = {
  lastFocusedElement: null,
  missedKeystrokesCount: 0,
  lastKeyDownTime: 0,
  lastKey: null,

  init() {
    this.setupFocusTracking();
    this.setupKeystrokeMonitoring();
  },

  setupFocusTracking() {
    // Capture-phase tracking ensures we capture focus even if stopped by other scripts
    document.addEventListener('focusin', (e) => {
      const target = e.target;
      if (Utils.isEditable(target)) {
        this.lastFocusedElement = target;
        this.missedKeystrokesCount = 0;
      }
    }, true);

    document.addEventListener('mousedown', (e) => {
      const target = e.target;
      if (Utils.isEditable(target)) {
        this.lastFocusedElement = target;
      }
    }, true);
  },

  setupKeystrokeMonitoring() {
    // Monitor in capture phase (before page handlers can swallow it)
    document.addEventListener('keydown', (e) => {
      // Ignore system shortcuts
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'Shift' || e.key === 'Control' || e.key === 'Alt') return;

      const active = Utils.getActiveElement();
      this.lastKeyDownTime = Date.now();
      this.lastKey = e.key;

      if (!active || !Utils.isEditable(active)) {
        // Keystroke typed with no active editable element focused!
        // Check if there was a recently focused editable element
        if (this.lastFocusedElement && document.body.contains(this.lastFocusedElement)) {
          this.missedKeystrokesCount++;
          if (this.missedKeystrokesCount >= 2) {
            console.warn('[Input Healer] Detected typing without focus. Re-asserting focus...');
            UniversalHealer.reviveElement(this.lastFocusedElement);
          }
        }
        return;
      }

      // Check for frozen controlled inputs:
      // Keystroke fired, but let's check shortly after if value/content remained unchanged
      const initialVal = active.value !== undefined ? active.value : active.textContent;
      const initialLen = initialVal ? initialVal.length : 0;

      setTimeout(() => {
        const currentActive = Utils.getActiveElement();
        if (currentActive === active && !e.defaultPrevented) {
          const currentVal = active.value !== undefined ? active.value : active.textContent;
          const currentLen = currentVal ? currentVal.length : 0;

          // If standard printable character was typed, but length and value did not change
          if (e.key.length === 1 && currentLen === initialLen && currentVal === initialVal) {
            this.missedKeystrokesCount++;
            if (this.missedKeystrokesCount >= 2) {
              console.warn('[Input Healer] Keystroke ignored by page state. Applying gentle heal...');
              UniversalHealer.reviveElement(active);
            }
          } else {
            // Typing is working fine, reset counter
            this.missedKeystrokesCount = 0;
          }
        }
      }, 80);
    }, true);
  },

  getCurrentTarget() {
    const active = Utils.getActiveElement();
    if (active && Utils.isEditable(active)) return active;
    if (this.lastFocusedElement && document.body.contains(this.lastFocusedElement)) {
      return this.lastFocusedElement;
    }

    // Modern AI chat prompt selectors (Gemini, ChatGPT, Claude, Antigravity, Google AI Studio, etc.)
    const chatSelectors = [
      'textarea[placeholder*="Ask"]',
      'textarea[placeholder*="Type"]',
      'textarea[placeholder*="Make changes"]',
      'textarea[placeholder*="features"]',
      'textarea[placeholder*="message"]',
      'div[contenteditable="true"][role="textbox"]',
      'div[contenteditable="true"].ProseMirror',
      'div[contenteditable="true"]',
      'ms-prompt-editor textarea',
      'textarea',
      'input[type="text"]'
    ];

    for (const selector of chatSelectors) {
      const el = document.querySelector(selector);
      if (el && !el.disabled) {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          return el;
        }
      }
    }

    return null;
  }
};
