(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root && !root.BrowserAssistProtocol) {
    root.BrowserAssistProtocol = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const INTERACTIVE_ROLES = new Set([
    "button",
    "checkbox",
    "combobox",
    "gridcell",
    "input",
    "link",
    "listbox",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "option",
    "radio",
    "scrollbar",
    "searchbox",
    "slider",
    "spinbutton",
    "switch",
    "tab",
    "textarea",
    "textbox",
    "treeitem"
  ]);

  function fallbackUuid() {
    const cryptoObject = typeof globalThis !== "undefined" ? globalThis.crypto : null;
    if (cryptoObject && typeof cryptoObject.getRandomValues === "function") {
      const bytes = new Uint8Array(16);
      cryptoObject.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  }

  function defaultUuid() {
    const cryptoObject = typeof globalThis !== "undefined" ? globalThis.crypto : null;
    return cryptoObject && typeof cryptoObject.randomUUID === "function"
      ? cryptoObject.randomUUID()
      : fallbackUuid();
  }

  function normalizeIdentityPart(value) {
    return String(value || "").trim();
  }

  function createDocumentIdentity(uuidFactory = defaultUuid) {
    const seed = normalizeIdentityPart(uuidFactory()) || fallbackUuid();
    return Object.freeze({
      documentId: `document-${seed}`,
      pageNonce: `nonce-${seed}`
    });
  }

  function createDomNodeId(identity, documentEpoch, sequence) {
    return [
      "dom",
      encodeURIComponent(identity.pageNonce),
      Math.max(0, Number.parseInt(documentEpoch, 10) || 0),
      Math.max(1, Number.parseInt(sequence, 10) || 1)
    ].join(":");
  }

  function createAxNodeId(identity, frameId, backendNodeId) {
    return [
      "ax",
      encodeURIComponent(identity.pageNonce),
      encodeURIComponent(String(frameId || "")),
      Math.max(0, Number.parseInt(backendNodeId, 10) || 0)
    ].join(":");
  }

  function parseNodeId(nodeId) {
    const parts = String(nodeId || "").split(":");
    const decodePart = (value) => {
      try {
        return decodeURIComponent(value);
      } catch (_error) {
        return null;
      }
    };
    if (parts[0] === "dom" && parts.length === 4) {
      const documentEpoch = Number.parseInt(parts[2], 10);
      const sequence = Number.parseInt(parts[3], 10);
      const pageNonce = decodePart(parts[1]);
      if (!pageNonce || !Number.isFinite(documentEpoch) || !Number.isFinite(sequence)) {
        return null;
      }
      return {
        kind: "dom",
        pageNonce,
        documentEpoch,
        sequence
      };
    }
    if (parts[0] === "ax" && parts.length === 4) {
      const backendNodeId = Number.parseInt(parts[3], 10);
      const pageNonce = decodePart(parts[1]);
      const frameId = decodePart(parts[2]);
      if (!pageNonce || frameId === null || !Number.isFinite(backendNodeId) || backendNodeId <= 0) {
        return null;
      }
      return {
        kind: "ax",
        pageNonce,
        frameId,
        backendNodeId
      };
    }
    return null;
  }

  function nodeRefMatchesDocument(nodeRef, identity, documentEpoch) {
    if (!nodeRef || typeof nodeRef !== "object" || !identity) {
      return false;
    }
    const parsed = parseNodeId(nodeRef.nodeId);
    if (!parsed || parsed.pageNonce !== identity.pageNonce) {
      return false;
    }
    if (nodeRef.documentId && nodeRef.documentId !== identity.documentId) {
      return false;
    }
    if (nodeRef.pageNonce && nodeRef.pageNonce !== identity.pageNonce) {
      return false;
    }
    const requestedEpoch = Number.parseInt(nodeRef.documentEpoch, 10);
    const currentEpoch = Number.parseInt(documentEpoch, 10);
    if (Number.isFinite(currentEpoch) && requestedEpoch !== currentEpoch) {
      return false;
    }
    if (parsed.kind === "dom" && Number.isFinite(currentEpoch) && parsed.documentEpoch !== currentEpoch) {
      return false;
    }
    return true;
  }

  function notRequestedVerification() {
    return {
      verified: false,
      verificationStatus: "not_requested",
      retryDisposition: "fail_fast",
      failureReason: null,
      observation: {
        verificationRequested: false,
        verificationSkipped: true,
        verificationStatus: "not_requested"
      }
    };
  }

  function withVerificationStatus(result, status) {
    const verificationStatus = status || (result?.verified ? "passed" : "failed");
    return {
      ...(result || {}),
      verified: verificationStatus === "passed",
      verificationStatus,
      observation: {
        ...(result?.observation || {}),
        verificationRequested: verificationStatus !== "not_requested",
        verificationStatus
      }
    };
  }

  function createKeyedSerialQueue() {
    const tails = new Map();
    return {
      get size() {
        return tails.size;
      },
      run(key, task) {
        if (typeof task !== "function") {
          return Promise.reject(new TypeError("Queued Browser Assist action must be a function."));
        }
        const normalizedKey = String(key);
        const previous = tails.get(normalizedKey) || Promise.resolve();
        const execution = previous.catch(() => undefined).then(() => task());
        let tail;
        const result = execution.finally(() => {
          if (tails.get(normalizedKey) === tail) {
            tails.delete(normalizedKey);
          }
        });
        tail = result.then(() => undefined, () => undefined);
        tails.set(normalizedKey, tail);
        return result;
      }
    };
  }

  function filterThenLimit(candidates, predicate, limit) {
    const normalizedLimit = Math.max(0, Number.parseInt(limit, 10) || 0);
    if (!Array.isArray(candidates) || normalizedLimit === 0) {
      return [];
    }
    return candidates.filter(predicate).slice(0, normalizedLimit);
  }

  function attributeValue(attributes, name) {
    if (!attributes || typeof attributes !== "object") {
      return null;
    }
    const value = attributes[name] ?? attributes[name.toLowerCase()] ?? null;
    return value === null || value === undefined ? null : String(value);
  }

  function hasAttribute(attributes, name) {
    return attributeValue(attributes, name) !== null;
  }

  function implicitRoleFor(tagName, attributes = {}) {
    const tag = String(tagName || "").toLowerCase();
    if (tag === "a" || tag === "area") {
      return hasAttribute(attributes, "href") ? "link" : "any";
    }
    if (tag === "button" || tag === "summary") {
      return "button";
    }
    if (tag === "textarea") {
      return "textbox";
    }
    if (tag === "select") {
      const size = Number.parseInt(attributeValue(attributes, "size"), 10);
      return hasAttribute(attributes, "multiple") || (Number.isFinite(size) && size > 1) ? "listbox" : "combobox";
    }
    if (tag === "input") {
      const type = String(attributeValue(attributes, "type") || "text").toLowerCase();
      if (type === "hidden") {
        return "any";
      }
      if (type === "checkbox") {
        return "checkbox";
      }
      if (type === "radio") {
        return "radio";
      }
      if (type === "range") {
        return "slider";
      }
      if (type === "number") {
        return "spinbutton";
      }
      if (type === "search") {
        return "searchbox";
      }
      if (["button", "file", "image", "reset", "submit"].includes(type)) {
        return "button";
      }
      return "textbox";
    }
    const namedLandmark = Boolean(
      attributeValue(attributes, "aria-label") ||
      attributeValue(attributes, "aria-labelledby") ||
      attributeValue(attributes, "title")
    );
    const roles = {
      aside: "complementary",
      dialog: "dialog",
      footer: "contentinfo",
      form: namedLandmark ? "form" : "any",
      header: "banner",
      hr: "separator",
      main: "main",
      menu: "menu",
      meter: "meter",
      nav: "navigation",
      ol: "list",
      option: "option",
      output: "status",
      progress: "progressbar",
      section: namedLandmark ? "region" : "any",
      table: "table",
      tbody: "rowgroup",
      td: "cell",
      tfoot: "rowgroup",
      th: attributeValue(attributes, "scope") === "row" ? "rowheader" : "columnheader",
      thead: "rowgroup",
      tr: "row",
      ul: "list"
    };
    if (/^h[1-6]$/.test(tag)) {
      return "heading";
    }
    if (tag === "li") {
      return "listitem";
    }
    if (tag === "img") {
      return attributeValue(attributes, "alt") === "" ? "presentation" : "img";
    }
    if (attributeValue(attributes, "contenteditable") !== null && attributeValue(attributes, "contenteditable") !== "false") {
      return "textbox";
    }
    return roles[tag] || "any";
  }

  function roleMatches(requestedRole, actualRole) {
    const requested = String(requestedRole || "any").toLowerCase();
    const actual = String(actualRole || "any").toLowerCase();
    if (requested === "any" || requested === actual) {
      return true;
    }
    if (requested === "input") {
      return ["combobox", "listbox", "searchbox", "spinbutton", "textbox"].includes(actual);
    }
    if (requested === "textarea") {
      return actual === "textbox";
    }
    return false;
  }

  function isInteractiveRole(role) {
    return INTERACTIVE_ROLES.has(String(role || "").toLowerCase());
  }

  function samplesAreStable(first, second, tolerance = 2) {
    if (!first || !second || !first.rect || !second.rect) {
      return false;
    }
    return Boolean(
      first.attached &&
      second.attached &&
      Math.abs(first.rect.left - second.rect.left) <= tolerance &&
      Math.abs(first.rect.top - second.rect.top) <= tolerance &&
      Math.abs(first.rect.width - second.rect.width) <= tolerance &&
      Math.abs(first.rect.height - second.rect.height) <= tolerance &&
      first.visible === second.visible &&
      first.notOccluded === second.notOccluded
    );
  }

  return Object.freeze({
    createAxNodeId,
    createDocumentIdentity,
    createDomNodeId,
    createKeyedSerialQueue,
    filterThenLimit,
    implicitRoleFor,
    isInteractiveRole,
    nodeRefMatchesDocument,
    notRequestedVerification,
    parseNodeId,
    roleMatches,
    samplesAreStable,
    withVerificationStatus
  });
});
