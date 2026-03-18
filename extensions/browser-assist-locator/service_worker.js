importScripts("schemas.js");

const CONFIG = Object.freeze({
  websocketUrl: "__BROWSER_ASSIST_WS_URL__",
  daemonBaseUrl: "__BROWSER_ASSIST_DAEMON_BASE_URL__",
  keepaliveMs: 20 * 1000,
  reconnectBaseMs: 1000,
  reconnectMaxMs: 20 * 1000,
  reconnectAlarmName: "browser-assist-reconnect"
});

const RETRY = Object.freeze({
  RETRY_SAME_TARGET: "retry_same_target",
  REACQUIRE_TARGET: "reacquire_target",
  CONTEXT_LOST: "context_lost",
  FAIL_FAST: "fail_fast"
});

let socket = null;
let keepaliveTimer = null;
let reconnectAttempts = 0;
let resolvedWebSocketUrl = null;
let connectPromise = null;
const tabSessions = new Map();
const tabIdToSessionId = new Map();

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

function isSupportedTabUrl(url) {
  return /^https?:/i.test(String(url || ""));
}

function normalizeInteger(value, fallback = null) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function extensionError(message, retryDisposition) {
  const error = new Error(message);
  error.retryDisposition = retryDisposition;
  return error;
}

function serializeError(error) {
  return {
    message: String(error && error.message ? error.message : error || "Unknown Browser Assist error"),
    retryDisposition: typeof error?.retryDisposition === "string" ? error.retryDisposition : RETRY.FAIL_FAST
  };
}

function cloneSession(session) {
  return session ? { ...session } : null;
}

function configuredDaemonBaseUrl() {
  if (CONFIG.daemonBaseUrl && !CONFIG.daemonBaseUrl.includes("__")) {
    return CONFIG.daemonBaseUrl;
  }
  return "http://127.0.0.1:37688";
}

