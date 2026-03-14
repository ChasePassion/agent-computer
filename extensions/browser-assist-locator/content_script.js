(function () {
  if (globalThis.__browserAssistContentScriptInstalled) {
    return;
  }

  globalThis.__browserAssistContentScriptInstalled = true;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    (async () => {
      if (!message || typeof message !== "object") {
        sendResponse({ ok: false, error: { message: "Invalid Browser Assist message." } });
        return;
      }

      if (message.type === "browser-assist:ping") {
        sendResponse({ ok: true, pageUrl: window.location.href, pageTitle: document.title });
        return;
      }

      if (message.type === "browser-assist:locate") {
        const request = globalThis.BrowserAssistSchemas.normalizeLocateRequest(message.payload);
        const result = globalThis.BrowserAssistLocator.locate(request);
        sendResponse({ ok: true, result });
        return;
      }

      sendResponse({ ok: false, error: { message: `Unsupported Browser Assist message type: ${message.type}` } });
    })().catch((error) => {
      sendResponse({
        ok: false,
        error: { message: String(error && error.message ? error.message : error) }
      });
    });

    return true;
  });
})();
