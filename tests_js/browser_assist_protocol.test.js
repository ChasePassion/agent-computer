"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const protocol = require("../extensions/browser-assist-locator/protocol.js");

test("a node reference cannot cross top-level documents even when the epoch resets", () => {
  const firstDocument = protocol.createDocumentIdentity(() => "first-document");
  const secondDocument = protocol.createDocumentIdentity(() => "second-document");
  const nodeRef = {
    nodeId: protocol.createDomNodeId(firstDocument, 1, 7),
    documentId: firstDocument.documentId,
    pageNonce: firstDocument.pageNonce,
    documentEpoch: 1
  };

  assert.equal(protocol.nodeRefMatchesDocument(nodeRef, firstDocument, 1), true);
  assert.equal(protocol.nodeRefMatchesDocument(nodeRef, secondDocument, 1), false);
  assert.equal(protocol.nodeRefMatchesDocument({ nodeId: "node-1-7", documentEpoch: 1 }, secondDocument, 1), false);
});

test("an explicit document identity mismatch wins over an encoded node id", () => {
  const currentDocument = protocol.createDocumentIdentity(() => "current-document");
  const nodeRef = {
    nodeId: protocol.createDomNodeId(currentDocument, 3, 2),
    documentId: "document-stale-document",
    pageNonce: currentDocument.pageNonce,
    documentEpoch: 3
  };

  assert.equal(protocol.nodeRefMatchesDocument(nodeRef, currentDocument, 3), false);
});

test("an omitted verification is reported as not requested instead of verified", () => {
  assert.deepEqual(protocol.notRequestedVerification(), {
    verified: false,
    verificationStatus: "not_requested",
    retryDisposition: "fail_fast",
    failureReason: null,
    observation: {
      verificationRequested: false,
      verificationSkipped: true,
      verificationStatus: "not_requested"
    }
  });
});

test("requested verification uses passed and failed tri-state values", () => {
  assert.equal(protocol.withVerificationStatus({ verified: true }, "passed").verificationStatus, "passed");
  assert.equal(protocol.withVerificationStatus({ verified: true }, "passed").verified, true);
  assert.equal(protocol.withVerificationStatus({ verified: false }, "failed").verificationStatus, "failed");
  assert.equal(protocol.withVerificationStatus({ verified: false }, "failed").verified, false);
});

test("the keyed queue serializes one tab without blocking another tab", async () => {
  const queue = protocol.createKeyedSerialQueue();
  const events = [];
  let releaseFirst;
  const firstGate = new Promise((resolve) => {
    releaseFirst = resolve;
  });

  const first = queue.run(10, async () => {
    events.push("tab-10:first:start");
    await firstGate;
    events.push("tab-10:first:end");
  });
  const second = queue.run(10, async () => {
    events.push("tab-10:second:start");
    events.push("tab-10:second:end");
  });
  const otherTab = queue.run(11, async () => {
    events.push("tab-11:start");
    events.push("tab-11:end");
  });

  await otherTab;
  assert.deepEqual(events, [
    "tab-10:first:start",
    "tab-11:start",
    "tab-11:end"
  ]);

  releaseFirst();
  await Promise.all([first, second]);
  assert.deepEqual(events, [
    "tab-10:first:start",
    "tab-11:start",
    "tab-11:end",
    "tab-10:first:end",
    "tab-10:second:start",
    "tab-10:second:end"
  ]);
  assert.equal(queue.size, 0);
});

test("a rejected tab action does not poison the next queued action", async () => {
  const queue = protocol.createKeyedSerialQueue();
  const failure = queue.run(4, async () => {
    throw new Error("expected failure");
  });
  const recovery = queue.run(4, async () => "recovered");

  await assert.rejects(failure, /expected failure/);
  assert.equal(await recovery, "recovered");
  assert.equal(queue.size, 0);
});

test("candidate filtering happens before the result limit is applied", () => {
  const candidates = [
    { id: "hidden-high-score", visible: false },
    { id: "visible-second", visible: true },
    { id: "visible-third", visible: true }
  ];

  const selected = protocol.filterThenLimit(candidates, (candidate) => candidate.visible, 2);

  assert.deepEqual(selected.map((candidate) => candidate.id), ["visible-second", "visible-third"]);
});

test("implicit roles cover modern native controls and preserve legacy query aliases", () => {
  assert.equal(protocol.implicitRoleFor("summary", {}), "button");
  assert.equal(protocol.implicitRoleFor("input", { type: "search" }), "searchbox");
  assert.equal(protocol.implicitRoleFor("input", { type: "number" }), "spinbutton");
  assert.equal(protocol.implicitRoleFor("select", { multiple: "" }), "listbox");
  assert.equal(protocol.implicitRoleFor("nav", {}), "navigation");
  assert.equal(protocol.implicitRoleFor("progress", {}), "progressbar");
  assert.equal(protocol.roleMatches("input", "searchbox"), true);
  assert.equal(protocol.roleMatches("textarea", "textbox"), true);
  assert.equal(protocol.roleMatches("button", "link"), false);
});

test("stability comparison can be shared by a batch of candidate samples", () => {
  const baseline = {
    attached: true,
    visible: true,
    notOccluded: true,
    rect: { left: 10, top: 20, width: 100, height: 30 }
  };

  assert.equal(protocol.samplesAreStable(baseline, {
    ...baseline,
    rect: { left: 12, top: 19, width: 101, height: 30 }
  }), true);
  assert.equal(protocol.samplesAreStable(baseline, {
    ...baseline,
    rect: { left: 15, top: 20, width: 100, height: 30 }
  }), false);
});

test("an accessibility node handle carries document, frame and backend node identity", () => {
  const identity = protocol.createDocumentIdentity(() => "ax-document");
  const nodeId = protocol.createAxNodeId(identity, "FRAME-42", 901);

  assert.deepEqual(protocol.parseNodeId(nodeId), {
    kind: "ax",
    pageNonce: identity.pageNonce,
    frameId: "FRAME-42",
    backendNodeId: 901
  });
});

test("malformed encoded node handles are rejected instead of throwing", () => {
  const identity = protocol.createDocumentIdentity(() => "safe-document");

  assert.equal(protocol.parseNodeId("dom:%zz:1:1"), null);
  assert.equal(protocol.nodeRefMatchesDocument({
    nodeId: "dom:%zz:1:1",
    documentEpoch: 1
  }, identity, 1), false);
});