function websocketBaseUrlForDaemon(daemonBaseUrl) {
  const parsed = new URL(daemonBaseUrl);
  return `${parsed.protocol === "https:" ? "wss:" : "ws:"}//${parsed.host}`;
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

function scheduleReconnect() {
  const delay = Math.min(CONFIG.reconnectBaseMs * (2 ** reconnectAttempts), CONFIG.reconnectMaxMs);
  chrome.alarms.create(CONFIG.reconnectAlarmName, { when: Date.now() + delay + Math.floor(Math.random() * 300) });
  reconnectAttempts += 1;
}

function clearReconnectAlarm() {
  chrome.alarms.clear(CONFIG.reconnectAlarmName);
}

async function findBestActiveTab() {
  const lastFocusedWindow = await chrome.windows.getLastFocused({ populate: true });
  const focusedTabs = Array.isArray(lastFocusedWindow?.tabs) ? lastFocusedWindow.tabs : [];
  const active = focusedTabs.find((tab) => tab.active && isSupportedTabUrl(tab.url));
  if (active) {
    return active;
  }
  const queried = await chrome.tabs.query({ active: true });
  return queried.find((tab) => isSupportedTabUrl(tab.url)) || null;
}

async function ensureContentScript(tabId) {
  try {
    const ping = await chrome.tabs.sendMessage(tabId, { type: "browser-assist:ping" });
    if (ping?.ok) {
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

async function readTabState(tabId) {
  await ensureContentScript(tabId);
  const response = await chrome.tabs.sendMessage(tabId, { type: "browser-assist:ping" });
  if (!response?.ok) {
    throw extensionError("Browser Assist content script did not return page state.", RETRY.FAIL_FAST);
  }
  return {
    url: response.pageUrl || null,
    title: response.pageTitle || null,
    frameId: normalizeInteger(response.frameId, 0),
    documentEpoch: normalizeInteger(response.documentEpoch, 0) || 0
  };
}

function ensureSessionId(tabId) {
  const existing = tabIdToSessionId.get(tabId);
  if (existing) {
    return existing;
  }
  const sessionId = `tab-session-${crypto.randomUUID()}`;
  tabIdToSessionId.set(tabId, sessionId);
  return sessionId;
}

async function ensureTabSession(tab) {
  if (!tab || typeof tab.id !== "number") {
    throw extensionError("context_lost: No browser tab is available.", RETRY.CONTEXT_LOST);
  }
  if (!isSupportedTabUrl(tab.url)) {
    throw extensionError(`context_lost: Unsupported tab URL: ${tab.url || "<empty>"}`, RETRY.CONTEXT_LOST);
  }

  const page = await readTabState(tab.id);
  const session = {
    tabSessionId: ensureSessionId(tab.id),
    tabId: tab.id,
    frameId: page.frameId,
    windowId: typeof tab.windowId === "number" ? tab.windowId : null,
    url: page.url || tab.url || null,
    title: page.title || tab.title || null,
    documentEpoch: page.documentEpoch
  };
  tabSessions.set(session.tabSessionId, session);
  return cloneSession(session);
}

function removeSession(tabId) {
  const sessionId = tabIdToSessionId.get(tabId);
  if (!sessionId) {
    return;
  }
  tabIdToSessionId.delete(tabId);
  tabSessions.delete(sessionId);
}

async function resolveKnownSession(tabSessionId) {
  const known = tabSessions.get(tabSessionId);
  if (!known) {
    return null;
  }
  try {
    const tab = await chrome.tabs.get(known.tabId);
    if (!tab || !isSupportedTabUrl(tab.url)) {
      removeSession(known.tabId);
      return null;
    }
    return { tab, session: await ensureTabSession(tab) };
  } catch (_error) {
    removeSession(known.tabId);
    return null;
  }
}

async function captureActiveSession() {
  const tab = await findBestActiveTab();
  if (!tab) {
    return null;
  }
  return ensureTabSession(tab);
}

async function publishSessionState(reason) {
  try {
    const session = await captureActiveSession();
    if (!session) {
      return;
    }
    sendEnvelope("session-state", { reason, session });
  } catch (_error) {
    // Best-effort only.
  }
}

function requestedSessionId(payload) {
  return String(payload?.tabSessionId || payload?.nodeRef?.tabSessionId || "").trim();
}

async function resolveTarget(payload) {
  const explicitSessionId = requestedSessionId(payload);
  if (explicitSessionId) {
    const resolved = await resolveKnownSession(explicitSessionId);
    if (!resolved) {
      throw extensionError(`context_lost: Browser Assist tab session ${explicitSessionId} is unavailable.`, RETRY.CONTEXT_LOST);
    }
    return { ...resolved, requestedSessionId: explicitSessionId };
  }

  const session = await captureActiveSession();
  if (!session) {
    throw extensionError("context_lost: No Browser Assist tab session is available.", RETRY.CONTEXT_LOST);
  }
  const tab = await chrome.tabs.get(session.tabId);
  return { tab, session, requestedSessionId: "" };
}

function attachNodeRef(nodeRef, session) {
  if (!nodeRef || typeof nodeRef !== "object") {
    return nodeRef;
  }
  return {
    ...nodeRef,
    tabSessionId: session.tabSessionId,
    frameId: session.frameId ?? 0,
    documentEpoch: session.documentEpoch
  };
}

function attachActionability(actionability, sameSession) {
  if (!actionability || typeof actionability !== "object") {
    return actionability;
  }
  return { ...actionability, sameSession };
}

function applyLocateContext(result, session, requestedId) {
  const context = {
    ...session,
    url: result?.page?.url || session.url,
    title: result?.page?.title || session.title,
    documentEpoch: normalizeInteger(result?.page?.documentEpoch, session.documentEpoch) || session.documentEpoch
  };
  tabSessions.set(context.tabSessionId, context);
  const sameSession = !requestedId || requestedId === context.tabSessionId;
  const matches = Array.isArray(result?.matches)
    ? result.matches.map((match) => ({
      ...match,
      nodeRef: attachNodeRef(match.nodeRef, context),
      actionability: attachActionability(match.actionability, sameSession)
    }))
    : [];
  return {
    ...result,
    context,
    page: { ...(result?.page || {}), url: context.url, title: context.title, documentEpoch: context.documentEpoch },
    matchCount: matches.length,
    matches
  };
}

function applyObservationContext(result, session, requestedId) {
  const sameSession = !requestedId || requestedId === session.tabSessionId;
  const observation = {
    ...(result?.observation || {}),
    nodeRef: attachNodeRef(result?.observation?.nodeRef, session),
    actionability: attachActionability(result?.observation?.actionability, sameSession)
  };
  return { context: session, observation };
}

function applyActContext(result, session, requestedId) {
  const sameSession = !requestedId || requestedId === session.tabSessionId;
  return {
    ...result,
    context: session,
    nodeRef: attachNodeRef(result?.nodeRef, session),
    actionability: attachActionability(result?.actionability, sameSession)
  };
}

function assertActionability(actionability, action) {
  if (!actionability?.attached) {
    throw extensionError("Target is no longer attached.", RETRY.REACQUIRE_TARGET);
  }
  if (!actionability?.visible || !actionability?.notOccluded || !actionability?.enabled || !actionability?.stable) {
    throw extensionError("Target failed pre-action gates.", RETRY.FAIL_FAST);
  }
  if (action === "type" && actionability?.editable !== true) {
    throw extensionError("Target is not editable.", RETRY.FAIL_FAST);
  }
}

function messageChannelClosed(error) {
  const text = String(error?.message || error || "").toLowerCase();
  return (
    text.includes("back/forward cache") ||
    text.includes("message channel is closed") ||
    text.includes("message port closed") ||
    text.includes("closed before a response was received") ||
    text.includes("receiving end does not exist")
  );
}

async function withDebugger(tabId, callback) {
  const target = { tabId };
  let attached = false;

  try {
    await chrome.debugger.attach(target, "1.3");
    attached = true;
  } catch (error) {
    const message = String(error?.message || error || "");
    if (!message.includes("already attached")) {
      throw error;
    }
  }

  try {
    return await callback(target);
  } finally {
    if (attached) {
      try {
        await chrome.debugger.detach(target);
      } catch (_error) {
        // Ignore detach failures.
      }
    }
  }
}

async function dispatchTrustedClick(tabId, point) {
  await withDebugger(tabId, async (target) => {
    const base = {
      x: point.x,
      y: point.y,
      clickCount: 1
    };

    await chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
      ...base,
      type: "mouseMoved",
      button: "none",
      buttons: 0
    });
    await chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
      ...base,
      type: "mousePressed",
      button: "left",
      buttons: 1
    });
    await chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
      ...base,
      type: "mouseReleased",
      button: "left",
      buttons: 0
    });
  });
}

