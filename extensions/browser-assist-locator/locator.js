(function () {
  if (globalThis.BrowserAssistLocator) {
    return;
  }

  const QUERY_SELECTOR = [
    "button",
    "a[href]",
    "input",
    "textarea",
    "select",
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
    "section"
  ].join(", ");
  const RETRY = Object.freeze({
    RETRY_SAME_TARGET: "retry_same_target",
    REACQUIRE_TARGET: "reacquire_target",
    FAIL_FAST: "fail_fast"
  });

  function createRuntime() {
    const state = {
      documentEpoch: 1,
      nextNodeId: 1,
      nodeRefs: new WeakMap(),
      nodeLookup: new Map(),
      pendingWeight: 0,
      timer: null
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
          state.documentEpoch += 1;
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
      state.documentEpoch += 1;
    });
    window.addEventListener("popstate", () => {
      state.documentEpoch += 1;
    });
    window.addEventListener("beforeunload", () => {
      state.documentEpoch += 1;
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
      documentEpoch: runtime().documentEpoch
    };
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
      return explicit;
    }
    const tag = element.tagName.toLowerCase();
    if (tag === "button") {
      return "button";
    }
    if (tag === "a") {
      return "link";
    }
    if (tag === "textarea") {
      return "textarea";
    }
    if (tag === "select" || tag === "input") {
      const type = (element.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox") {
        return "checkbox";
      }
      if (type === "radio") {
        return "radio";
      }
      return "input";
    }
    return "any";
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
    return element.isContentEditable || role === "input" || role === "textarea" || element.tagName.toLowerCase() === "select";
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
    const node = document.elementFromPoint(cx, cy);
    const owned = node === element || element.contains(node) || (node instanceof Element && node.contains(element));
    return {
      point: { x: cx, y: cy },
      occluded: !owned
    };
  }

  async function actionability(element, role) {
    const sample = () => {
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
    };

    const first = sample();
    await nextFrame();
    const second = sample();
    const stable =
      first.attached &&
      second.attached &&
      Math.abs(first.rect.left - second.rect.left) <= 2 &&
      Math.abs(first.rect.top - second.rect.top) <= 2 &&
      Math.abs(first.rect.width - second.rect.width) <= 2 &&
      Math.abs(first.rect.height - second.rect.height) <= 2 &&
      first.visible === second.visible &&
      first.notOccluded === second.notOccluded;
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

  function buildNodeRef(element, previous = null) {
    const state = runtime();
    const epoch = state.documentEpoch;
    const existing = state.nodeRefs.get(element);
    const nodeId = existing && existing.epoch === epoch ? existing.nodeId : `node-${epoch}-${state.nextNodeId++}`;
    state.nodeRefs.set(element, { epoch, nodeId });
    state.nodeLookup.set(nodeId, element);
    const snapshot = textSnapshot(element);
    return {
      nodeId,
      tabSessionId: previous?.tabSessionId || null,
      frameId: previous?.frameId ?? 0,
      documentEpoch: epoch,
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
    if ((nodeRef.documentEpoch ?? 0) !== runtime().documentEpoch) {
      throw fail("nodeRef documentEpoch is no longer current.", RETRY.REACQUIRE_TARGET, {
        requestedDocumentEpoch: nodeRef.documentEpoch,
        currentDocumentEpoch: runtime().documentEpoch
      });
    }
    const direct = runtime().nodeLookup.get(nodeRef.nodeId);
    if (direct instanceof Element && direct.isConnected) {
      return direct;
    }
    const selector = normalizeText(nodeRef.selectorHint || nodeRef.locatorRecipe?.selectorHint || "");
    if (selector) {
      try {
        const candidate = document.querySelector(selector);
        if (candidate instanceof Element) {
          return candidate;
        }
      } catch (_error) {
        // Ignore invalid selector hints and fall through.
      }
    }
    const targetText = normalizeText(nodeRef.locatorRecipe?.text || "");
    const candidates = Array.from(document.querySelectorAll(QUERY_SELECTOR));
    return candidates.find((element) => {
      const snapshot = textSnapshot(element);
      return !targetText || snapshot.normalized === targetText || snapshot.normalized.includes(targetText);
    }) || null;
  }

  function matchScore(element, query) {
    const snapshot = textSnapshot(element);
    const role = roleOf(element);
    const textNeedle = normalizeText(query.text);
    if (query.role && query.role !== "any" && role !== query.role) {
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
    if (query.role === "any" || role === query.role) {
      score += 4;
    }
    const rect = element.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      score += 1;
    }
    return score;
  }

  async function locate(request) {
    const candidates = Array.from(document.querySelectorAll(QUERY_SELECTOR))
      .map((element) => ({
        element,
        score: matchScore(element, request.query)
      }))
      .filter((item) => item.score > 0)
      .sort((left, right) => right.score - left.score)
      .slice(0, request.options.maxCandidates);

    const anchor = browserAnchor();
    const matches = [];
    for (let index = 0; index < candidates.length; index += 1) {
      const element = candidates[index].element;
      const role = roleOf(element);
      const snapshot = textSnapshot(element);
      const ability = await actionability(element, role);
      if (request.options.visibleOnly && !ability.gates.visible) {
        continue;
      }
      if (request.options.interactiveOnly && role === "any") {
        continue;
      }
      matches.push({
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
        score: candidates[index].score
      });
    }

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
        const currentText = observed.observation.text;
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
        options: params.options || { visibleOnly: true, interactiveOnly: true, maxCandidates: 5 }
      });
      if (verify.kind === "element_disappeared") {
        return { verified: located.matchCount === 0, observation: { matchCount: located.matchCount } };
      }
      return { verified: located.matchCount > 0, observation: { matchCount: located.matchCount } };
    }

    throw fail(`Unsupported verify kind: ${verify.kind}`, RETRY.FAIL_FAST);
  }

  async function runVerify(verify, nodeRef) {
    if (!verify) {
      return { verified: true, retryDisposition: RETRY.FAIL_FAST, failureReason: null, observation: { verificationSkipped: true } };
    }
    const baseline = verify.kind === "url_changed"
      ? { url: window.location.href }
      : verify.kind === "text_changed"
        ? { text: (await observe({ nodeRef })).observation.text }
        : verify.kind === "selection_changed"
          ? { selected: (await observe({ nodeRef })).observation.selected }
          : { matchCount: 0 };
    const deadline = Date.now() + verify.timeoutMs;
    let lastObservation = null;
    while (true) {
      const result = await verifyCondition(verify, nodeRef, baseline);
      lastObservation = result.observation;
      if (result.verified) {
        return { verified: true, retryDisposition: RETRY.FAIL_FAST, failureReason: null, observation: result.observation };
      }
      if (Date.now() >= deadline) {
        return {
          verified: false,
          retryDisposition: RETRY.RETRY_SAME_TARGET,
          failureReason: `Verification timed out for ${verify.kind}.`,
          observation: lastObservation
        };
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
    if (request.action === "click") {
      await applyClick(element, ability.current.clickablePoint);
    } else {
      applyType(element, String(request.text || ""));
    }

    const verification = await runVerify(request.verify || null, nodeRef);
    return {
      action: request.action,
      nodeRef,
      actionability: ability.gates,
      verified: verification.verified,
      retryDisposition: verification.retryDisposition,
      failureReason: verification.failureReason,
      observation: verification.observation
    };
  }

  runtime();

  globalThis.BrowserAssistLocator = {
    act,
    getDocumentEpoch: () => runtime().documentEpoch,
    getPageState: pageState,
    locate,
    observe
  };
})();
