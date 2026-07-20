importScripts("protocol.js", "schemas.js");

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
const protocol = globalThis.BrowserAssistProtocol;

let socket = null;
let keepaliveTimer = null;
let reconnectAttempts = 0;
let resolvedWebSocketUrl = null;
let connectPromise = null;
const tabSessions = new Map();
const tabIdToSessionId = new Map();
const tabActionQueue = protocol.createKeyedSerialQueue();
const tabDebuggerQueue = protocol.createKeyedSerialQueue();

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
    if (ping?.ok && ping.documentId && ping.pageNonce) {
      return;
    }
    if (ping?.ok) {
      throw extensionError("Browser Assist page runtime is stale; reload the tab before reusing nodeRef values.", RETRY.REACQUIRE_TARGET);
    }
  } catch (_error) {
    if (_error?.retryDisposition) {
      throw _error;
    }
    // Fall through to injection.
  }

  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["protocol.js", "schemas.js", "locator.js", "content_script.js"]
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
    documentEpoch: normalizeInteger(response.documentEpoch, 0) || 0,
    documentId: String(response.documentId || response.pageState?.documentId || "").trim() || null,
    pageNonce: String(response.pageNonce || response.pageState?.pageNonce || "").trim() || null,
    viewportWidth: normalizeInteger(response.pageState?.viewportWidth, 0) || 0,
    viewportHeight: normalizeInteger(response.pageState?.viewportHeight, 0) || 0
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
    documentEpoch: page.documentEpoch,
    documentId: page.documentId,
    pageNonce: page.pageNonce
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
    frameId: nodeRef.frameId ?? session.frameId ?? 0,
    documentEpoch: normalizeInteger(nodeRef.documentEpoch, session.documentEpoch) ?? session.documentEpoch,
    documentId: nodeRef.documentId || session.documentId || null,
    pageNonce: nodeRef.pageNonce || session.pageNonce || null
  };
}

