(function () {
  if (globalThis.BrowserAssistLocator) {
    return;
  }

  const INTERACTIVE_SELECTOR = [
    "button",
    "a[href]",
    "input",
    "textarea",
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
    "[role]",
    "div",
    "span",
    "p",
    "li",
    "strong",
    "h1",
    "h2",
    "h3",
    "h4"
  ].join(", ");

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

  function normalizeText(value) {
    return String(value || "")
      .replace(/[\u200B-\u200D\uFEFF]/g, "")
      .replace(/[\uE000-\uF8FF]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function extractElementText(element) {
    return normalizeText(
      element.getAttribute?.("aria-label") ||
      element.getAttribute?.("title") ||
      element.getAttribute?.("placeholder") ||
      element.getAttribute?.("data-title") ||
      element.value ||
      element.innerText ||
      element.textContent ||
      ""
    );
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
    const classes = Array.from(element.classList || []).slice(0, 2).map((item) => `.${item}`).join("");
    return `${tag}${id}${classes}`;
  }

  function isVisible(element) {
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return false;
    }

    const style = window.getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden" || style.pointerEvents === "none") {
      return false;
    }

    return rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight && rect.left < window.innerWidth;
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

  function hasInteractiveDescendant(element) {
    return Boolean(element.querySelector?.(INTERACTIVE_SELECTOR));
  }

  function isInteractive(element, role) {
    if (element.hasAttribute("disabled") || element.getAttribute("aria-disabled") === "true") {
      return false;
    }

    if (["button", "link", "input", "textarea", "tab", "checkbox", "radio"].includes(role)) {
      return true;
    }

    const tag = element.tagName.toLowerCase();
    return tag === "button" || tag === "a" || tag === "input" || tag === "textarea" || isButtonLike(element);
  }

  function matchesRole(role, queryRole) {
    return queryRole === "any" || role === queryRole;
  }

  function closestHintText(element) {
    let current = element;
    let hops = 0;

    while (current && hops < 4) {
      const label = normalizeText(
        current.getAttribute?.("aria-label") ||
          current.getAttribute?.("data-title") ||
          current.querySelector?.("h1,h2,h3,h4,strong,.title,.name")?.textContent ||
          ""
      );
      if (label) {
        return label;
      }
      current = current.parentElement;
      hops += 1;
    }

    return "";
  }

  function computeHintScore(element, hint) {
    if (!hint) {
      return 0;
    }

    const normalizedHint = normalizeText(hint);
    if (!normalizedHint) {
      return 0;
    }

    const direct = normalizeText(element.textContent);
    if (direct.includes(normalizedHint)) {
      return 3;
    }

    const ancestor = closestHintText(element);
    if (ancestor.includes(normalizedHint)) {
      return 2;
    }

    const dataset = normalizeText(element.closest("[data-name],[data-title],[aria-label]")?.textContent || "");
    if (dataset.includes(normalizedHint)) {
      return 1;
    }

    return 0;
  }

  function noisePenalty(element, text, role) {
    const rect = element.getBoundingClientRect();
    let penalty = 0;

    if (text.length > 120) {
      penalty += 6;
    }

    if (text.length > 300) {
      penalty += 10;
    }

    if (rect.width * rect.height > 120000) {
      penalty += 6;
    }

    if (rect.height > 180) {
      penalty += 4;
    }

    if (hasInteractiveDescendant(element) && role === "any" && !isButtonLike(element)) {
      penalty += 8;
    }

    return penalty;
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

  function resolveTargetElement(element, queryRole) {
    let current = element;
    let hops = 0;

    while (current && hops < 5) {
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

  function locate(request) {
    const query = request.query;
    const options = request.options;

    const anchor = collectBrowserAnchor();
    const textNeedle = normalizeText(query.text);

    const seen = new Set();
    const matches = collectCandidates(query.role)
      .map((sourceElement) => {
        const sourceText = extractElementText(sourceElement);
        const targetElement = resolveTargetElement(sourceElement, query.role);
        if (!targetElement) {
          return null;
        }
        const rect = targetElement.getBoundingClientRect();
        const text = extractElementText(targetElement) || sourceText;
        const role = inferRole(targetElement);
        const hintScore = computeHintScore(targetElement, query.hint);
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
        return {
          element: targetElement,
          text,
          role,
          rect,
          hintScore,
          sourceText,
          score:
            hintScore * 10 +
            hintTokenScore(text, query.hint) * 4 +
            textScore(text, textNeedle) * 10 +
            (role === query.role ? 8 : 0) +
            (isInteractive(targetElement, role) ? 4 : 0) -
            Math.round((rect.width * rect.height) / 100000) -
            noisePenalty(targetElement, text, role)
        };
      })
      .filter(Boolean)
      .filter((item) => !options.visibleOnly || isVisible(item.element))
      .filter((item) => matchesRole(item.role, query.role) || query.role === "any")
      .filter((item) => query.role === "any" || !options.interactiveOnly || isInteractive(item.element, item.role))
      .filter((item) => item.text.length > 0)
      .filter((item) => !textNeedle || item.text.includes(textNeedle) || item.sourceText.includes(textNeedle))
      .sort((left, right) => right.score - left.score)
      .slice(0, options.maxCandidates)
      .map((item, index) => ({
        id: `candidate-${index + 1}`,
        text: item.text,
        role: item.role,
        tagName: item.element.tagName,
        rect: roundRect(item.rect),
        clickablePoint: {
          x: Math.round(item.rect.left + item.rect.width / 2),
          y: Math.round(item.rect.top + item.rect.height / 2)
        }
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
