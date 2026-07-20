(function () {
  if (globalThis.BrowserAssistLocator) {
    return;
  }

  const protocol = globalThis.BrowserAssistProtocol;
  if (!protocol) {
    throw new Error("BrowserAssistProtocol must be loaded before locator.js.");
  }

  const QUERY_SELECTOR = [
    "button",
    "a[href]",
    "area[href]",
    "input",
    "textarea",
    "select",
    "option",
    "summary",
    "[contenteditable]:not([contenteditable='false'])",
    "[role]",
    "[tabindex]",
    "[onclick]",
    "[aria-label]",
    "div",
    "span",
    "p",
    "li",
    "label",
    "article",
    "section",
    "aside",
    "details",
    "dialog",
    "form",
    "header",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "img",
    "main",
    "menu",
    "meter",
    "nav",
    "ol",
    "output",
    "progress",
    "table",
    "td",
    "th",
    "tr",
    "ul",
    "[aria-labelledby]"
  ].join(", ");
  const RETRY = Object.freeze({
    RETRY_SAME_TARGET: "retry_same_target",
    REACQUIRE_TARGET: "reacquire_target",
    FAIL_FAST: "fail_fast"
  });

  function createRuntime() {
    const state = {
      ...protocol.createDocumentIdentity(),
      documentEpoch: 1,
      nextNodeId: 1,
      nodeRefs: new WeakMap(),
      nodeLookup: new Map(),
      pendingWeight: 0,
      timer: null
    };

    const bumpDocumentEpoch = () => {
      state.documentEpoch += 1;
      state.nodeLookup.clear();
    };

    const observer = new MutationObserver((records) => {
      let weight = 0;
      for (const record of records) {
        if (record.type === "childList") {
          weight += record.addedNodes.length + record.removedNodes.length + 3;
        } else {
          weight += 1;
        }
      }
      if (weight <= 0) {
        return;
      }
      state.pendingWeight += weight;
      if (state.timer !== null) {
        return;
      }
      state.timer = setTimeout(() => {
        if (state.pendingWeight >= 24) {
          bumpDocumentEpoch();
        }
        state.pendingWeight = 0;
        state.timer = null;
      }, 150);
    });

    observer.observe(document.documentElement || document, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["class", "style", "hidden", "disabled", "checked", "aria-disabled", "aria-selected", "aria-pressed", "aria-checked"]
    });

    window.addEventListener("hashchange", () => {
      bumpDocumentEpoch();
    });
    window.addEventListener("popstate", () => {
      bumpDocumentEpoch();
    });
    window.addEventListener("beforeunload", () => {
      bumpDocumentEpoch();
    });

    return state;
  }

  function runtime() {
    if (!globalThis.__browserAssistRuntime) {
      globalThis.__browserAssistRuntime = createRuntime();
    }
    return globalThis.__browserAssistRuntime;
  }

  function fail(message, retryDisposition, details = {}) {
    const error = new Error(message);
    error.retryDisposition = retryDisposition;
    error.details = details;
    return error;
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function nextFrame() {
    return new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
  }

  function normalizeText(value) {
    return String(value || "")
      .replace(/[\u200B-\u200D\uFEFF]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function roundRect(rect) {
    return {
      left: Math.round(rect.left),
      top: Math.round(rect.top),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      right: Math.round(rect.right),
      bottom: Math.round(rect.bottom)
    };
  }

  function pageState() {
    return {
      url: window.location.href,
      title: document.title,
      scrollX: Math.round(window.scrollX),
      scrollY: Math.round(window.scrollY),
      viewportWidth: Math.round(window.innerWidth),
      viewportHeight: Math.round(window.innerHeight),
      devicePixelRatio: window.devicePixelRatio,
      documentEpoch: runtime().documentEpoch,
      documentId: runtime().documentId,
      pageNonce: runtime().pageNonce
    };
  }

  function queryElementsDeep(selector = QUERY_SELECTOR) {
    const matches = [];
    const seen = new Set();

    function visit(root) {
      if (!root || typeof root.querySelectorAll !== "function") {
        return;
      }
      for (const element of root.querySelectorAll(selector)) {
        if (!seen.has(element)) {
          seen.add(element);
          matches.push(element);
        }
      }
      for (const element of root.querySelectorAll("*")) {
        if (element.shadowRoot) {
          visit(element.shadowRoot);
        }
      }
    }

    visit(document);
    return matches;
  }

  function deepElementFromPoint(x, y) {
    let element = document.elementFromPoint(x, y);
    while (element?.shadowRoot && typeof element.shadowRoot.elementFromPoint === "function") {
      const nested = element.shadowRoot.elementFromPoint(x, y);
      if (!nested || nested === element) {
        break;
      }
      element = nested;
    }
    return element;
  }

  function ownsDeepNode(element, node) {
    let current = node;
    while (current instanceof Node) {
      if (current === element || element.contains(current)) {
        return true;
      }
      const root = typeof current.getRootNode === "function" ? current.getRootNode() : null;
      current = root instanceof ShadowRoot ? root.host : null;
    }
    return false;
  }

  function browserAnchor() {
    const visualViewport = window.visualViewport;
    const offsetLeft = Math.round(visualViewport?.offsetLeft ?? 0);
    const offsetTop = Math.round(visualViewport?.offsetTop ?? 0);
    const scale = Number((visualViewport?.scale ?? 1).toFixed(4));
    const horizontalChrome = Math.max(0, window.outerWidth - window.innerWidth);
    const verticalChrome = Math.max(0, window.outerHeight - window.innerHeight);
    const inferredLeftInset = horizontalChrome / 2;
    const inferredTopInset = Math.max(0, verticalChrome - inferredLeftInset);
    return {
      viewport: {
        offsetLeft,
        offsetTop,
        scale
      },
      browser: {
        contentLeftOnScreen: Math.round(window.screenX + inferredLeftInset),
        contentTopOnScreen: Math.round(window.screenY + inferredTopInset),
        raw: {
          screenX: Math.round(window.screenX),
          screenY: Math.round(window.screenY),
          outerWidth: Math.round(window.outerWidth),
          outerHeight: Math.round(window.outerHeight),
          innerWidth: Math.round(window.innerWidth),
          innerHeight: Math.round(window.innerHeight),
          inferredLeftInset: Math.round(inferredLeftInset),
          inferredTopInset: Math.round(inferredTopInset)
        }
      }
    };
  }

  function textSnapshot(element) {
    const raw = String(
      element?.getAttribute?.("aria-label") ||
      element?.getAttribute?.("title") ||
      element?.getAttribute?.("placeholder") ||
      element?.value ||
      element?.innerText ||
      element?.textContent ||
      ""
    );
    return { raw, normalized: normalizeText(raw) };
  }

  function selectorHint(element) {
    const tag = element.tagName.toLowerCase();
    const id = element.id ? `#${element.id}` : "";
    const classes = Array.from(element.classList || []).slice(0, 3).map((item) => `.${item}`).join("");
    return `${tag}${id}${classes}`;
  }

  function roleOf(element) {
    const explicit = element.getAttribute("role");
    if (explicit) {
      return explicit.trim().split(/\s+/)[0].toLowerCase();
    }
    const attributes = {};
    for (const name of ["alt", "aria-label", "aria-labelledby", "contenteditable", "href", "multiple", "size", "scope", "title", "type"]) {
      if (element.hasAttribute(name)) {
        attributes[name] = element.getAttribute(name) ?? "";
      }
    }
    return protocol.implicitRoleFor(element.tagName, attributes);
  }

  function selectedState(element) {
    const tag = element.tagName.toLowerCase();
    if (tag === "option") {
      return Boolean(element.selected);
    }
    if (tag === "input") {
      const type = (element.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox" || type === "radio") {
        return Boolean(element.checked);
      }
    }
    if (element.getAttribute("aria-selected") === "true" || element.getAttribute("aria-pressed") === "true" || element.getAttribute("aria-checked") === "true") {
      return true;
    }
    if (element.getAttribute("aria-selected") === "false" || element.getAttribute("aria-pressed") === "false" || element.getAttribute("aria-checked") === "false") {
      return false;
    }
    return null;
  }

  function isEditable(element, role) {
    return (
      element.isContentEditable ||
      ["combobox", "input", "listbox", "searchbox", "spinbutton", "textarea", "textbox"].includes(role) ||
      element.tagName.toLowerCase() === "select"
    );
  }

  function isInteractive(element, role) {
    if (protocol.isInteractiveRole(role)) {
      return true;
    }
    if (element.isContentEditable || element.hasAttribute("onclick")) {
      return true;
    }
    const tabIndex = Number.parseInt(element.getAttribute("tabindex"), 10);
    return Number.isFinite(tabIndex) && tabIndex >= 0;
  }

  function computeVisibleRect(rect) {
    const left = Math.max(0, Math.min(window.innerWidth, rect.left));
    const top = Math.max(0, Math.min(window.innerHeight, rect.top));
    const right = Math.max(0, Math.min(window.innerWidth, rect.right));
    const bottom = Math.max(0, Math.min(window.innerHeight, rect.bottom));
    return {
      left,
      top,
      right,
      bottom,
      width: Math.max(0, right - left),
      height: Math.max(0, bottom - top)
    };
  }

  function clickableSample(element, rect) {
    const visibleRect = computeVisibleRect(rect);
    const cx = Math.round(visibleRect.left + visibleRect.width / 2);
    const cy = Math.round(visibleRect.top + visibleRect.height / 2);
    const node = deepElementFromPoint(cx, cy);
    const owned = ownsDeepNode(element, node);
    return {
      point: { x: cx, y: cy },
      occluded: !owned
    };
  }

  function sampleActionability(element, role) {
    const rect = element.getBoundingClientRect();
    const visibleRect = computeVisibleRect(rect);
    const clickable = clickableSample(element, rect);
    return {
      rect: roundRect(rect),
      visibleRect: roundRect(visibleRect),
      visibleRatio: rect.width > 0 && rect.height > 0 ? Number(((visibleRect.width * visibleRect.height) / (rect.width * rect.height)).toFixed(4)) : 0,
      fullyVisible: rect.left >= 0 && rect.top >= 0 && rect.right <= window.innerWidth && rect.bottom <= window.innerHeight,
      clickablePoint: clickable.point,
      attached: Boolean(element.isConnected),
      visible: rect.width > 0 && rect.height > 0 && visibleRect.width > 0 && visibleRect.height > 0,
      notOccluded: !clickable.occluded,
      enabled: !element.hasAttribute("disabled") && element.getAttribute("aria-disabled") !== "true",
      editable: isEditable(element, role),
      selected: selectedState(element)
    };
  }

  function summarizeActionability(first, second) {
    const stable = protocol.samplesAreStable(first, second);
    const current = second.attached ? second : first;
    return {
      current,
      gates: {
        sameSession: true,
        attached: first.attached && second.attached,
        visible: first.visible && second.visible,
        notOccluded: first.notOccluded && second.notOccluded,
        enabled: first.enabled && second.enabled,
        editable: current.editable,
        stable
      }
    };
  }

  async function actionability(element, role) {
    const first = sampleActionability(element, role);
    await nextFrame();
    return summarizeActionability(first, sampleActionability(element, role));
  }

  function buildNodeRef(element, previous = null) {
    const state = runtime();
    const epoch = state.documentEpoch;
    const existing = state.nodeRefs.get(element);
    const nodeId = existing && existing.epoch === epoch
      ? existing.nodeId
      : protocol.createDomNodeId(state, epoch, state.nextNodeId++);
    state.nodeRefs.set(element, { epoch, nodeId });
    state.nodeLookup.set(nodeId, element);
    const snapshot = textSnapshot(element);
    return {
      nodeId,
      tabSessionId: previous?.tabSessionId || null,
      frameId: previous?.frameId ?? 0,
      documentEpoch: epoch,
      documentId: state.documentId,
      pageNonce: state.pageNonce,
      selectorHint: selectorHint(element),
      locatorRecipe: {
        role: roleOf(element),
        text: snapshot.normalized || null,
        selectorHint: selectorHint(element),
        ancestorHints: [],
        indexHint: 0
      }
    };
  }

  function resolveNodeRef(nodeRef) {
    if (!nodeRef || typeof nodeRef !== "object") {
      throw fail("Missing nodeRef.", RETRY.FAIL_FAST);
    }
    const state = runtime();
    if (!protocol.nodeRefMatchesDocument(nodeRef, state, state.documentEpoch)) {
      throw fail("nodeRef document identity is no longer current.", RETRY.REACQUIRE_TARGET, {
        requestedDocumentEpoch: nodeRef.documentEpoch,
        currentDocumentEpoch: state.documentEpoch,
        requestedDocumentId: nodeRef.documentId || null,
        currentDocumentId: state.documentId
      });
    }
    const parsedNodeId = protocol.parseNodeId(nodeRef.nodeId);
    if (parsedNodeId?.kind !== "dom") {
      throw fail("Accessibility nodeRef must be resolved by the extension service worker.", RETRY.REACQUIRE_TARGET);
    }
    const direct = state.nodeLookup.get(nodeRef.nodeId);
    if (direct instanceof Element && direct.isConnected) {
      return direct;
    }
    const selector = normalizeText(nodeRef.selectorHint || nodeRef.locatorRecipe?.selectorHint || "");
    if (selector) {
      try {
        const candidate = queryElementsDeep(selector)[0];
        if (candidate instanceof Element) {
          return candidate;
        }
      } catch (_error) {
        // Ignore invalid selector hints and fall through.
      }
    }
    const targetText = normalizeText(nodeRef.locatorRecipe?.text || "");
    const candidates = queryElementsDeep();
    return candidates.find((element) => {
      const snapshot = textSnapshot(element);
      return !targetText || snapshot.normalized === targetText || snapshot.normalized.includes(targetText);
    }) || null;
  }

  function matchScore(element, query) {
    const snapshot = textSnapshot(element);
    const role = roleOf(element);
    const textNeedle = normalizeText(query.text);
    if (!protocol.roleMatches(query.role, role)) {
      return 0;
    }
    if (textNeedle && !snapshot.normalized.includes(textNeedle)) {
      return 0;
    }
    let score = 0;
    if (textNeedle && snapshot.normalized === textNeedle) {
      score += 10;
    } else if (textNeedle) {
      score += 6;
    }
    if (query.hint && snapshot.normalized.includes(normalizeText(query.hint))) {
      score += 3;
    }
    if (protocol.roleMatches(query.role, role)) {
      score += 4;
    }
    const rect = element.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      score += 1;
    }
    return score;
  }

  async function locate(request) {
    const scored = queryElementsDeep()
      .map((element, order) => ({
        element,
        order,
        role: roleOf(element),
        score: matchScore(element, request.query)
      }))
      .filter((item) => item.score > 0)
      .sort((left, right) => right.score - left.score || left.order - right.order);

    for (const candidate of scored) {
      candidate.firstSample = sampleActionability(candidate.element, candidate.role);
    }
    const firstPass = scored.filter((candidate) => (
      (!request.options.visibleOnly || candidate.firstSample.visible) &&
      (!request.options.interactiveOnly || isInteractive(candidate.element, candidate.role))
    ));
    if (firstPass.length > 0) {
      await nextFrame();
    }

    const evaluated = firstPass.map((candidate) => ({
      ...candidate,
      ability: summarizeActionability(
        candidate.firstSample,
        sampleActionability(candidate.element, candidate.role)
      )
    }));
    const candidates = protocol.filterThenLimit(
      evaluated,
      (candidate) => (
        (!request.options.visibleOnly || candidate.ability.gates.visible) &&
        (!request.options.interactiveOnly || isInteractive(candidate.element, candidate.role))
      ),
      request.options.maxCandidates
    );

    const anchor = browserAnchor();
    const matches = candidates.map((candidate, index) => {
      const element = candidate.element;
      const role = candidate.role;
      const snapshot = textSnapshot(element);
      const ability = candidate.ability;
      return {
        id: `candidate-${index + 1}`,
        text: snapshot.normalized,
        textRaw: snapshot.raw,
        normalizedText: snapshot.normalized,
        role,
        tagName: element.tagName,
        selectorHint: selectorHint(element),
        rect: ability.current.rect,
        visibleRect: ability.current.visibleRect,
        nodeRef: buildNodeRef(element),
        clickablePoint: ability.current.clickablePoint,
        actionability: ability.gates,
        visibleRatio: ability.current.visibleRatio,
        fullyVisible: ability.current.fullyVisible,
        occluded: !ability.current.notOccluded,
        selected: ability.current.selected,
        actionabilityScore: ability.current.notOccluded ? 1.0 : 0.0,
        score: candidate.score
      };
    });

    return {
      page: pageState(),
      viewport: anchor.viewport,
      browser: anchor.browser,
      flags: {
        isSecurityPage: /security-check|verify-slider/i.test(window.location.href),
        bodyContainsSecurityText: /安全验证|滑块|验证/i.test(document.body?.innerText || "")
      },
      matchCount: matches.length,
      matches
    };
  }

  async function observe(request) {
    const element = resolveNodeRef(request.nodeRef);
    if (!element) {
      return {
        observation: {
          nodeRef: request.nodeRef,
          exists: false,
          text: null,
          textRaw: null,
          value: null,
          selected: null,
          actionability: null
        }
      };
    }

    const ability = await actionability(element, roleOf(element));
    const snapshot = textSnapshot(element);
    return {
      observation: {
        nodeRef: buildNodeRef(element, request.nodeRef),
        exists: true,
        text: snapshot.normalized || null,
        textRaw: snapshot.raw || null,
        value: typeof element.value === "string" ? element.value : (element.isContentEditable ? element.textContent || "" : null),
        selected: selectedState(element),
        actionability: ability.gates,
        rect: ability.current.rect,
        clickablePoint: ability.current.clickablePoint
      }
    };
  }

  async function verifyCondition(verify, fallbackNodeRef, baseline) {
    const params = verify.params || {};
    if (verify.kind === "url_changed") {
      const currentUrl = window.location.href;
      const expectedUrl = normalizeText(params.expectedUrl);
      const urlContains = normalizeText(params.urlContains);
      if (expectedUrl) {
        return { verified: currentUrl === expectedUrl, observation: { baselineUrl: baseline.url, currentUrl } };
      }
      if (urlContains) {
        return { verified: currentUrl.includes(urlContains), observation: { baselineUrl: baseline.url, currentUrl } };
      }
      return { verified: Boolean(baseline.url) && currentUrl !== baseline.url, observation: { baselineUrl: baseline.url, currentUrl } };
    }

    if (verify.kind === "text_changed" || verify.kind === "selection_changed") {
      const observed = await observe({ nodeRef: fallbackNodeRef });
      if (verify.kind === "text_changed") {
        const currentText = observed.observation.value ?? observed.observation.text;
        const expectedText = normalizeText(params.expectedText);
        if (expectedText) {
          return { verified: currentText === expectedText, observation: { baselineText: baseline.text, currentText } };
        }
        return { verified: baseline.text !== null && currentText !== baseline.text, observation: { baselineText: baseline.text, currentText } };
      }
      const currentSelected = observed.observation.selected;
      if (typeof params.selected === "boolean") {
        return { verified: currentSelected === params.selected, observation: { baselineSelected: baseline.selected, currentSelected } };
      }
      return { verified: baseline.selected !== null && currentSelected !== baseline.selected, observation: { baselineSelected: baseline.selected, currentSelected } };
    }

    if (verify.kind === "dialog_appeared" || verify.kind === "element_appeared" || verify.kind === "element_disappeared") {
      const query = params.query && typeof params.query === "object"
        ? params.query
        : (params.text ? { text: String(params.text), role: "any", hint: null } : null);
      if (!query) {
        throw fail(`Verify spec ${verify.kind} requires params.query or params.text.`, RETRY.FAIL_FAST);
      }
      const located = await locate({
        query,
        options: params.options || { visibleOnly: true, interactiveOnly: false, maxCandidates: 5 }
      });
      if (verify.kind === "element_disappeared") {
        return { verified: located.matchCount === 0, observation: { matchCount: located.matchCount } };
      }
      return { verified: located.matchCount > 0, observation: { matchCount: located.matchCount } };
    }

    throw fail(`Unsupported verify kind: ${verify.kind}`, RETRY.FAIL_FAST);
  }

  async function captureVerificationBaseline(verify, nodeRef) {
    if (verify.kind === "url_changed") {
      return { url: window.location.href };
    }
    if (verify.kind === "text_changed") {
      const observation = (await observe({ nodeRef })).observation;
      return { text: observation.value ?? observation.text };
    }
    if (verify.kind === "selection_changed") {
      return { selected: (await observe({ nodeRef })).observation.selected };
    }
    return { matchCount: 0 };
  }

  async function runVerify(verify, nodeRef, baseline = null) {
    if (!verify) {
      return protocol.notRequestedVerification();
    }
    const effectiveBaseline = baseline || await captureVerificationBaseline(verify, nodeRef);
    const deadline = Date.now() + verify.timeoutMs;
    let lastObservation = null;
    while (true) {
      const result = await verifyCondition(verify, nodeRef, effectiveBaseline);
      lastObservation = result.observation;
      if (result.verified) {
        return protocol.withVerificationStatus({
          verified: true,
          retryDisposition: RETRY.FAIL_FAST,
          failureReason: null,
          observation: result.observation
        }, "passed");
      }
      if (Date.now() >= deadline) {
        return protocol.withVerificationStatus({
          verified: false,
          retryDisposition: RETRY.RETRY_SAME_TARGET,
          failureReason: `Verification timed out for ${verify.kind}.`,
          observation: lastObservation
        }, "failed");
      }
      await sleep(verify.pollIntervalMs);
    }
  }

  function buildMouseEventInit(point, overrides = {}) {
    return {
      bubbles: true,
      cancelable: true,
      composed: true,
      view: window,
      clientX: point.x,
      clientY: point.y,
      screenX: Math.round(window.screenX + point.x),
      screenY: Math.round(window.screenY + point.y),
      button: 0,
      buttons: 0,
      detail: 1,
      ...overrides
    };
  }

  function dispatchPointerOrMouseEvent(target, type, point, overrides = {}) {
    const init = buildMouseEventInit(point, overrides);
    if (type.startsWith("pointer") && typeof PointerEvent === "function") {
      target.dispatchEvent(new PointerEvent(type, {
        ...init,
        pointerId: 1,
        pointerType: "mouse",
        isPrimary: true
      }));
      return;
    }
    target.dispatchEvent(new MouseEvent(type, init));
  }

  async function applyClick(element, point) {
    element.scrollIntoView({ block: "center", inline: "center" });
    await nextFrame();

    const latestPoint = point || clickableSample(element, element.getBoundingClientRect()).point;
    const pointTarget = document.elementFromPoint(latestPoint.x, latestPoint.y);
    const eventTarget = pointTarget instanceof Element && (pointTarget === element || element.contains(pointTarget))
      ? pointTarget
      : element;

    if (typeof element.focus === "function") {
      element.focus({ preventScroll: true });
    }
    if (eventTarget !== element && typeof eventTarget.focus === "function") {
      eventTarget.focus({ preventScroll: true });
    }

    dispatchPointerOrMouseEvent(eventTarget, "pointerover", latestPoint);
    dispatchPointerOrMouseEvent(eventTarget, "mouseover", latestPoint);
    dispatchPointerOrMouseEvent(eventTarget, "pointermove", latestPoint);
    dispatchPointerOrMouseEvent(eventTarget, "mousemove", latestPoint);
    dispatchPointerOrMouseEvent(eventTarget, "pointerdown", latestPoint, { buttons: 1 });
    dispatchPointerOrMouseEvent(eventTarget, "mousedown", latestPoint, { buttons: 1 });
    dispatchPointerOrMouseEvent(eventTarget, "pointerup", latestPoint);
    dispatchPointerOrMouseEvent(eventTarget, "mouseup", latestPoint);

    const activationTarget = (
      element.tagName.toLowerCase() === "a" ||
      roleOf(element) === "link" ||
      typeof eventTarget.click !== "function"
    )
      ? element
      : eventTarget;
    if (typeof activationTarget.click === "function") {
      activationTarget.click();
      return;
    }

    dispatchPointerOrMouseEvent(eventTarget, "click", latestPoint);
  }

  function applyType(element, text) {
    if (typeof element.focus === "function") {
      element.focus({ preventScroll: true });
    }
    if (element.isContentEditable) {
      element.textContent = text;
    } else if (typeof element.value === "string") {
      const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(element), "value");
      if (descriptor?.set) {
        descriptor.set.call(element, text);
      } else {
        element.value = text;
      }
    } else {
      throw fail("Target is not editable.", RETRY.FAIL_FAST);
    }
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function act(request) {
    if (request.action !== "click" && request.action !== "type") {
      throw fail(`Unsupported action: ${request.action}`, RETRY.FAIL_FAST);
    }
    const element = resolveNodeRef(request.nodeRef);
    if (!element) {
      throw fail("nodeRef could not be resolved in the current document epoch.", RETRY.REACQUIRE_TARGET);
    }
    const ability = await actionability(element, roleOf(element));
    if (!ability.gates.attached) {
      throw fail("Target is no longer attached.", RETRY.REACQUIRE_TARGET);
    }
    if (!ability.gates.visible || !ability.gates.notOccluded || !ability.gates.enabled || !ability.gates.stable) {
      throw fail("Target failed pre-action gates.", RETRY.FAIL_FAST, { actionability: ability.gates });
    }
    if (request.action === "type" && ability.gates.editable !== true) {
      throw fail("Target is not editable.", RETRY.FAIL_FAST, { actionability: ability.gates });
    }

    const nodeRef = buildNodeRef(element, request.nodeRef);
    const verificationBaseline = request.verify
      ? await captureVerificationBaseline(request.verify, nodeRef)
      : null;
    if (request.action === "click") {
      await applyClick(element, ability.current.clickablePoint);
    } else {
      applyType(element, String(request.text || ""));
    }

    const verification = await runVerify(request.verify || null, nodeRef, verificationBaseline);
    return {
      action: request.action,
      nodeRef,
      actionability: ability.gates,
      verified: verification.verified,
      verificationStatus: verification.verificationStatus,
      retryDisposition: verification.retryDisposition,
      failureReason: verification.failureReason,
      observation: verification.observation
    };
  }

  runtime();

  globalThis.BrowserAssistLocator = {
    act,
    getDocumentId: () => runtime().documentId,
    getDocumentEpoch: () => runtime().documentEpoch,
    getDocumentIdentity: () => ({ documentId: runtime().documentId, pageNonce: runtime().pageNonce }),
    getPageNonce: () => runtime().pageNonce,
    getPageState: pageState,
    locate,
    observe
  };
})();
