// Popup UI Controller

document.addEventListener('DOMContentLoaded', async () => {
  const btnUnfreeze = document.getElementById('btn-unfreeze');
  const btnWisprPaste = document.getElementById('btn-wispr-paste');
  const toggleAIStudio = document.getElementById('toggle-aistudio');
  const toggleUniversal = document.getElementById('toggle-universal');
  const toggleVisual = document.getElementById('toggle-visual');
  const statusText = document.getElementById('status-text');
  const siteBadge = document.getElementById('site-badge');

  // Load preferences
  chrome.storage.sync.get([
    'aiStudioAdapterEnabled',
    'universalHealerEnabled',
    'visualNotificationEnabled'
  ], (items) => {
    toggleAIStudio.checked = items.aiStudioAdapterEnabled !== false;
    toggleUniversal.checked = items.universalHealerEnabled !== false;
    toggleVisual.checked = items.visualNotificationEnabled !== false;
  });

  // Query current tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.url) {
    if (tab.url.includes('aistudio.google.com')) {
      siteBadge.textContent = 'Google AI Studio';
      siteBadge.style.color = '#38bdf8';
      siteBadge.style.borderColor = 'rgba(56, 189, 248, 0.4)';
    }
  }

  // Handle Unfreeze action
  btnUnfreeze.addEventListener('click', async () => {
    if (!tab?.id) return;
    // Don't send messages to restricted chrome internal pages
    if (tab.url && (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://') || tab.url.startsWith('about:'))) {
      statusText.textContent = 'Open a web page to test';
      return;
    }
    statusText.textContent = 'Unfreezing field...';
    try {
      chrome.tabs.sendMessage(tab.id, { action: 'TRIGGER_UNFREEZE' }, (res) => {
        if (chrome.runtime.lastError) {
          statusText.textContent = 'Refresh page once to connect';
          return;
        }
        if (res?.success) {
          statusText.textContent = `Unblocked target: <${(res.target || 'input').toLowerCase()}>`;
        } else {
          statusText.textContent = 'No input element found';
        }
      });
    } catch (e) {
      statusText.textContent = 'Refresh page once to connect';
    }
  });

  // Handle Wispr Paste action
  btnWisprPaste.addEventListener('click', async () => {
    if (!tab?.id) return;
    if (tab.url && (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://') || tab.url.startsWith('about:'))) {
      statusText.textContent = 'Open a web page to test';
      return;
    }
    statusText.textContent = 'Pasting Wispr Flow transcript...';
    try {
      chrome.tabs.sendMessage(tab.id, { action: 'TRIGGER_WISPR_PASTE' }, (res) => {
        if (chrome.runtime.lastError) {
          statusText.textContent = 'Refresh page once to connect';
          return;
        }
        statusText.textContent = 'Transcript inserted!';
      });
    } catch (e) {
      statusText.textContent = 'Refresh page once to connect';
    }
  });

  // Save toggle changes
  toggleAIStudio.addEventListener('change', () => {
    chrome.storage.sync.set({ aiStudioAdapterEnabled: toggleAIStudio.checked });
  });

  toggleUniversal.addEventListener('change', () => {
    chrome.storage.sync.set({ universalHealerEnabled: toggleUniversal.checked });
  });

  toggleVisual.addEventListener('change', () => {
    chrome.storage.sync.set({ visualNotificationEnabled: toggleVisual.checked });
  });
});
