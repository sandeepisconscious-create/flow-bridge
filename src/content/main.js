// Main Content Script entry point

(function() {
  // 1. Inject page-level engine script
  try {
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL('src/injected/page_engine.js');
    script.onload = () => script.remove();
    (document.head || document.documentElement).appendChild(script);
  } catch (err) {
    console.warn('[Input Healer] Could not inject page script:', err);
  }

  // 2. Initialize modules
  Detector.init();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      AIStudioAdapter.init();
    });
  } else {
    AIStudioAdapter.init();
  }

  // 3. Listen for commands and messages from background service worker or popup
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'TRIGGER_UNFREEZE') {
      const target = Detector.getCurrentTarget();
      if (target) {
        UniversalHealer.reviveElement(target);
        sendResponse({ success: true, target: target.tagName });
      } else {
        Utils.showNotification('No input field found', 'warning');
        sendResponse({ success: false });
      }
    } else if (request.action === 'TRIGGER_WISPR_PASTE') {
      if (AIStudioAdapter.isAIStudio()) {
        AIStudioAdapter.pasteWisprFlowText();
        sendResponse({ success: true });
      } else {
        // Universal clipboard insert into whatever is active
        const target = Detector.getCurrentTarget();
        if (target) {
          Utils.readClipboard().then(text => {
            if (text) {
              UniversalHealer.insertTextDirectly(target, text);
              Utils.showNotification('Pasted from clipboard', 'success');
            }
          });
        }
        sendResponse({ success: true });
      }
    }
    return true;
  });

  console.log('[Input Healer] Active and monitoring input fields.');
})();