function assertNodeRefDocument(nodeRef, session) {
  if (!nodeRef || typeof nodeRef !== "object") {
    throw extensionError("Missing nodeRef.", RETRY.FAIL_FAST);
  }
  if (!protocol.nodeRefMatchesDocument(nodeRef, session, session.documentEpoch)) {
    throw extensionError("nodeRef belongs to a different top-level document.", RETRY.REACQUIRE_TARGET);
  }
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
    documentEpoch: normalizeInteger(result?.page?.documentEpoch, session.documentEpoch) || session.documentEpoch,
    documentId: String(result?.page?.documentId || session.documentId || "").trim() || null,
    pageNonce: String(result?.page?.pageNonce || session.pageNonce || "").trim() || null
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
    page: {
      ...(result?.page || {}),
      url: context.url,
      title: context.title,
      documentEpoch: context.documentEpoch,
      documentId: context.documentId,
      pageNonce: context.pageNonce
    },
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

async function withDebugger(tabId, callback) {
  return tabDebuggerQueue.run(tabId, async () => {
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
  });
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

async function dispatchTrustedText(tabId, text) {
  await withDebugger(tabId, async (target) => {
    const selectAll = {
      key: "a",
      code: "KeyA",
      modifiers: 2,
      windowsVirtualKeyCode: 65,
      nativeVirtualKeyCode: 65
    };
    await chrome.debugger.sendCommand(target, "Input.dispatchKeyEvent", {
      ...selectAll,
      type: "keyDown"
    });
    await chrome.debugger.sendCommand(target, "Input.dispatchKeyEvent", {
      ...selectAll,
      type: "keyUp"
    });
    await chrome.debugger.sendCommand(target, "Input.insertText", { text: String(text || "") });
  });
}

function normalizeText(value) {
  return String(value || "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function axValue(value) {
  return value && typeof value === "object" && "value" in value ? value.value : null;
}

function axProperty(node, name) {
  const property = Array.isArray(node?.properties)
    ? node.properties.find((item) => item?.name === name)
    : null;
  return axValue(property?.value);
}

function axSelectedState(node) {
  for (const name of ["selected", "checked", "pressed"]) {
    const value = axProperty(node, name);
    if (typeof value === "boolean") {
      return value;
    }
    if (value === "true" || value === "mixed") {
      return true;
    }
    if (value === "false") {
      return false;
    }
  }
  return null;
}

function axNodeSnapshot(node) {
  return {
    backendNodeId: normalizeInteger(node?.backendDOMNodeId),
    ignored: Boolean(node?.ignored),
    name: normalizeText(axValue(node?.name)),
    value: normalizeText(axValue(node?.value)),
    role: normalizeText(axValue(node?.role)).toLowerCase() || "any",
    disabled: axProperty(node, "disabled") === true,
    editable: axProperty(node, "editable") !== null,
    selected: axSelectedState(node)
  };
}

function accessibilityMatchScore(snapshot, query) {
  if (!snapshot.backendNodeId || snapshot.ignored || !protocol.roleMatches(query?.role, snapshot.role)) {
    return 0;
  }
  const textNeedle = normalizeText(query?.text);
  if (textNeedle && !snapshot.name.toLowerCase().includes(textNeedle.toLowerCase())) {
    return 0;
  }
  let score = protocol.roleMatches(query?.role, snapshot.role) ? 4 : 0;
  if (textNeedle && snapshot.name.toLowerCase() === textNeedle.toLowerCase()) {
    score += 10;
  } else if (textNeedle) {
    score += 6;
  }
  const hint = normalizeText(query?.hint);
  if (hint && snapshot.name.toLowerCase().includes(hint.toLowerCase())) {
    score += 3;
  }
  return score;
}

function flattenFrameIds(frameTree, target = []) {
  const frameId = String(frameTree?.frame?.id || "").trim();
  if (frameId) {
    target.push(frameId);
  }
  for (const child of frameTree?.childFrames || []) {
    flattenFrameIds(child, target);
  }
  return target;
}

function rectFromQuad(quad) {
  if (!Array.isArray(quad) || quad.length < 8) {
    return null;
  }
  const xs = [quad[0], quad[2], quad[4], quad[6]].map(Number);
  const ys = [quad[1], quad[3], quad[5], quad[7]].map(Number);
  if ([...xs, ...ys].some((value) => !Number.isFinite(value))) {
    return null;
  }
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  return {
    left: Math.round(left),
    top: Math.round(top),
    width: Math.round(Math.max(0, right - left)),
    height: Math.round(Math.max(0, bottom - top)),
    right: Math.round(right),
    bottom: Math.round(bottom)
  };
}

function visibleRectForViewport(rect, page) {
  const viewportWidth = Math.max(0, normalizeInteger(page?.viewportWidth, 0) || 0);
  const viewportHeight = Math.max(0, normalizeInteger(page?.viewportHeight, 0) || 0);
  const left = Math.max(0, Math.min(viewportWidth, rect.left));
  const right = Math.max(0, Math.min(viewportWidth, rect.right));
  const top = Math.max(0, Math.min(viewportHeight, rect.top));
  const bottom = Math.max(0, Math.min(viewportHeight, rect.bottom));
  return {
    left: Math.round(left),
    top: Math.round(top),
    width: Math.round(Math.max(0, right - left)),
    height: Math.round(Math.max(0, bottom - top)),
    right: Math.round(right),
    bottom: Math.round(bottom)
  };
}

async function accessibilityPointOwnership(target, backendNodeId, point) {
  try {
    const hit = await chrome.debugger.sendCommand(target, "DOM.getNodeForLocation", {
      x: point.x,
      y: point.y,
      includeUserAgentShadowDOM: true,
      ignorePointerEventsNone: true
    });
    const hitBackendNodeId = normalizeInteger(hit?.backendNodeId);
    if (!hitBackendNodeId) {
      return false;
    }
    if (hitBackendNodeId === backendNodeId) {
      return true;
    }
    const ancestors = await chrome.debugger.sendCommand(target, "Accessibility.getAXNodeAndAncestors", {
      backendNodeId: hitBackendNodeId
    });
    return (ancestors?.nodes || []).some((node) => normalizeInteger(node?.backendDOMNodeId) === backendNodeId);
  } catch (_error) {
    return null;
  }
}

async function sampleAccessibilityBox(target, candidate, page) {
  try {
    const result = await chrome.debugger.sendCommand(target, "DOM.getBoxModel", {
      backendNodeId: candidate.snapshot.backendNodeId
    });
    const rect = rectFromQuad(result?.model?.border || result?.model?.content);
    if (!rect) {
      return null;
    }
    const visibleRect = visibleRectForViewport(rect, page);
    const point = {
      x: Math.round(visibleRect.left + visibleRect.width / 2),
      y: Math.round(visibleRect.top + visibleRect.height / 2)
    };
    const pointOwned = visibleRect.width > 0 && visibleRect.height > 0
      ? await accessibilityPointOwnership(target, candidate.snapshot.backendNodeId, point)
      : false;
    return {
      rect,
      visibleRect,
      attached: true,
      visible: rect.width > 0 && rect.height > 0 && visibleRect.width > 0 && visibleRect.height > 0,
      notOccluded: pointOwned !== false,
      occlusionChecked: pointOwned !== null
    };
  } catch (_error) {
    return null;
  }
}

async function waitForDebuggerAnimationFrame(target) {
  try {
    await chrome.debugger.sendCommand(target, "Runtime.evaluate", {
      expression: "new Promise(resolve => requestAnimationFrame(() => resolve(true)))",
      awaitPromise: true,
      returnByValue: true
    });
  } catch (_error) {
    // A second box-model batch is still useful if the frame cannot evaluate script.
  }
}

async function collectAccessibilityCandidates(target, payload, page) {
  await chrome.debugger.sendCommand(target, "Accessibility.enable");
  const frameTreeResult = await chrome.debugger.sendCommand(target, "Page.getFrameTree");
  const frameIds = flattenFrameIds(frameTreeResult?.frameTree);
  const candidates = [];
  const seen = new Set();
  let order = 0;

  for (const frameId of frameIds) {
    let tree;
    try {
      tree = await chrome.debugger.sendCommand(target, "Accessibility.getFullAXTree", { frameId });
    } catch (_error) {
      continue;
    }
    for (const node of tree?.nodes || []) {
      const snapshot = axNodeSnapshot(node);
      const score = accessibilityMatchScore(snapshot, payload?.query || {});
      const key = `${frameId}:${snapshot.backendNodeId || 0}`;
      if (score <= 0 || seen.has(key)) {
        continue;
      }
      seen.add(key);
      candidates.push({ frameId, order: order++, score, snapshot });
    }
  }

  candidates.sort((left, right) => right.score - left.score || left.order - right.order);
  const firstSamples = await Promise.all(candidates.map((candidate) => sampleAccessibilityBox(target, candidate, page)));
  const firstPass = candidates.filter((candidate, index) => {
    candidate.firstSample = firstSamples[index];
    return Boolean(
      candidate.firstSample &&
      (!payload?.options?.visibleOnly || candidate.firstSample.visible) &&
      (!payload?.options?.interactiveOnly || protocol.isInteractiveRole(candidate.snapshot.role))
    );
  });
  if (firstPass.length > 0) {
    await waitForDebuggerAnimationFrame(target);
  }
  const secondSamples = await Promise.all(firstPass.map((candidate) => sampleAccessibilityBox(target, candidate, page)));
  const evaluated = firstPass.map((candidate, index) => ({
    ...candidate,
    secondSample: secondSamples[index]
  }));
  return protocol.filterThenLimit(
    evaluated,
    (candidate) => Boolean(
      candidate.secondSample &&
      (!payload?.options?.visibleOnly || candidate.secondSample.visible) &&
      (!payload?.options?.interactiveOnly || protocol.isInteractiveRole(candidate.snapshot.role))
    ),
    normalizeInteger(payload?.options?.maxCandidates, 5) || 5
  );
}

function accessibilityCandidateToMatch(candidate, session, index) {
  const first = candidate.firstSample;
  const current = candidate.secondSample || first;
  const stable = protocol.samplesAreStable(first, current);
  const area = current.rect.width * current.rect.height;
  const visibleArea = current.visibleRect.width * current.visibleRect.height;
  const visibleRatio = area > 0 ? Number((visibleArea / area).toFixed(4)) : 0;
  const point = {
    x: Math.round(current.visibleRect.left + current.visibleRect.width / 2),
    y: Math.round(current.visibleRect.top + current.visibleRect.height / 2)
  };
  const editable = candidate.snapshot.editable || ["combobox", "searchbox", "spinbutton", "textbox"].includes(candidate.snapshot.role);
  const actionability = {
    sameSession: true,
    attached: Boolean(first?.attached && current?.attached),
    visible: Boolean(first?.visible && current?.visible),
    notOccluded: Boolean(first?.notOccluded && current?.notOccluded),
    enabled: !candidate.snapshot.disabled,
    editable,
    stable
  };
  return {
    id: `candidate-${index + 1}`,
    text: candidate.snapshot.name,
    textRaw: candidate.snapshot.name,
    normalizedText: candidate.snapshot.name,
    role: candidate.snapshot.role,
    tagName: "AXNode",
    selectorHint: `ax:${candidate.snapshot.role}`,
    rect: current.rect,
    visibleRect: current.visibleRect,
    nodeRef: {
      nodeId: protocol.createAxNodeId(session, candidate.frameId, candidate.snapshot.backendNodeId),
      tabSessionId: session.tabSessionId,
      frameId: 0,
      cdpFrameId: candidate.frameId,
      backendNodeId: candidate.snapshot.backendNodeId,
      documentEpoch: session.documentEpoch,
      documentId: session.documentId,
      pageNonce: session.pageNonce,
      selectorHint: `ax:${candidate.snapshot.role}`,
      locatorRecipe: {
        role: candidate.snapshot.role,
        text: candidate.snapshot.name || null,
        selectorHint: `ax:${candidate.snapshot.role}`,
        ancestorHints: [],
        indexHint: index
      }
    },
    clickablePoint: point,
    actionability,
    visibleRatio,
    fullyVisible: visibleRatio === 1,
    occluded: !actionability.notOccluded,
    occlusionChecked: Boolean(first?.occlusionChecked && current?.occlusionChecked),
    selected: candidate.snapshot.selected,
    actionabilityScore: stable ? 1 : 0.5,
    score: candidate.score,
    source: "cdp_accessibility"
  };
}

async function locateWithAccessibilityFallback(tab, session, payload, domResult) {
  if ((domResult?.matchCount || 0) > 0 || !session.pageNonce) {
    return domResult;
  }
  try {
    const matches = await withDebugger(tab.id, async (target) => {
      const candidates = await collectAccessibilityCandidates(target, payload, domResult?.page || {});
      return candidates.map((candidate, index) => accessibilityCandidateToMatch(candidate, session, index));
    });
    if (matches.length === 0) {
      return domResult;
    }
    return {
      ...domResult,
      matchCount: matches.length,
      matches,
      flags: {
        ...(domResult?.flags || {}),
        accessibilityFallbackUsed: true
      }
    };
  } catch (error) {
    return {
      ...domResult,
      flags: {
        ...(domResult?.flags || {}),
        accessibilityFallbackError: String(error?.message || error || "Accessibility fallback failed.")
      }
    };
  }
}

function isAccessibilityNodeRef(nodeRef) {
  return protocol.parseNodeId(nodeRef?.nodeId)?.kind === "ax";
}

async function observeAccessibilityNode(tabId, session, nodeRef) {
  assertNodeRefDocument(nodeRef, session);
  const parsed = protocol.parseNodeId(nodeRef.nodeId);
  return withDebugger(tabId, async (target) => {
    await chrome.debugger.sendCommand(target, "Accessibility.enable");
    let partialTree;
    let firstBox;
    try {
      [partialTree, firstBox] = await Promise.all([
        chrome.debugger.sendCommand(target, "Accessibility.getPartialAXTree", {
          backendNodeId: parsed.backendNodeId,
          fetchRelatives: false
        }),
        chrome.debugger.sendCommand(target, "DOM.getBoxModel", { backendNodeId: parsed.backendNodeId })
      ]);
    } catch (_error) {
      return {
        observation: {
          nodeRef,
          exists: false,
          text: null,
          textRaw: null,
          value: null,
          selected: null,
          actionability: null
        }
      };
    }
    const snapshot = axNodeSnapshot(partialTree?.nodes?.[0] || {});
    const currentTab = await chrome.tabs.get(tabId);
    const page = await readTabState(tabId);
    await waitForDebuggerAnimationFrame(target);
    let secondBox = firstBox;
    try {
      secondBox = await chrome.debugger.sendCommand(target, "DOM.getBoxModel", { backendNodeId: parsed.backendNodeId });
    } catch (_error) {
      secondBox = null;
    }
    const firstRect = rectFromQuad(firstBox?.model?.border || firstBox?.model?.content);
    const rect = rectFromQuad(secondBox?.model?.border || secondBox?.model?.content) || firstRect;
    const firstVisibleRect = firstRect ? visibleRectForViewport(firstRect, page) : null;
    const visibleRect = rect ? visibleRectForViewport(rect, page) : null;
    const visible = Boolean(rect && visibleRect && rect.width > 0 && rect.height > 0 && visibleRect.width > 0 && visibleRect.height > 0);
    const point = visible
      ? {
        x: Math.round(visibleRect.left + visibleRect.width / 2),
        y: Math.round(visibleRect.top + visibleRect.height / 2)
      }
      : null;
    const pointOwned = point
      ? await accessibilityPointOwnership(target, parsed.backendNodeId, point)
      : false;
    const notOccluded = pointOwned !== false;
    const stable = protocol.samplesAreStable(
      {
        attached: Boolean(firstRect),
        visible: Boolean(firstRect && firstVisibleRect?.width > 0 && firstVisibleRect?.height > 0),
        notOccluded,
        rect: firstRect
      },
      {
        attached: Boolean(secondBox && rect),
        visible,
        notOccluded,
        rect
      }
    );
    const clickablePoint = point;
    return {
      observation: {
        nodeRef: attachNodeRef(nodeRef, { ...session, url: currentTab?.url || session.url }),
        exists: Boolean(snapshot.backendNodeId && secondBox && rect),
        text: snapshot.name || null,
        textRaw: snapshot.name || null,
        value: snapshot.value || null,
        selected: snapshot.selected,
        actionability: {
          sameSession: true,
          attached: Boolean(snapshot.backendNodeId && secondBox && rect),
          visible,
          notOccluded,
          enabled: !snapshot.disabled,
          editable: snapshot.editable || ["combobox", "searchbox", "spinbutton", "textbox"].includes(snapshot.role),
          stable
        },
        rect,
        clickablePoint,
        occlusionChecked: pointOwned !== null,
        source: "cdp_accessibility"
      }
    };
  });
}

async function observeNodeInTab(tabId, session, nodeRef) {
  return isAccessibilityNodeRef(nodeRef)
    ? observeAccessibilityNode(tabId, session, nodeRef)
    : dispatchToContentScript(tabId, "browser-assist:observe", { nodeRef });
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
      return protocol.withVerificationStatus({
        currentTab,
        verified: true,
        retryDisposition: RETRY.FAIL_FAST,
        failureReason: null,
        observation: {
          baselineUrl,
          currentUrl
        }
      }, "passed");
    }
    if (Date.now() >= deadline) {
      return protocol.withVerificationStatus({
        currentTab,
        verified: false,
        retryDisposition: RETRY.RETRY_SAME_TARGET,
        failureReason: "Verification timed out for url_changed.",
        observation: {
          baselineUrl,
          currentUrl
        }
      }, "failed");
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
    const currentTab = await chrome.tabs.get(tab.id);
    const currentUrl = currentTab?.url || session.url || null;
    const navigation = Boolean(session.url && currentUrl && currentUrl !== session.url);
    const skipped = protocol.notRequestedVerification();
    return {
      ...skipped,
      observation: {
        ...skipped.observation,
        baselineUrl: session.url || null,
        currentUrl,
        navigationObserved: navigation
      },
      navigation
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
  let navigationObserved = false;

  while (true) {
    if (verify.kind === "text_changed" || verify.kind === "selection_changed") {
      const observed = await observeNodeInTab(tab.id, session, payload.nodeRef);
      if (verify.kind === "text_changed") {
        const currentText = observed?.observation?.value ?? observed?.observation?.text ?? null;
        const baselineText = preparedObservation.value ?? preparedObservation.text ?? null;
        const expectedText = String(verify?.params?.expectedText || "").trim();
        lastObservation = {
          baselineText,
          currentText
        };
        if ((expectedText && currentText === expectedText) || (!expectedText && currentText !== null && currentText !== baselineText)) {
          return protocol.withVerificationStatus({
            verified: true,
            retryDisposition: RETRY.FAIL_FAST,
            failureReason: null,
            observation: lastObservation,
            navigation: false
          }, "passed");
        }
      } else {
        const currentSelected = observed?.observation?.selected;
        const expectedSelected = typeof verify?.params?.selected === "boolean" ? verify.params.selected : null;
        lastObservation = {
          baselineSelected: preparedObservation.selected ?? null,
          currentSelected
        };
        if ((expectedSelected !== null && currentSelected === expectedSelected) || (expectedSelected === null && currentSelected !== null && currentSelected !== preparedObservation.selected)) {
          return protocol.withVerificationStatus({
            verified: true,
            retryDisposition: RETRY.FAIL_FAST,
            failureReason: null,
            observation: lastObservation,
            navigation: false
          }, "passed");
        }
      }
    } else {
      const locatePayload = normalizeLocateVerifyPayload(verify);
      const domLocated = await dispatchToContentScript(tab.id, "browser-assist:locate", locatePayload);
      navigationObserved = Boolean(
        (session.documentId && domLocated?.page?.documentId && session.documentId !== domLocated.page.documentId) ||
        (session.url && domLocated?.page?.url && session.url !== domLocated.page.url)
      );
      const located = await locateWithAccessibilityFallback(tab, session, locatePayload, domLocated);
      lastObservation = { matchCount: located?.matchCount || 0 };
      const matched = verify.kind === "element_disappeared"
        ? lastObservation.matchCount === 0
        : lastObservation.matchCount > 0;
      if (matched) {
        return protocol.withVerificationStatus({
          verified: true,
          retryDisposition: RETRY.FAIL_FAST,
          failureReason: null,
          observation: lastObservation,
          navigation: navigationObserved
        }, "passed");
      }
    }

    if (Date.now() >= deadline) {
      return protocol.withVerificationStatus({
        verified: false,
        retryDisposition: RETRY.RETRY_SAME_TARGET,
        failureReason: `Verification timed out for ${verify.kind}.`,
        observation: lastObservation,
        navigation: navigationObserved
      }, "failed");
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
  const skipped = protocol.notRequestedVerification();
  const reportedVerification = payload?.verify
    ? verification
    : {
      ...skipped,
      observation: {
        ...verification.observation,
        ...skipped.observation,
        navigationObserved: verification.verified
      }
    };

  return {
    context: nextSession,
    action: "navigate",
    nodeRef: null,
    actionability: null,
    verified: reportedVerification.verified,
    verificationStatus: reportedVerification.verificationStatus,
    retryDisposition: reportedVerification.retryDisposition,
    failureReason: reportedVerification.failureReason,
    observation: reportedVerification.observation
  };
}

async function clickInTab(tab, session, payload, requestedId) {
  assertNodeRefDocument(payload.nodeRef, session);
  const prepared = await observeNodeInTab(tab.id, session, payload.nodeRef);
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
    verificationStatus: verification.verificationStatus,
    retryDisposition: verification.retryDisposition,
    failureReason: verification.failureReason,
    observation: verification.observation
  };
}

async function typeInAccessibilityNode(tab, session, payload, requestedId) {
  assertNodeRefDocument(payload.nodeRef, session);
  const prepared = await observeAccessibilityNode(tab.id, session, payload.nodeRef);
  const observation = prepared?.observation || {};
  if (!observation.exists) {
    throw extensionError("Target could not be resolved for typing.", RETRY.REACQUIRE_TARGET);
  }
  if (!observation.clickablePoint) {
    throw extensionError("Target did not provide a focus point.", RETRY.FAIL_FAST);
  }
  assertActionability(observation.actionability, "type");
  await dispatchTrustedClick(tab.id, observation.clickablePoint);
  await dispatchTrustedText(tab.id, payload.text);

  const verification = await runPostClickVerification(tab, session, payload, observation);
  const nextSession = verification.navigation
    ? await refreshSessionFromTab(tab.id, session)
    : cloneSession(session);
  const sameSession = !requestedId || requestedId === nextSession.tabSessionId;
  return {
    context: nextSession,
    action: "type",
    nodeRef: verification.navigation ? null : attachNodeRef(observation.nodeRef, nextSession),
    actionability: verification.navigation ? null : attachActionability(observation.actionability, sameSession),
    verified: verification.verified,
    verificationStatus: verification.verificationStatus,
    retryDisposition: verification.retryDisposition,
    failureReason: verification.failureReason,
    observation: verification.observation
  };
}

async function refreshResolvedTarget(resolved) {
  const tab = await chrome.tabs.get(resolved.tab.id);
  if (!tab || !isSupportedTabUrl(tab.url)) {
    throw extensionError("context_lost: Browser Assist action tab is no longer available.", RETRY.CONTEXT_LOST);
  }
  return {
    tab,
    session: await ensureTabSession(tab),
    requestedSessionId: resolved.requestedSessionId
  };
}

async function runActCommand(resolved, payload) {
  const { tab, session, requestedSessionId } = await refreshResolvedTarget(resolved);
  if (payload?.nodeRef) {
    assertNodeRefDocument(payload.nodeRef, session);
  }
  if (payload?.action === "navigate") {
    return navigateInTab(tab, session, payload, requestedSessionId);
  }
  if (payload?.action === "click") {
    return clickInTab(tab, session, payload, requestedSessionId);
  }
  if (payload?.action === "type" && isAccessibilityNodeRef(payload.nodeRef)) {
    return typeInAccessibilityNode(tab, session, payload, requestedSessionId);
  }
  return applyActContext(
    await dispatchToContentScript(tab.id, "browser-assist:act", payload),
    session,
    requestedSessionId
  );
}

async function runCommand(type, payload) {
  const resolved = await resolveTarget(payload);
  const { tab, session, requestedSessionId } = resolved;

  if (type === "locate") {
    const domResult = await dispatchToContentScript(tab.id, "browser-assist:locate", payload);
    const result = await locateWithAccessibilityFallback(tab, session, payload, domResult);
    return applyLocateContext(result, session, requestedSessionId);
  }

  if (type === "observe") {
    assertNodeRefDocument(payload?.nodeRef, session);
    return applyObservationContext(await observeNodeInTab(tab.id, session, payload.nodeRef), session, requestedSessionId);
  }

  if (type === "act") {
    return tabActionQueue.run(tab.id, () => runActCommand(resolved, payload));
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
          protocolVersion: 2,
          capabilities: [
            "document-identity-v2",
            "verification-status-v2",
            "tab-action-queue",
            "shadow-dom",
            "cdp-accessibility-fallback"
          ],
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