async function dispatchToContentScript(tabId, type, payload) {
  await ensureContentScript(tabId);
  const response = await chrome.tabs.sendMessage(tabId, { type, payload });
  if (!response?.ok) {
    throw extensionError(response?.error?.message || `Browser Assist content script did not return a valid ${type} response.`, RETRY.FAIL_FAST);
  }
  return response.result;
}

function normalizeUrlVerify(verify, expectedUrl = "") {
  if (verify && typeof verify === "object" && verify.kind === "url_changed") {
    return verify;
  }
  return {
    kind: "url_changed",
    timeoutMs: 2000,
    pollIntervalMs: 100,
    params: expectedUrl ? { expectedUrl } : {}
  };
}

async function waitForUrlVerification(tabId, verify, baselineUrl) {
  const effectiveVerify = normalizeUrlVerify(verify);
  const deadline = Date.now() + (normalizeInteger(effectiveVerify.timeoutMs, 2000) || 2000);
  let currentUrl = baselineUrl;

  while (true) {
    const currentTab = await chrome.tabs.get(tabId);
    currentUrl = currentTab?.url || currentUrl;
    const expectedUrl = String(effectiveVerify?.params?.expectedUrl || "").trim();
    const urlContains = String(effectiveVerify?.params?.urlContains || "").trim();
    const verified = expectedUrl
      ? currentUrl === expectedUrl
      : (urlContains ? currentUrl.includes(urlContains) : (baselineUrl && currentUrl !== baselineUrl));
    if (verified) {
      return {
        currentTab,
        verified: true,
        retryDisposition: RETRY.FAIL_FAST,
        failureReason: null,
        observation: {
          baselineUrl,
          currentUrl
        }
      };
    }
    if (Date.now() >= deadline) {
      return {
        currentTab,
        verified: false,
        retryDisposition: RETRY.RETRY_SAME_TARGET,
        failureReason: "Verification timed out for url_changed.",
        observation: {
          baselineUrl,
          currentUrl
        }
      };
    }
    await new Promise((resolve) => setTimeout(resolve, normalizeInteger(effectiveVerify.pollIntervalMs, 100) || 100));
  }
}

