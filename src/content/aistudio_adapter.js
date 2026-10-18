// Dedicated Adapter for Google AI Studio (aistudio.google.com) and Wispr Flow

const AIStudioAdapter = {
  isAIStudio() {
    return window.location.hostname.includes('aistudio.google.com');
  },

  // Locates the actual active prompt input in AI Studio
  findPromptEditor() {
    // 1. Check if user is already inside an editable element
    const active = Utils.getActiveElement();
    if (active && Utils.isEditable(active)) {
      return active;
    }

    // 2. AI Studio prompt area selectors (Angular/Material/Custom wrappers)
    const selectors = [
      'ms-prompt-editor textarea',
      'ms-chunk-editor textarea',
      'textarea[aria-label*="Prompt"]',
      'textarea[placeholder*="Type something"]',
      'textarea[placeholder*="Start typing"]',
      'textarea.textarea',
      'div[contenteditable="true"][role="textbox"]',
      '.chat-turn textarea',
      'textarea'
    ];

    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && !el.disabled) {
        return el;
      }
    }

    return null;
  },

  // Focus lock anchor: prevents random background blurs while using Wispr Flow
  anchorFocus() {
    const editor = this.findPromptEditor();
    if (editor) {
      editor.focus({ preventScroll: true });
      UniversalHealer.moveCursorToEnd(editor);
      return true;
    }
    return false;
  },

  // Paste handler tailored specifically for Wispr Flow text
  async pasteWisprFlowText() {
    const editor = this.findPromptEditor();
    if (!editor) {
      Utils.showNotification('Could not find AI Studio prompt box', 'warning');
      return false;
    }

    // Make sure it is focused
    editor.focus({ preventScroll: true });

    // Grab transcript directly from clipboard
    const clipText = await Utils.readClipboard();
    if (!clipText || !clipText.trim()) {
      Utils.showNotification('Clipboard is empty', 'warning');
      return false;
    }

    // Try inserting via document.execCommand first (safest for Angular/ProseMirror models)
    let success = document.execCommand('insertText', false, clipText);

    if (!success) {
      // Fallback: Dispatch synthetic input event cascade
      if (editor.tagName && editor.tagName.toLowerCase() === 'textarea') {
        const start = editor.selectionStart || editor.value.length;
        const end = editor.selectionEnd || editor.value.length;
        editor.value = editor.value.substring(0, start) + clipText + editor.value.substring(end);
        editor.selectionStart = editor.selectionEnd = start + clipText.length;

        // Fire full synthetic event chain for Angular/Material reactivity
        editor.dispatchEvent(new Event('input', { bubbles: true }));
        editor.dispatchEvent(new Event('change', { bubbles: true }));
        success = true;
      }
    }

    if (success) {
      Utils.showNotification('Wispr Flow text synced!', 'success');
      return true;
    } else {
      Utils.showNotification('Failed to insert text', 'warning');
      return false;
    }
  },

  init() {
    if (!this.isAIStudio()) return;
    console.log('[Input Healer] Google AI Studio detected. Activating Wispr Flow adapter.');

    // Add a subtle persistent "Wispr Ready" badge in the AI Studio prompt area
    this.injectQuickPasteWidget();
  },

  // Injects an unobtrusive floating button next to AI Studio's prompt bar for 1-click import
  injectQuickPasteWidget() {
    const checkInterval = setInterval(() => {
      const editor = this.findPromptEditor();
      if (editor && !document.getElementById('wispr-flow-smart-paste-btn')) {
        const btn = document.createElement('button');
        btn.id = 'wispr-flow-smart-paste-btn';
        btn.title = 'Wispr Flow Smart Catch (Click or Cmd+Shift+V)';
        btn.innerHTML = `<span>🎙️ Paste Wispr</span>`;
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          this.pasteWisprFlowText();
        });

        // Position next to the editor container
        const parent = editor.closest('ms-prompt-editor') || editor.parentElement;
        if (parent) {
          parent.style.position = 'relative';
          parent.appendChild(btn);
        }
      }
    }, 2000);
  }
};
