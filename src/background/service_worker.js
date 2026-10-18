// Service Worker for Input Healer & Wispr Flow Auto-Paster

chrome.runtime.onInstalled.addListener(() => {
  console.log('[Input Healer] Extension installed.');
  // Initialize default settings in storage
  chrome.storage.sync.set({
    universalHealerEnabled: true,
    aiStudioAdapterEnabled: true,
    autoCatchWisprEnabled: true,
    visualNotificationEnabled: true,
    sensitivity: 'medium'
  });
});

// Listen for keyboard command shortcuts
chrome.commands.onCommand.addListener(async (command) => {
  try {
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab || !activeTab.id) return;

    if (command === 'unfreeze_field') {
      chrome.tabs.sendMessage(activeTab.id, { action: 'TRIGGER_UNFREEZE' }).catch(() => {});
    } else if (command === 'quick_paste_wispr') {
      chrome.tabs.sendMessage(activeTab.id, { action: 'TRIGGER_WISPR_PASTE' }).catch(() => {});
    }
  } catch (err) {
    console.warn('[Input Healer] Command error:', err);
  }
});

// Relay messages between popup and content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'GET_TAB_INFO') {
    chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      sendResponse({ url: tab?.url || '' });
    });
    return true; // keep channel open
  }
});