async function refreshSessionFromTab(tabId, session) {
  try {
    const currentTab = await chrome.tabs.get(tabId);
    if (currentTab && isSupportedTabUrl(currentTab.url)) {
      return await ensureTabSession(currentTab);
    }
  } catch (_error) {
    // Fall back to the previous session snapshot.
  }

  return cloneSession(session);
}

function normalizeLocateVerifyPayload(verify) {
  const query = verify?.params?.query && typeof verify.params.query === "object"
    ? verify.params.query
    : (verify?.params?.text ? { text: String(verify.params.text), role: "any", hint: null } : null);
  if (!query) {
    throw extensionError(`Verify spec ${verify?.kind || "<empty>"} requires params.query or params.text.`, RETRY.FAIL_FAST);
  }

  return {
    query,
    options: verify?.params?.options && typeof verify.params.options === "object"
      ? verify.params.options
      : { visibleOnly: true, interactiveOnly: false, maxCandidates: 5 }
  };
}

async function runPostClickVerification(tab, session, payload, preparedObservation) {
  const verify = payload?.verify;
  if (!verify || typeof verify !== "object") {
    return {
      verified: true,
      retryDisposition: RETRY.FAIL_FAST,
      failureReason: null,
      observation: { verificationSkipped: true },
      navigation: false
    };
  }

  if (verify.kind === "url_changed") {
    const verification = await waitForUrlVerification(tab.id, verify, session.url || tab.url || null);
    return {
      ...verification,
      navigation: verification.verified && verification.observation.currentUrl !== verification.observation.baselineUrl
    };
  }

  const deadline = Date.now() + (normalizeInteger(verify.timeoutMs, 2000) || 2000);
  const pollIntervalMs = normalizeInteger(verify.pollIntervalMs, 100) || 100;
  let lastObservation = null;

  while (true) {
    if (verify.kind === "text_changed" || verify.kind === "selection_changed") {
      const observed = await dispatchToContentScript(tab.id, "browser-assist:observe", { nodeRef: payload.nodeRef });
      if (verify.kind === "text_changed") {
        const currentText = observed?.observation?.text ?? null;
        const expectedText = String(verify?.params?.expectedText || "").trim();
        lastObservation = {
          baselineText: preparedObservation.text ?? null,
          currentText
        };
        if ((expectedText && currentText === expectedText) || (!expectedText && currentText !== null && currentText !== preparedObservation.text)) {
          return {
            verified: true,
            retryDisposition: RETRY.FAIL_FAST,
            failureReason: null,
            observation: lastObservation,
            navigation: false
          };
        }
      } else {
        const currentSelected = observed?.observation?.selected;
        const expectedSelected = typeof verify?.params?.selected === "boolean" ? verify.params.selected : null;
        lastObservation = {
          baselineSelected: preparedObservation.selected ?? null,
          currentSelected
        };
        if ((expectedSelected !== null && currentSelected === expectedSelected) || (expectedSelected === null && currentSelected !== null && currentSelected !== preparedObservation.selected)) {
          return {
            verified: true,
            retryDisposition: RETRY.FAIL_FAST,
            failureReason: null,
            observation: lastObservation,
            navigation: false
          };
        }
      }
    } else {
      const locatePayload = normalizeLocateVerifyPayload(verify);
      const located = await dispatchToContentScript(tab.id, "browser-assist:locate", locatePayload);
      lastObservation = { matchCount: located?.matchCount || 0 };
      const matched = verify.kind === "element_disappeared"
        ? lastObservation.matchCount === 0
        : lastObservation.matchCount > 0;
      if (matched) {
        return {
          verified: true,
          retryDisposition: RETRY.FAIL_FAST,
          failureReason: null,
          observation: lastObservation,
          navigation: false
        };
      }
    }

    if (Date.now() >= deadline) {
      return {
        verified: false,
        retryDisposition: RETRY.RETRY_SAME_TARGET,
        failureReason: `Verification timed out for ${verify.kind}.`,
        observation: lastObservation,
        navigation: false
      };
    }

    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }
}

