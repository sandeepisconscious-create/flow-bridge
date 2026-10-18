// Shared utility functions for input detection, traversal and notification

const Utils = {
  // Check if an element is an editable input
  isEditable(el) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
    const tagName = el.tagName.toLowerCase();
    if (tagName === 'textarea') return true;
    if (tagName === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      const textTypes = ['text', 'search', 'url', 'tel', 'email', 'password', 'number'];
      return textTypes.includes(type);
    }
    if (el.isContentEditable || el.getAttribute('contenteditable') === 'true' || el.getAttribute('contenteditable') === '') {
      return true;
    }
    if (el.getAttribute('role') === 'textbox') return true;
    return false;
  },

  // Traverse deep active element inside Shadow DOMs
  getActiveElement(root = document) {
    let active = root.activeElement;
    while (active && active.shadowRoot && active.shadowRoot.activeElement) {
      active = active.shadowRoot.activeElement;
    }
    return active;
  },

  // Show a floating micro-notification on screen
  showNotification(message, type = 'info') {
    let toast = document.getElementById('input-healer-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'input-healer-toast';
      document.body.appendChild(toast);
    }
    toast.className = `input-healer-toast ${type} show`;
    toast.innerHTML = `<span class="icon">${type === 'success' ? '✓' : '⚡'}</span> <span>${message}</span>`;

    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
      toast.classList.remove('show');
    }, 2400);
  },

  // Read latest text from clipboard
  async readClipboard() {
    try {
      return await navigator.clipboard.readText();
    } catch (err) {
      console.warn('[Input Healer] Clipboard access restricted:', err);
      return null;
    }
  }
};
