// Universal Input Healer: unfreezes inputs, re-asserts focus, clears traps

const UniversalHealer = {
  reviveElement(element) {
    if (!element) return false;

    try {
      // 1. Remove disabling or read-only blocks
      if (element.hasAttribute('disabled')) element.removeAttribute('disabled');
      if (element.readOnly) element.readOnly = false;

      // 2. Clear pointer-events and styles that prevent user interaction
      if (window.getComputedStyle(element).pointerEvents === 'none') {
        element.style.pointerEvents = 'auto';
      }

      // 3. Force focus with preventScroll to avoid abrupt jumps
      element.focus({ preventScroll: true });

      // 4. Position cursor at the very end
      this.moveCursorToEnd(element);

      // 5. Provide gentle visual pulse indicator
      element.classList.add('input-healer-active-pulse');
      setTimeout(() => element.classList.remove('input-healer-active-pulse'), 400);

      // 6. Signal page-level script to sync native prototype value if needed
      window.postMessage({
        type: 'INPUT_HEALER_PAGE_REVIVE',
        targetId: element.id || null,
        tagName: element.tagName.toLowerCase()
      }, '*');

      Utils.showNotification('Input field unblocked & focused', 'success');
      return true;
    } catch (err) {
      console.error('[Input Healer] Failed to revive element:', err);
      return false;
    }
  },

  moveCursorToEnd(element) {
    if (typeof element.selectionStart === 'number') {
      const len = element.value ? element.value.length : 0;
      element.setSelectionRange(len, len);
    } else if (element.isContentEditable || element.getAttribute('contenteditable') === 'true') {
      const range = document.createRange();
      const sel = window.getSelection();
      range.selectNodeContents(element);
      range.collapse(false); // false = end
      sel.removeAllRanges();
      sel.addRange(range);
    }
  },

  // Insert text directly using native synthetic commands
  insertTextDirectly(element, text) {
    if (!element || !text) return false;

    this.reviveElement(element);

    const isInput = element.tagName && (element.tagName.toLowerCase() === 'textarea' || element.tagName.toLowerCase() === 'input');

    if (isInput) {
      // 1. Try execCommand first (safest for undo stacks)
      const success = document.execCommand('insertText', false, text);

      // 2. Direct fallback injection + event cascade
      if (!success || !element.value.includes(text)) {
        const start = element.selectionStart !== undefined ? element.selectionStart : element.value.length;
        const end = element.selectionEnd !== undefined ? element.selectionEnd : element.value.length;
        element.value = element.value.substring(0, start) + text + element.value.substring(end);
        element.selectionStart = element.selectionEnd = start + text.length;

        // Dispatches complete reactive event cascade
        element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));

        // Notify page-level engine to call native setter directly
        window.postMessage({
          type: 'INPUT_HEALER_SET_VALUE',
          text: text
        }, '*');
      }
      return true;
    } else if (element.isContentEditable || element.getAttribute('contenteditable') === 'true' || element.getAttribute('role') === 'textbox') {
      // Rich text / contenteditable
      const success = document.execCommand('insertText', false, text);
      if (!success) {
        element.textContent = (element.textContent || '') + text;
        element.dispatchEvent(new Event('input', { bubbles: true }));
      }
      return true;
    }
    return false;
  }
};