async function navigateInTab(tab, session, payload, requestedId) {
  const baselineUrl = session.url || tab.url || null;
  await chrome.tabs.update(tab.id, { url: payload.url });

  const verification = await waitForUrlVerification(
    tab.id,
    normalizeUrlVerify(payload.verify, payload.url),
    baselineUrl
  );
  const nextSession = verification.verified
    ? await refreshSessionFromTab(tab.id, session)
    : cloneSession(session);

  return {
    context: nextSession,
    action: "navigate",
    nodeRef: null,
    actionability: null,
    verified: verification.verified,
    retryDisposition: verification.retryDisposition,
    failureReason: verification.failureReason,
    observation: verification.observation
  };
}

async function recoverNavigationAct(tab, session, payload, error) {
  const baselineUrl = session.url || tab.url || null;
  const verification = await waitForUrlVerification(
    tab.id,
    normalizeUrlVerify(payload.verify),
    baselineUrl
  );
  const nextSession = verification.verified
    ? await refreshSessionFromTab(tab.id, session)
    : cloneSession(session);

  return {
    context: nextSession,
    action: payload.action,
    nodeRef: null,
    actionability: null,
    verified: verification.verified,
    retryDisposition: verification.retryDisposition,
    failureReason: verification.failureReason,
    observation: {
      ...verification.observation,
      recoveredFrom: String(error?.message || error || "")
    }
  };
}

async function clickInTab(tab, session, payload, requestedId) {
  const prepared = await dispatchToContentScript(tab.id, "browser-assist:observe", { nodeRef: payload.nodeRef });
  const observation = prepared?.observation || {};
  if (!observation.exists) {
    throw extensionError("Target could not be resolved for click.", RETRY.REACQUIRE_TARGET);
  }
  if (!observation.clickablePoint) {
    throw extensionError("Target did not provide a clickable point.", RETRY.FAIL_FAST);
  }

  assertActionability(observation.actionability, "click");
  await dispatchTrustedClick(tab.id, observation.clickablePoint);

  const verification = await runPostClickVerification(tab, session, payload, observation);
  const nextSession = verification.navigation
    ? await refreshSessionFromTab(tab.id, session)
    : cloneSession(session);
  const sameSession = !requestedId || requestedId === nextSession.tabSessionId;

  return {
    context: nextSession,
    action: "click",
    nodeRef: verification.navigation ? null : attachNodeRef(observation.nodeRef, nextSession),
    actionability: verification.navigation ? null : attachActionability(observation.actionability, sameSession),
    verified: verification.verified,
    retryDisposition: verification.retryDisposition,
    failureReason: verification.failureReason,
    observation: verification.observation
  };
}

