// Page Context Script (runs in target page context, bypassing isolated content script world)
(function() {
  // Listen for messages from content script
  window.addEventListener('message', (event) => {
    if (!event.data || typeof event.data !== 'object') return;

    if (event.data.type === 'INPUT_HEALER_SET_VALUE') {
      const active = document.activeElement;
      if (!active) return;

      const text = event.data.text;
      const isInput = active.tagName.toLowerCase() === 'input';
      const isTextarea = active.tagName.toLowerCase() === 'textarea';

      if (isInput || isTextarea) {
        const proto = isInput ? window.HTMLInputElement.prototype : window.HTMLTextAreaElement.prototype;
        const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;

        if (nativeSetter) {
          const currentVal = active.value || '';
          const start = active.selectionStart !== undefined ? active.selectionStart : currentVal.length;
          const end = active.selectionEnd !== undefined ? active.selectionEnd : currentVal.length;
          const newVal = currentVal.substring(0, start) + text + currentVal.substring(end);

          // Invoke native prototype setter to bypass React/Vue controlled state barriers
          nativeSetter.call(active, newVal);

          // Move cursor
          const newPos = start + text.length;
          active.setSelectionRange(newPos, newPos);

          // Dispatch synthetic input event cascade
          active.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, inputType: 'insertText', data: text }));
          active.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
    }
  });
})();
