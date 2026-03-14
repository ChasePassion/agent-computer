importScripts("schemas.js");

const CONFIG = Object.freeze({
  websocketUrl: "__BROWSER_ASSIST_WS_URL__",
  daemonBaseUrl: "__BROWSER_ASSIST_DAEMON_BASE_URL__",
  keepaliveMs: 20 * 1000,
  reconnectBaseMs: 1000,
  reconnectMaxMs: 20 * 1000,
  reconnectAlarmName: "browser-assist-reconnect"
});

let socket = null;
let keepaliveTimer = null;
let reconnectAttempts = 0;
let resolvedWebSocketUrl = null;

function parseEnvelope(rawText) {
  return globalThis.BrowserAssistSchemas.parseEnvelope(rawText);
}

function buildEnvelope(type, payload, requestId = null) {
  return globalThis.BrowserAssistSchemas.buildEnvelope(type, payload, requestId);
}

function sendEnvelope(type, payload, requestId = null) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  socket.send(buildEnvelope(type, payload, requestId));
}

function stopKeepalive() {
  if (keepaliveTimer !== null) {
    clearInterval(keepaliveTimer);
    keepaliveTimer = null;
  }
}

function startKeepalive() {
  stopKeepalive();
  keepaliveTimer = setInterval(() => {
    sendEnvelope("keepalive", {});
  }, CONFIG.keepaliveMs);
}

function configuredDaemonBaseUrl() {
  if (CONFIG.daemonBaseUrl && !CONFIG.daemonBaseUrl.includes("__")) {
    return CONFIG.daemonBaseUrl;
  }
  return "http://127.0.0.1:37688";
}

function websocketBaseUrlForDaemon(daemonBaseUrl) {
  const parsed = new URL(daemonBaseUrl);
  const protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${parsed.host}`;
}

function clearResolvedWebSocketUrl() {
  resolvedWebSocketUrl = null;
}

function clearReconnectAlarm() {
  chrome.alarms.clear(CONFIG.reconnectAlarmName);
}

function scheduleReconnect() {
  const attempt = reconnectAttempts;
  const delay = Math.min(CONFIG.reconnectBaseMs * (2 ** attempt), CONFIG.reconnectMaxMs);
  const jitter = Math.floor(Math.random() * 300);
  chrome.alarms.create(CONFIG.reconnectAlarmName, { when: Date.now() + delay + jitter });
  reconnectAttempts += 1;
}

async function ensureContentScript(tabId) {
  try {
    const ping = await chrome.tabs.sendMessage(tabId, { type: "browser-assist:ping" });
    if (ping && ping.ok) {
      return;
    }
  } catch (_error) {
    // Fall through to injection.
  }

  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["schemas.js", "locator.js", "content_script.js"]
  });
}

async function locateInActiveTab(payload) {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || typeof tab.id !== "number") {
    throw new Error("No active browser tab is available for Browser Assist.");
  }

  if (!/^https?:/i.test(tab.url || "")) {
    throw new Error(`Unsupported Browser Assist tab URL: ${tab.url || "<empty>"}`);
  }

  await ensureContentScript(tab.id);

  const response = await chrome.tabs.sendMessage(tab.id, {
    type: "browser-assist:locate",
    payload
  });

  if (!response || !response.ok) {
    throw new Error(response?.error?.message || "Browser Assist content script did not return a valid response.");
  }

  return response.result;
}

async function handleServerMessage(event) {
  const envelope = parseEnvelope(event.data);
  if (envelope.type !== "locate") {
    return;
  }

  try {
    const result = await locateInActiveTab(envelope.payload);
    sendEnvelope("locate-result", result, envelope.requestId);
  } catch (error) {
    sendEnvelope(
      "error",
      { message: String(error && error.message ? error.message : error) },
      envelope.requestId
    );
  }
}

async function resolveWebSocketUrl() {
  if (resolvedWebSocketUrl) {
    return resolvedWebSocketUrl;
  }

  if (CONFIG.websocketUrl && !CONFIG.websocketUrl.includes("__")) {
    resolvedWebSocketUrl = CONFIG.websocketUrl;
    return resolvedWebSocketUrl;
  }

  const daemonBaseUrl = configuredDaemonBaseUrl();
  const response = await fetch(`${daemonBaseUrl}/browser-assist/status`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch Browser Assist status: HTTP ${response.status}`);
  }

  const payload = await response.json();
  if (!payload.token) {
    throw new Error("Browser Assist status did not return a token.");
  }

  resolvedWebSocketUrl = `${websocketBaseUrlForDaemon(daemonBaseUrl)}/ws/browser-assist?token=${encodeURIComponent(payload.token)}`;
  return resolvedWebSocketUrl;
}

async function connectWebSocket() {
  const websocketUrl = await resolveWebSocketUrl();

  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  socket = new WebSocket(websocketUrl);

  socket.onopen = () => {
    reconnectAttempts = 0;
    clearReconnectAlarm();
    sendEnvelope("hello", {
      extensionVersion: chrome.runtime.getManifest().version,
      browserName: "chromium",
      browserVersion: navigator.userAgent
    });
    startKeepalive();
  };

  socket.onmessage = (event) => {
    handleServerMessage(event).catch((error) => {
      console.error("Browser Assist failed to process websocket message:", error);
    });
  };

  socket.onerror = () => {
    clearResolvedWebSocketUrl();
    if (socket) {
      socket.close();
    }
  };

  socket.onclose = () => {
    socket = null;
    stopKeepalive();
    clearResolvedWebSocketUrl();
    scheduleReconnect();
  };
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== CONFIG.reconnectAlarmName) {
    return;
  }

  connectWebSocket().catch((error) => {
    console.error("Browser Assist failed to reconnect websocket:", error);
    scheduleReconnect();
  });
});

chrome.runtime.onInstalled.addListener(() => {
  connectWebSocket().catch((error) => {
    console.error("Browser Assist failed to connect on install:", error);
    scheduleReconnect();
  });
});

chrome.runtime.onStartup.addListener(() => {
  connectWebSocket().catch((error) => {
    console.error("Browser Assist failed to connect on startup:", error);
    scheduleReconnect();
  });
});

connectWebSocket().catch((error) => {
  console.error("Browser Assist failed to establish websocket connection:", error);
  scheduleReconnect();
});
