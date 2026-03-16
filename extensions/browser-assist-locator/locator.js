(function () {
  if (globalThis.BrowserAssistLocator) {
    return;
  }

  const INTERACTIVE_SELECTOR = [
    "button",
    "a[href]",
    "input",
    "textarea",
    "select",
    "[role]",
    "[tabindex]",
    "[onclick]",
    "[aria-label]",
    "[class*='btn']",
    "[class*='button']"
  ].join(", ");

  const TEXT_SELECTOR = [
    "button",
    "a[href]",
    "input",
    "textarea",
    "select",
    "[role]",
    "div",
    "span",
    "p",
    "li",
    "strong",
    "h1",
    "h2",
    "h3",
    "h4",
    "label",
    "article",
    "section"
  ].join(", ");

  const HINT_QUERY_SELECTOR = "h1,h2,h3,h4,strong,.title,.name,[data-title],[aria-label]";

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

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function normalizeText(value) {
    return String(value || "")
      .replace(/[\u200B-\u200D\uFEFF]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function extractElementTextSnapshot(element) {
    const raw = String(
      element?.getAttribute?.("aria-label") ||
      element?.getAttribute?.("title") ||
      element?.getAttribute?.("placeholder") ||
      element?.getAttribute?.("data-title") ||
      element?.value ||
      element?.innerText ||
      element?.textContent ||
      ""
    );

    return {
      raw,
      normalized: normalizeText(raw)
    };
  }

  function inferRole(element) {
    const explicitRole = element.getAttribute("role");
    if (explicitRole) {
      return explicitRole;
    }

    const tag = element.tagName.toLowerCase();
    if (tag === "button") {
      return "button";
    }
    if (tag === "a") {
      if (classLikeButton(element) || !element.hasAttribute("href")) {
        return "button";
      }
      return "link";
    }
    if (tag === "textarea") {
      return "textarea";
    }
    if (tag === "select") {
      return "input";
    }
    if (tag === "input") {
      const type = (element.getAttribute("type") || "text").toLowerCase();
      if (type === "checkbox") {
        return "checkbox";
      }
      if (type === "radio") {
        return "radio";
      }
      return "input";
    }

    if (isButtonLike(element)) {
      return "button";
    }

    return "any";
  }

  function buildSelectorHint(element) {
    const tag = element.tagName.toLowerCase();
    const id = element.id ? `#${element.id}` : "";
    const classes = Array.from(element.classList || [])
      .slice(0, 3)
      .map((item) => `.${item}`)
      .join("");
    return `${tag}${id}${classes}`;
  }

  function classLikeButton(element) {
    const className = normalizeText(element.className || "").toLowerCase();
    return className.includes("btn") || className.includes("button");
  }

  function isButtonLike(element) {
    const tag = element.tagName.toLowerCase();
    if (tag === "button") {
      return true;
    }
    if (element.getAttribute("role") === "button") {
      return true;
    }
    if (tag === "a" && element.hasAttribute("href")) {
      return true;
    }
    if (classLikeButton(element)) {
      return true;
    }
    if (element.hasAttribute("onclick")) {
      return true;
    }
    if (element.hasAttribute("tabindex") && Number(element.getAttribute("tabindex")) >= 0) {
      return true;
    }

    const style = window.getComputedStyle(element);
    return style.cursor === "pointer";
  }

  function interactiveDescendantsCount(element) {
    return element.querySelectorAll?.(INTERACTIVE_SELECTOR)?.length || 0;
  }

  function hasInteractiveDescendant(element) {
    return interactiveDescendantsCount(element) > 0;
  }

  function isInteractive(element, role) {
    if (element.hasAttribute("disabled") || element.getAttribute("aria-disabled") === "true") {
      return false;
    }

    if (["button", "link", "input", "textarea", "tab", "checkbox", "radio"].includes(role)) {
      return true;
    }

    const tag = element.tagName.toLowerCase();
    return tag === "button" || tag === "a" || tag === "input" || tag === "textarea" || tag === "select" || isButtonLike(element);
  }

  function matchesRole(role, queryRole) {
    return queryRole === "any" || role === queryRole;
  }

  function computeVisibleRect(rect) {
    const left = clamp(rect.left, 0, window.innerWidth);
    const top = clamp(rect.top, 0, window.innerHeight);
    const right = clamp(rect.right, 0, window.innerWidth);
    const bottom = clamp(rect.bottom, 0, window.innerHeight);

    return {
      left,
      top,
      right,
      bottom,
      width: Math.max(0, right - left),
      height: Math.max(0, bottom - top)
    };
  }

  function computeVisibilityMetrics(rect) {
    const visibleRect = computeVisibleRect(rect);
    const area = Math.max(0, rect.width) * Math.max(0, rect.height);
    const visibleArea = visibleRect.width * visibleRect.height;
    const visibleRatio = area > 0 ? Number((visibleArea / area).toFixed(4)) : 0;

    return {
      visibleRect,
      visibleRatio,
      fullyVisible:
        rect.left >= 0 &&
        rect.top >= 0 &&
        rect.right <= window.innerWidth &&
        rect.bottom <= window.innerHeight,
      partiallyVisible: visibleArea > 0,
      clippedByViewport:
        rect.left < 0 ||
        rect.top < 0 ||
        rect.right > window.innerWidth ||
        rect.bottom > window.innerHeight
    };
  }

  function isVisible(element) {
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return false;
    }

    const style = window.getComputedStyle(element);
    if (
      style.display === "none" ||
      style.visibility === "hidden" ||
      style.pointerEvents === "none" ||
      Number(style.opacity || "1") === 0
    ) {
      return false;
    }

    return computeVisibilityMetrics(rect).partiallyVisible;
  }

  function isMeaningfulTextCandidate(snapshot) {
    return snapshot.normalized.length > 0;
  }

  function closestHintText(element) {
    let current = element;
    let hops = 0;

    while (current && hops < 4) {
      const snapshot = extractElementTextSnapshot(current);
      if (snapshot.normalized) {
        return snapshot.normalized;
      }

      const inner = current.querySelector?.(HINT_QUERY_SELECTOR);
      const innerSnapshot = extractElementTextSnapshot(inner);
      if (innerSnapshot.normalized) {
        return innerSnapshot.normalized;
      }

      current = current.parentElement;
      hops += 1;
    }

    return "";
  }

  function computeHintScore(element, normalizedText, hint) {
    if (!hint) {
      return 0;
    }

    const normalizedHint = normalizeText(hint);
    if (!normalizedHint) {
      return 0;
    }

    if (normalizedText.includes(normalizedHint)) {
      return 4;
    }

    const ancestor = closestHintText(element);
    if (ancestor.includes(normalizedHint)) {
      return 2;
    }

    const dataset = normalizeText(
      element.closest?.("[data-name],[data-title],[aria-label]")?.textContent || ""
    );
    if (dataset.includes(normalizedHint)) {
      return 1;
    }

    return 0;
  }

  function isPointOwnedByElement(targetElement, node) {
    if (!targetElement || !node) {
      return false;
    }

    return (
      node === targetElement ||
      targetElement.contains(node) ||
      (node instanceof Element && node.contains(targetElement))
    );
  }

  function dedupePoints(points) {
    const seen = new Set();
    const output = [];

    for (const point of points) {
      const key = `${Math.round(point.x)}:${Math.round(point.y)}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      output.push(point);
    }

    return output;
  }

  function buildSamplePoints(visibleRect) {
    const insetX = Math.min(18, Math.max(8, visibleRect.width * 0.18));
    const insetY = Math.min(18, Math.max(8, visibleRect.height * 0.18));
    const left = visibleRect.left + insetX;
    const centerX = visibleRect.left + visibleRect.width / 2;
    const right = visibleRect.right - insetX;
    const top = visibleRect.top + insetY;
    const centerY = visibleRect.top + visibleRect.height / 2;
    const bottom = visibleRect.bottom - insetY;

    return dedupePoints([
      { x: centerX, y: centerY },
      { x: left, y: top },
      { x: right, y: top },
      { x: left, y: bottom },
      { x: right, y: bottom },
      { x: centerX, y: top },
      { x: centerX, y: bottom },
      { x: left, y: centerY },
      { x: right, y: centerY }
    ]).filter((point) => (
      point.x >= 0 &&
      point.y >= 0 &&
      point.x <= window.innerWidth - 1 &&
      point.y <= window.innerHeight - 1
    ));
  }

  function findClickablePoint(element, rect, role) {
    const visibility = computeVisibilityMetrics(rect);
    const visibleRect = visibility.visibleRect;

    if (!visibility.partiallyVisible) {
      return {
        point: {
          x: Math.round(rect.left + rect.width / 2),
          y: Math.round(rect.top + rect.height / 2)
        },
        actionabilityScore: 0,
        occluded: true
      };
    }

    const samplePoints = buildSamplePoints(visibleRect);
    let best = null;

    for (const point of samplePoints) {
      const node = document.elementFromPoint(point.x, point.y);
      const owned = isPointOwnedByElement(element, node);
      const interactiveNode = node instanceof Element ? isInteractive(node, inferRole(node)) : false;
      const interactiveElement = isInteractive(element, role);

      let score = 0;
      if (owned) {
        score += 8;
      }
      if (interactiveElement) {
        score += 3;
      }
      if (interactiveNode) {
        score += 2;
      }
      if (point.x > visibleRect.left && point.x < visibleRect.right) {
        score += 0.5;
      }
      if (point.y > visibleRect.top && point.y < visibleRect.bottom) {
        score += 0.5;
      }

      const candidate = {
        point: {
          x: Math.round(point.x),
          y: Math.round(point.y)
        },
        actionabilityScore: Number(score.toFixed(2)),
        occluded: !owned
      };

      if (!best || candidate.actionabilityScore > best.actionabilityScore) {
        best = candidate;
      }
    }

    return best || {
      point: {
        x: Math.round(visibleRect.left + visibleRect.width / 2),
        y: Math.round(visibleRect.top + visibleRect.height / 2)
      },
      actionabilityScore: 0,
      occluded: true
    };
  }

  function structuralNoisePenalty(element, snapshot, role, visibility) {
    const rect = element.getBoundingClientRect();
    const interactiveChildren = interactiveDescendantsCount(element);
    let penalty = 0;

    if (snapshot.normalized.length > 140) {
      penalty += 4;
    }
    if (snapshot.normalized.length > 320) {
      penalty += 8;
    }
    if (rect.width * rect.height > 120000) {
      penalty += 6;
    }
    if (rect.width * rect.height > 260000) {
      penalty += 10;
    }
    if (rect.height > 180) {
      penalty += 3;
    }
    if (interactiveChildren >= 4 && role === "any" && !isButtonLike(element)) {
      penalty += 7;
    }
    if (interactiveChildren >= 8 && !isButtonLike(element)) {
      penalty += 8;
    }
    if (!visibility.fullyVisible && visibility.visibleRatio < 0.45) {
      penalty += 4;
    }

    return penalty;
  }

  function resolveTargetElement(element, queryRole) {
    let current = element;
    let hops = 0;

    while (current && hops < 6) {
      const role = inferRole(current);
      if (queryRole === "any") {
        return current;
      }
      if (matchesRole(role, queryRole) && isInteractive(current, role)) {
        return current;
      }
      if (queryRole === "button" && isButtonLike(current)) {
        return current;
      }
      current = current.parentElement;
      hops += 1;
    }

    return queryRole === "any" ? element : null;
  }

  function textScore(text, needle) {
    if (!needle) {
      return 0;
    }
    if (text === needle) {
      return 6;
    }
    if (text.startsWith(needle) || text.endsWith(needle)) {
      return 4;
    }
    if (text.includes(needle)) {
      return 2;
    }
    return 0;
  }

  function hintTokenScore(text, hint) {
    const normalizedHint = normalizeText(hint);
    if (!normalizedHint) {
      return 0;
    }

    const tokens = normalizedHint
      .split(/[ ,，、:：/]+/)
      .map((item) => item.trim())
      .filter((item) => item.length >= 2);

    return tokens.reduce((score, token) => score + (text.includes(token) ? 1 : 0), 0);
  }

  function collectBrowserAnchor() {
    const visualViewport = window.visualViewport;
    const viewportOffsetLeft = Math.round(visualViewport?.offsetLeft ?? 0);
    const viewportOffsetTop = Math.round(visualViewport?.offsetTop ?? 0);
    const viewportScale = Number((visualViewport?.scale ?? 1).toFixed(4));

    const horizontalChrome = Math.max(0, window.outerWidth - window.innerWidth);
    const verticalChrome = Math.max(0, window.outerHeight - window.innerHeight);
    const inferredLeftInset = horizontalChrome / 2;
    const inferredTopInset = Math.max(0, verticalChrome - inferredLeftInset);

    return {
      viewport: {
        offsetLeft: viewportOffsetLeft,
        offsetTop: viewportOffsetTop,
        scale: viewportScale
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

  function collectCandidates(queryRole) {
    const selector = queryRole === "any"
      ? TEXT_SELECTOR
      : `${INTERACTIVE_SELECTOR}, ${TEXT_SELECTOR}`;

    return Array.from(document.querySelectorAll(selector));
  }

  function locate(request) {
    const query = request.query;
    const options = request.options;
    const anchor = collectBrowserAnchor();
    const textNeedle = normalizeText(query.text);
    const seen = new Set();

    const matches = collectCandidates(query.role)
      .map((sourceElement) => {
        const sourceSnapshot = extractElementTextSnapshot(sourceElement);
        const targetElement = resolveTargetElement(sourceElement, query.role);
        if (!targetElement) {
          return null;
        }

        const rect = targetElement.getBoundingClientRect();
        const snapshot = extractElementTextSnapshot(targetElement);
        if (!isMeaningfulTextCandidate(snapshot)) {
          return null;
        }

        const role = inferRole(targetElement);
        const visibility = computeVisibilityMetrics(rect);
        const clickability = findClickablePoint(targetElement, rect, role);
        const hintScore = computeHintScore(targetElement, snapshot.normalized, query.hint);

        const candidateKey = [
          targetElement.tagName,
          buildSelectorHint(targetElement),
          Math.round(rect.left),
          Math.round(rect.top),
          Math.round(rect.width),
          Math.round(rect.height)
        ].join("|");
        if (seen.has(candidateKey)) {
          return null;
        }
        seen.add(candidateKey);

        const score =
          hintScore * 10 +
          hintTokenScore(snapshot.normalized, query.hint) * 4 +
          textScore(snapshot.normalized, textNeedle) * 10 +
          (role === query.role ? 8 : 0) +
          (isInteractive(targetElement, role) ? 4 : 0) +
          visibility.visibleRatio * 6 +
          clickability.actionabilityScore * 5 -
          structuralNoisePenalty(targetElement, snapshot, role, visibility) -
          (clickability.occluded ? 10 : 0);

        return {
          element: targetElement,
          text: snapshot.normalized,
          textRaw: snapshot.raw,
          role,
          rect,
          visibility,
          clickability,
          score,
          hintScore,
          sourceText: sourceSnapshot.normalized,
          selectorHint: buildSelectorHint(targetElement)
        };
      })
      .filter(Boolean)
      .filter((item) => !options.visibleOnly || item.visibility.partiallyVisible)
      .filter((item) => matchesRole(item.role, query.role) || query.role === "any")
      .filter((item) => query.role === "any" || !options.interactiveOnly || isInteractive(item.element, item.role))
      .filter((item) => !textNeedle || item.text.includes(textNeedle) || item.sourceText.includes(textNeedle))
      .sort((left, right) => right.score - left.score)
      .slice(0, options.maxCandidates)
      .map((item, index) => ({
        id: `candidate-${index + 1}`,
        text: item.text,
        textRaw: item.textRaw,
        normalizedText: item.text,
        role: item.role,
        tagName: item.element.tagName,
        selectorHint: item.selectorHint,
        rect: roundRect(item.rect),
        visibleRect: roundRect(item.visibility.visibleRect),
        clickablePoint: {
          x: item.clickability.point.x,
          y: item.clickability.point.y
        },
        visibleRatio: item.visibility.visibleRatio,
        fullyVisible: item.visibility.fullyVisible,
        occluded: item.clickability.occluded,
        actionabilityScore: Number(item.clickability.actionabilityScore.toFixed(2)),
        score: Number(item.score.toFixed(2))
      }));

    return {
      page: {
        url: window.location.href,
        title: document.title,
        scrollX: Math.round(window.scrollX),
        scrollY: Math.round(window.scrollY),
        viewportWidth: Math.round(window.innerWidth),
        viewportHeight: Math.round(window.innerHeight),
        devicePixelRatio: window.devicePixelRatio
      },
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

  globalThis.BrowserAssistLocator = {
    locate
  };
})();