async function runCommand(type, payload) {
  const { tab, session, requestedSessionId } = await resolveTarget(payload);

  if (type === "locate") {
    return applyLocateContext(await dispatchToContentScript(tab.id, "browser-assist:locate", payload), session, requestedSessionId);
  }

  if (type === "observe") {
    return applyObservationContext(await dispatchToContentScript(tab.id, "browser-assist:observe", payload), session, requestedSessionId);
  }

  if (type === "act") {
    if (payload?.action === "navigate") {
      return navigateInTab(tab, session, payload, requestedSessionId);
    }
    if (payload?.action === "click") {
      return clickInTab(tab, session, payload, requestedSessionId);
    }
    try {
      return applyActContext(await dispatchToContentScript(tab.id, "browser-assist:act", payload), session, requestedSessionId);
    } catch (error) {
      if (payload?.action === "click" && messageChannelClosed(error)) {
        return await recoverNavigationAct(tab, session, payload, error);
      }
      throw error;
    }
  }

  throw extensionError(`Unsupported Browser Assist command: ${type}`, RETRY.FAIL_FAST);
}

async function handleServerMessage(event) {
  const envelope = parseEnvelope(event.data);
  if (envelope.type !== "locate" && envelope.type !== "observe" && envelope.type !== "act") {
    return;
  }

  try {
    const result = await runCommand(envelope.type, envelope.payload);
    sendEnvelope(`${envelope.type}-result`, result, envelope.requestId);
  } catch (error) {
    sendEnvelope("error", serializeError(error), envelope.requestId);
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

  const response = await fetch(`${configuredDaemonBaseUrl()}/browser-assist/status`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch Browser Assist status: HTTP ${response.status}`);
  }
  const payload = await response.json();
  resolvedWebSocketUrl = `${websocketBaseUrlForDaemon(configuredDaemonBaseUrl())}/ws/browser-assist?token=${encodeURIComponent(payload.token)}`;
  return resolvedWebSocketUrl;
}

async function connectWebSocket() {
  if (connectPromise) {
    return connectPromise;
  }

  connectPromise = (async () => {
    const websocketUrl = await resolveWebSocketUrl();
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    socket = new WebSocket(websocketUrl);
    socket.onopen = () => {
      reconnectAttempts = 0;
      clearReconnectAlarm();
      startKeepalive();
      captureActiveSession().catch(() => null).then((activeSession) => {
        sendEnvelope("hello", {
          extensionVersion: chrome.runtime.getManifest().version,
          browserName: "chromium",
          browserVersion: navigator.userAgent,
          activeSession
        });
      });
    };
    socket.onmessage = (event) => {
      handleServerMessage(event).catch(() => {
        // Errors are converted into websocket payloads.
      });
    };
    socket.onerror = () => {
      if (socket) {
        socket.close();
      }
    };
    socket.onclose = () => {
      socket = null;
      stopKeepalive();
      resolvedWebSocketUrl = null;
      scheduleReconnect();
    };
  })();

  try {
    await connectPromise;
  } finally {
    connectPromise = null;
  }
}

function ensureConnected(reason) {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  connectWebSocket().catch(() => {
    scheduleReconnect();
  });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === CONFIG.reconnectAlarmName) {
    ensureConnected("alarms.onAlarm");
  }
});

chrome.runtime.onInstalled.addListener(() => ensureConnected("runtime.onInstalled"));
chrome.runtime.onStartup.addListener(() => ensureConnected("runtime.onStartup"));
chrome.tabs.onActivated.addListener(() => {
  ensureConnected("tabs.onActivated");
  publishSessionState("tabs.onActivated");
});
chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && isSupportedTabUrl(tab?.url)) {
    ensureConnected("tabs.onUpdated");
    publishSessionState("tabs.onUpdated");
  }
});
chrome.tabs.onRemoved.addListener((tabId) => {
  removeSession(tabId);
});
chrome.windows.onFocusChanged.addListener((windowId) => {
  if (windowId !== chrome.windows.WINDOW_ID_NONE) {
    ensureConnected("windows.onFocusChanged");
    publishSessionState("windows.onFocusChanged");
  }
});

ensureConnected("bootstrap");
