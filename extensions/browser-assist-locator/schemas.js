(function () {
  if (globalThis.BrowserAssistSchemas) {
    return;
  }

  const DEFAULT_QUERY = Object.freeze({
    text: null,
    role: "any",
    hint: null
  });

  const DEFAULT_OPTIONS = Object.freeze({
    visibleOnly: true,
    interactiveOnly: true,
    maxCandidates: 5
  });

  function clampInteger(value, fallback, min, max) {
    const number = Number.parseInt(value, 10);
    if (!Number.isFinite(number)) {
      return fallback;
    }
    return Math.max(min, Math.min(max, number));
  }

  function normalizeLocateRequest(raw) {
    const query = { ...DEFAULT_QUERY, ...(raw?.query || {}) };
    const options = { ...DEFAULT_OPTIONS, ...(raw?.options || {}) };
    const tabSessionId = typeof raw?.tabSessionId === "string" ? raw.tabSessionId.trim() : "";
    const documentEpoch = Number.parseInt(raw?.documentEpoch, 10);

    query.role = typeof query.role === "string" ? query.role : "any";

    options.visibleOnly = Boolean(options.visibleOnly);
    options.interactiveOnly = Boolean(options.interactiveOnly);
    options.maxCandidates = clampInteger(options.maxCandidates, 5, 1, 20);

    return {
      query,
      options,
      tabSessionId: tabSessionId || null,
      documentEpoch: Number.isFinite(documentEpoch) ? Math.max(0, documentEpoch) : null
    };
  }

  function parseEnvelope(rawText) {
    const data = JSON.parse(rawText);
    return {
      type: String(data?.type || ""),
      requestId: data?.requestId ? String(data.requestId) : null,
      payload: data?.payload && typeof data.payload === "object" ? data.payload : {}
    };
  }

  function buildEnvelope(type, payload, requestId = null) {
    return JSON.stringify({
      type,
      requestId,
      payload: payload && typeof payload === "object" ? payload : {}
    });
  }

  globalThis.BrowserAssistSchemas = {
    buildEnvelope,
    normalizeLocateRequest,
    parseEnvelope
  };
})();
