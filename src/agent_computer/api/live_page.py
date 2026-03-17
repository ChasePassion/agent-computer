from __future__ import annotations

from typing import Literal

ObservationMode = Literal["preview", "grid"]

_STYLE = """
:root {
  color-scheme: dark;
  --bg: #0b1016;
  --panel: #0f1722;
  --panel-2: #121d2a;
  --line: #223043;
  --text: #e7eef7;
  --muted: #94a7ba;
  --blue: #79c0ff;
  --green: #7ee787;
  --red: #ff8e8e;
  --yellow: #f2cc60;
  --font: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  background: linear-gradient(180deg, #0c1218, var(--bg));
  color: var(--text);
  font: 14px/1.55 var(--font);
}
.shell { width: min(1180px, calc(100vw - 18px)); margin: 0 auto; padding: 10px 0 18px; }
.topbar, .card { border: 1px solid var(--line); border-radius: 14px; background: var(--panel); }
.topbar {
  position: sticky; top: 0; z-index: 10; display: flex; gap: 10px; flex-wrap: wrap;
  justify-content: space-between; align-items: center; margin-bottom: 10px; padding: 10px 12px;
}
.chips, .actions, .button-row, .pill-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.chip, .pill {
  min-height: 32px; padding: 6px 10px; border: 1px solid var(--line); border-radius: 999px;
  background: rgba(255,255,255,.04); color: var(--muted); font-size: 12px;
}
.chip strong { color: var(--text); }
.layout { display: grid; gap: 10px; }
.card-head {
  display: flex; gap: 12px; flex-wrap: wrap; justify-content: space-between; align-items: center;
  padding: 12px 14px; border-bottom: 1px solid var(--line);
}
.card-title { color: var(--blue); font-size: 13px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.card-meta, .help, .status, .session-line, .terminal-note, .entry-meta { color: var(--muted); font-size: 12px; }
.screen-body { padding: 12px; min-height: min(62vh, 720px); }
.screen-frame {
  position: relative;
  display: flex; align-items: center; justify-content: center; min-height: min(56vh, 660px);
  overflow: hidden; border: 1px solid var(--line); border-radius: 12px; background: #060b10;
}
#frame {
  display: block; width: 100%; height: auto; max-height: min(58vh, 700px); object-fit: contain;
  background: #05080d; cursor: crosshair;
}
#frame.busy { cursor: progress; }
.crosshair {
  position: absolute; width: 18px; height: 18px; margin-left: -9px; margin-top: -9px;
  border: 2px solid var(--green); border-radius: 999px; pointer-events: none;
  box-shadow: 0 0 0 1px rgba(0,0,0,.5); display: none;
}
.crosshair::before, .crosshair::after {
  content: ""; position: absolute; background: var(--green);
}
.crosshair::before { left: 50%; top: -5px; width: 2px; height: 26px; transform: translateX(-50%); }
.crosshair::after { top: 50%; left: -5px; width: 26px; height: 2px; transform: translateY(-50%); }
.control-body, .codex-body { display: grid; gap: 10px; padding: 12px; background: var(--panel-2); }
.panel {
  display: grid; gap: 8px; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: #0f1721;
}
.panel h3 { margin: 0; font-size: 12px; color: var(--text); text-transform: uppercase; letter-spacing: .06em; }
.status { min-height: 18px; }
.status.error { color: var(--red); }
.status.ok { color: var(--green); }
.pill.running, .entry-status.running, .entry-label.assistant { color: var(--green); }
.pill.idle, .pill.attach, .entry-label.command, .entry-label.patch, .entry-label.mcp, .entry-label.web-search, .entry-label.tool { color: var(--blue); }
.pill.waiting, .pill.stalled, .entry-label.plan, .entry-label.reasoning, .entry-status.waiting { color: var(--yellow); }
.pill.error, .entry-label.error, .entry-status.failed { color: var(--red); }
.terminal { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: #0b1118; }
.terminal-head { padding: 10px 12px; border-bottom: 1px solid var(--line); background: #0f1721; }
.terminal-title { color: var(--text); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
.terminal-body { min-height: 320px; max-height: min(58vh, 720px); overflow: auto; padding: 8px 0; }
.terminal-empty { padding: 14px 16px; color: var(--muted); }
.entry { display: grid; grid-template-columns: 92px minmax(0,1fr); gap: 10px; padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,.04); }
.entry:last-child { border-bottom: 0; }
.entry-label { font-size: 11px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.entry-main { min-width: 0; display: grid; gap: 6px; }
.entry-head { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; color: var(--muted); font-size: 12px; }
.entry-title { color: var(--text); font-weight: 700; }
.entry-status { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.entry-text { color: var(--text); white-space: normal; word-break: break-word; line-height: 1.62; }
button, textarea, input {
  border: 1px solid var(--line); border-radius: 10px; background: #0a1119; color: var(--text); font: inherit;
}
button {
  min-height: 40px; min-width: 84px; padding: 10px 14px; background: rgba(255,255,255,.04); cursor: pointer;
}
button.active { border-color: rgba(121,192,255,.4); color: var(--blue); background: rgba(121,192,255,.12); }
button.primary { border-color: rgba(126,231,135,.25); background: rgba(126,231,135,.12); color: var(--green); }
button.warn { border-color: rgba(242,204,96,.25); background: rgba(242,204,96,.12); color: var(--yellow); }
button[disabled], textarea:disabled, input:disabled { opacity: .55; cursor: not-allowed; }
textarea { width: 100%; min-height: 92px; padding: 12px; resize: vertical; }
input[type="number"] { width: 120px; padding: 10px 12px; }
.inline-form { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.rich-text code.inline-code {
  display: inline-block; padding: 1px 6px; margin: 0 1px; border: 1px solid rgba(121,192,255,.16);
  border-radius: 8px; background: rgba(121,192,255,.1); color: var(--blue);
}
.rich-text pre.code-block {
  margin: 0; padding: 12px; overflow: auto; border: 1px solid rgba(121,192,255,.12);
  border-radius: 12px; background: #081019; color: #d9f3ff; white-space: pre-wrap; word-break: break-word;
}
@media (max-width: 720px) {
  .shell { width: min(100vw - 10px, 100%); padding-top: 6px; }
  .screen-body { min-height: 230px; padding: 10px; }
  .screen-frame { min-height: 210px; }
  .terminal-body { min-height: 280px; max-height: 52vh; }
  .entry { grid-template-columns: 1fr; gap: 6px; }
  .inline-form input[type="number"] { width: 100%; }
}
"""

_BODY = """
<div class="shell" data-token="{token}" data-mode="{initial_mode}">
  <div class="topbar">
    <div class="chips">
      <div class="chip">Mode <strong id="mode-label">{initial_mode}</strong></div>
      <div class="chip">Screen <strong id="updated-label">warming up</strong></div>
      <div class="chip">Resolution <strong id="resolution-label">-</strong></div>
      <div class="chip">Cursor <strong id="cursor-label">-</strong></div>
    </div>
    <div class="actions">
      <button id="preview-btn" type="button">Preview</button>
      <button id="grid-btn" type="button">Grid</button>
    </div>
  </div>

  <div class="layout">
    <section class="card">
      <div class="card-head">
        <div class="card-title">Screen Live</div>
        <div class="card-meta" id="screen-meta">Watching latest desktop frame</div>
      </div>
      <div class="screen-body">
        <div class="screen-frame">
          <img id="frame" alt="live observation frame">
          <div id="crosshair" class="crosshair"></div>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="card-head">
        <div class="card-title">Remote Control</div>
        <div class="card-meta">Select a point first, then execute actions.</div>
      </div>
      <div class="control-body">
        <div class="panel">
          <h3>Pointer</h3>
          <div class="help">Tap the image above to select a desktop coordinate. Actions target the current selected point.</div>
          <div class="button-row">
            <button id="click-btn" type="button" class="primary">Click</button>
            <button id="double-click-btn" type="button">Double Click</button>
            <button id="right-click-btn" type="button">Right Click</button>
          </div>
        </div>

        <div class="panel">
          <h3>Scroll</h3>
          <div class="inline-form">
            <input id="scroll-amount" type="number" value="600" step="50">
            <button id="scroll-up-btn" type="button">Scroll Up</button>
            <button id="scroll-down-btn" type="button">Scroll Down</button>
          </div>
        </div>

        <div class="panel">
          <h3>Message To Codex</h3>
          <textarea id="message-input" rows="4" placeholder="Write text here, then paste it into the focused Codex input."></textarea>
          <div class="button-row">
            <button id="paste-btn" type="button" class="primary">Paste</button>
            <button id="paste-enter-btn" type="button" class="warn">Paste + Enter</button>
            <button id="ctrl-c-btn" type="button">Ctrl+C</button>
            <button id="enter-btn" type="button">Enter</button>
            <button id="backspace-btn" type="button">Backspace</button>
            <button id="esc-btn" type="button">Esc</button>
          </div>
          <div class="help">These actions operate on the current foreground window. Focus the Codex input box first.</div>
        </div>

        <div id="control-status" class="status">Waiting for first frame.</div>
      </div>
    </section>

    <section class="card">
      <div class="card-head">
        <div class="card-title">Codex Live</div>
        <div class="card-meta" id="output-updated-label">Updated -</div>
      </div>
      <div class="codex-body">
        <div class="pill-row">
          <div id="output-status-pill" class="pill">No Output</div>
          <div id="session-mode-pill" class="pill">No Session</div>
        </div>
        <div id="session-line" class="session-line">Waiting for Codex output</div>

        <div class="terminal">
          <div class="terminal-head">
            <div class="terminal-title">Transcript</div>
            <div id="terminal-note" class="terminal-note">Assistant replies, tool calls, plan changes, reasoning summaries, and errors appear here in one stream.</div>
          </div>
          <div id="terminal-body" class="terminal-body">
            <div class="terminal-empty">No Codex output yet.</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</div>
"""

_SCRIPT = """
const shell = document.querySelector(".shell");
const token = shell.dataset.token;
let mode = shell.dataset.mode;
let lastFrameSeq = -1;
let pollTimer = null;
let frameMeta = null;
let selectedPoint = null;
let controlBusy = false;

const frame = document.getElementById("frame");
const crosshair = document.getElementById("crosshair");
const modeLabel = document.getElementById("mode-label");
const updatedLabel = document.getElementById("updated-label");
const resolutionLabel = document.getElementById("resolution-label");
const cursorLabel = document.getElementById("cursor-label");
const previewBtn = document.getElementById("preview-btn");
const gridBtn = document.getElementById("grid-btn");
const screenMeta = document.getElementById("screen-meta");
const controlStatus = document.getElementById("control-status");
const scrollAmount = document.getElementById("scroll-amount");
const messageInput = document.getElementById("message-input");
const outputUpdatedLabel = document.getElementById("output-updated-label");
const outputStatusPill = document.getElementById("output-status-pill");
const sessionModePill = document.getElementById("session-mode-pill");
const sessionLine = document.getElementById("session-line");
const terminalNote = document.getElementById("terminal-note");
const terminalBody = document.getElementById("terminal-body");
const pointButtons = [
  document.getElementById("click-btn"),
  document.getElementById("double-click-btn"),
  document.getElementById("right-click-btn"),
];
const actionButtons = [
  ...pointButtons,
  document.getElementById("scroll-up-btn"),
  document.getElementById("scroll-down-btn"),
  document.getElementById("paste-btn"),
  document.getElementById("paste-enter-btn"),
  document.getElementById("ctrl-c-btn"),
  document.getElementById("enter-btn"),
  document.getElementById("backspace-btn"),
  document.getElementById("esc-btn"),
];

function liveStateUrl() { return `/live/state.json?token=${encodeURIComponent(token)}&mode=${encodeURIComponent(mode)}`; }
function controlUrl(path) { return `/live/control/${path}?token=${encodeURIComponent(token)}`; }
function parseTime(value) { const ms = Date.parse(value || ""); return Number.isNaN(ms) ? null : ms; }
function shortId(value) { const s = String(value || "").trim(); return !s ? "-" : (s.length <= 14 ? s : `${s.slice(0, 8)}…${s.slice(-4)}`); }
function normalizeKind(kind) {
  const v = String(kind || "assistant").trim();
  return v === "web_search" ? "web-search" : ((v === "commentary" || v === "final") ? "assistant" : (v || "assistant"));
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderRichText(value) {
  const source = String(value || "");
  if (!source) return "";
  const blocks = [];
  let html = escapeHtml(source).replace(/```([\\s\\S]*?)```/g, (_, code) => {
    const index = blocks.length;
    const trimmed = String(code || "").replace(/^\\n+/, "").replace(/\\n+$/, "");
    blocks.push(`<pre class="code-block"><code>${trimmed}</code></pre>`);
    return `@@CODEBLOCK${index}@@`;
  });
  html = html.replace(/`([^`\\n]+)`/g, '<code class="inline-code">$1</code>');
  html = html.replace(/\\n/g, "<br>");
  html = html.replace(/@@CODEBLOCK(\\d+)@@/g, (_, index) => blocks[Number(index)] || "");
  return `<div class="rich-text">${html}</div>`;
}

function updateModeButtons() {
  previewBtn.classList.toggle("active", mode === "preview");
  gridBtn.classList.toggle("active", mode === "grid");
  modeLabel.textContent = mode;
}

function setStatus(text, kind = "info") {
  controlStatus.textContent = text;
  controlStatus.className = kind === "error" ? "status error" : (kind === "ok" ? "status ok" : "status");
}

function updateControlAvailability() {
  const hasPoint = Boolean(selectedPoint);
  pointButtons.forEach((button) => { button.disabled = !hasPoint || controlBusy; });
  actionButtons.filter((button) => !pointButtons.includes(button)).forEach((button) => { button.disabled = controlBusy; });
  frame.classList.toggle("busy", controlBusy);
}

function setSelectedPoint(point, clientPoint = null) {
  selectedPoint = point;
  if (point && clientPoint) {
    crosshair.style.left = `${clientPoint.x}px`;
    crosshair.style.top = `${clientPoint.y}px`;
    crosshair.style.display = "block";
  }
  updateControlAvailability();
}

function applyFrame(framePayload) {
  frameMeta = framePayload;
  updatedLabel.textContent = framePayload.updated_at || "-";
  resolutionLabel.textContent = `${framePayload.desktop_width || framePayload.width}x${framePayload.desktop_height || framePayload.height}`;
  const cursor = framePayload.mouse_position;
  cursorLabel.textContent = cursor ? `(${cursor.x}, ${cursor.y})` : "-";
  screenMeta.textContent = `Watching latest ${mode} frame`;
  if (framePayload.frame_seq !== lastFrameSeq) {
    frame.src = `${framePayload.image_url}&ts=${Date.now()}`;
    lastFrameSeq = framePayload.frame_seq;
  }
}

function parseFramePoint(event) {
  if (!frameMeta) return null;
  const rect = frame.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const rawX = Math.max(0, Math.min(event.clientX - rect.left, rect.width));
  const rawY = Math.max(0, Math.min(event.clientY - rect.top, rect.height));
  const width = Number(frameMeta.desktop_width || frameMeta.width || 0);
  const height = Number(frameMeta.desktop_height || frameMeta.height || 0);
  if (!width || !height) return null;
  const x = Math.round((rawX / rect.width) * width);
  const y = Math.round((rawY / rect.height) * height);
  return {
    point: { x: Math.max(0, Math.min(x, width)), y: Math.max(0, Math.min(y, height)) },
    clientPoint: { x: rawX, y: rawY },
  };
}

function outputState(output) {
  if (!output || output.status === "no_output") return { text: "No Output", cls: "pill", detail: "Waiting for Codex transcript" };
  if (output.last_error && output.thread_status_type === "systemError") return { text: "Recoverable Error", cls: "pill error", detail: "Codex output bridge reported a recoverable error" };
  if (output.status === "idle") return { text: "Idle", cls: "pill idle", detail: "Codex is idle" };
  const staleAfterSec = Number(output.stale_after_seconds || 15);
  const heartbeatMs = parseTime(output.heartbeat_at || output.updated_at);
  if (heartbeatMs !== null && Date.now() - heartbeatMs > staleAfterSec * 1000) return { text: "Possible Stall", cls: "pill stalled", detail: "Running without recent heartbeat" };
  if (Array.isArray(output?.thread_active_flags) && output.thread_active_flags.includes("waitingOnApproval")) return { text: "Waiting", cls: "pill waiting", detail: "Codex is waiting on approval" };
  return { text: "Running", cls: "pill running", detail: "Codex is actively producing output" };
}

function sessionState(output) {
  if (!output || output.session_mode === "none") return { text: "No Session", cls: "pill", detail: "No Codex session metadata available" };
  if (output.session_mode === "managed") return { text: "Managed", cls: "pill attach", detail: "Watching a managed local Codex session" };
  return { text: "Readonly", cls: "pill attach", detail: "Watching an existing local Codex session" };
}

function buildTimeline(output) {
  const rows = [];
  const recent = Array.isArray(output?.recent) ? output.recent : [];
  const activity = Array.isArray(output?.recent_activity) ? output.recent_activity : [];

  for (const item of recent) {
    rows.push({
      id: `recent:${item.seq}`,
      sortAt: item.created_at || output?.updated_at || "",
      kind: item.kind === "tool" ? "tool" : "assistant",
      title: item.kind === "final" ? "Final reply" : "Assistant",
      status: item.kind === "final" ? "completed" : "info",
      text: item.text || "",
      meta: [item.created_at || ""].filter(Boolean),
    });
  }
  for (const item of activity) {
    const text = [item.detail || "", item.preview || ""].filter(Boolean).join("\\n\\n");
    const meta = [item.updated_at || "", ...(Array.isArray(item.meta) ? item.meta.filter(Boolean).map(String) : [])].filter(Boolean);
    rows.push({
      id: `activity:${item.id}`,
      sortAt: item.created_at || item.updated_at || output?.updated_at || "",
      kind: normalizeKind(item.kind || "tool"),
      title: item.title || item.kind || "Activity",
      status: item.status || "info",
      text,
      meta,
    });
  }
  if (output?.plan && (output.plan.text || output.plan.explanation || (Array.isArray(output.plan.steps) && output.plan.steps.length))) {
    const lines = [];
    if (output.plan.explanation) lines.push(output.plan.explanation);
    else if (output.plan.text) lines.push(output.plan.text);
    for (const step of Array.isArray(output.plan.steps) ? output.plan.steps : []) lines.push(`${step?.status ? `[${step.status}] ` : ""}${step?.step || ""}`.trim());
    rows.push({
      id: "plan:current",
      sortAt: output.plan.updated_at || output.updated_at || "",
      kind: "plan",
      title: "Plan",
      status: "info",
      text: lines.join("\\n"),
      meta: [output.plan.updated_at || ""].filter(Boolean),
    });
  }
  if (output?.reasoning?.text) {
    rows.push({
      id: "reasoning:current",
      sortAt: output.reasoning.updated_at || output.updated_at || "",
      kind: "reasoning",
      title: output.reasoning.kind === "raw" ? "Reasoning" : "Reasoning summary",
      status: "info",
      text: output.reasoning.text,
      meta: [output.reasoning.updated_at || ""].filter(Boolean),
    });
  }
  if (output?.active_text) {
    rows.push({
      id: "assistant:active",
      sortAt: output.updated_at || output.heartbeat_at || "",
      kind: "assistant",
      title: "Assistant",
      status: "running",
      text: output.active_text,
      meta: [output.updated_at || ""].filter(Boolean),
    });
  }
  const hasMatchingError = activity.some((item) => (item.kind || "") === "error" && item.detail === output?.last_error);
  if (output?.last_error && !hasMatchingError) {
    rows.push({
      id: "error:last",
      sortAt: output.updated_at || output.heartbeat_at || "",
      kind: "error",
      title: "Error",
      status: "failed",
      text: output.last_error,
      meta: [output.updated_at || ""].filter(Boolean),
    });
  }
  rows.sort((a, b) => (parseTime(a.sortAt) ?? 0) - (parseTime(b.sortAt) ?? 0) || a.id.localeCompare(b.id));
  return rows;
}

function renderTerminal(output) {
  const rows = buildTimeline(output);
  if (!rows.length) {
    terminalBody.innerHTML = '<div class="terminal-empty">No Codex output yet.</div>';
    return;
  }
  terminalBody.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const row of rows) {
    const entry = document.createElement("div");
    entry.className = "entry";
    const label = document.createElement("div");
    label.className = `entry-label ${normalizeKind(row.kind)}`;
    label.textContent = normalizeKind(row.kind);
    const main = document.createElement("div");
    main.className = "entry-main";
    const head = document.createElement("div");
    head.className = "entry-head";
    const title = document.createElement("span");
    title.className = "entry-title";
    title.textContent = row.title || normalizeKind(row.kind);
    head.appendChild(title);
    if (row.status) {
      const status = document.createElement("span");
      status.className = `entry-status ${row.status}`;
      status.textContent = row.status;
      head.appendChild(status);
    }
    main.appendChild(head);
    if (Array.isArray(row.meta) && row.meta.length) {
      const meta = document.createElement("div");
      meta.className = "entry-meta";
      meta.textContent = row.meta.join(" · ");
      main.appendChild(meta);
    }
    if (row.text) {
      const text = document.createElement("div");
      text.className = "entry-text";
      text.innerHTML = renderRichText(row.text);
      main.appendChild(text);
    }
    entry.appendChild(label);
    entry.appendChild(main);
    frag.appendChild(entry);
  }
  terminalBody.appendChild(frag);
  terminalBody.scrollTop = terminalBody.scrollHeight;
}

function applyOutput(output) {
  const state = outputState(output);
  const session = sessionState(output);
  outputStatusPill.textContent = state.text;
  outputStatusPill.className = state.cls;
  sessionModePill.textContent = session.text;
  sessionModePill.className = session.cls;
  const flags = Array.isArray(output?.thread_active_flags) && output.thread_active_flags.length ? ` · flags ${output.thread_active_flags.join(", ")}` : "";
  sessionLine.textContent = `${session.detail} · thread ${shortId(output?.thread_id)} · turn ${shortId(output?.turn_id)}${flags}`;
  terminalNote.textContent = output?.last_error ? `Latest issue: ${output.last_error}` : state.detail;
  outputUpdatedLabel.textContent = `Updated ${output?.updated_at || "-"}`;
  renderTerminal(output);
}

function resetOutput() {
  outputStatusPill.textContent = "No Output";
  outputStatusPill.className = "pill";
  sessionModePill.textContent = "No Session";
  sessionModePill.className = "pill";
  sessionLine.textContent = "Waiting for Codex output";
  terminalNote.textContent = "Waiting for Codex transcript";
  outputUpdatedLabel.textContent = "Updated -";
  terminalBody.innerHTML = '<div class="terminal-empty">No Codex output yet.</div>';
}

async function parseErrorResponse(response) {
  try {
    const payload = await response.json();
    if (payload?.detail) return String(payload.detail);
    if (payload?.error?.message) return String(payload.error.message);
  } catch (_error) {}
  return `HTTP ${response.status}`;
}

async function runControl(label, path, payload) {
  if (controlBusy) return null;
  controlBusy = true;
  updateControlAvailability();
  setStatus(`${label}...`);
  try {
    const response = await fetch(controlUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await parseErrorResponse(response));
    const result = await response.json();
    setStatus(`${label} completed`, "ok");
    triggerImmediatePoll();
    return result;
  } catch (error) {
    setStatus(String(error?.message || error), "error");
    return null;
  } finally {
    controlBusy = false;
    updateControlAvailability();
  }
}

async function runHotkey(label, keys) {
  return runControl(label, "hotkey", { keys });
}

async function runPress(label, key) {
  return runControl(label, "press", { key });
}

function triggerImmediatePoll() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  poll();
}

async function poll() {
  try {
    const response = await fetch(liveStateUrl(), { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    applyFrame(payload.frame);
    applyOutput(payload.output);
    if (!selectedPoint) setStatus("Tap the screen image to pick a point.");
  } catch (_error) {
    updatedLabel.textContent = "waiting";
    resolutionLabel.textContent = "-";
    cursorLabel.textContent = "-";
    screenMeta.textContent = "Waiting for daemon";
    setStatus("Waiting for daemon", "error");
    resetOutput();
  } finally {
    pollTimer = window.setTimeout(poll, 1000);
  }
}

frame.addEventListener("click", (event) => {
  const parsed = parseFramePoint(event);
  if (!parsed) {
    setStatus("Unable to map the selected point yet.", "error");
    return;
  }
  setSelectedPoint(parsed.point, parsed.clientPoint);
  setStatus(`Selected point (${parsed.point.x}, ${parsed.point.y})`, "ok");
});

document.getElementById("click-btn").addEventListener("click", async () => {
  if (!selectedPoint) return;
  await runControl("Click", "click", { ...selectedPoint, button: "left", double: false });
});

document.getElementById("double-click-btn").addEventListener("click", async () => {
  if (!selectedPoint) return;
  await runControl("Double click", "click", { ...selectedPoint, button: "left", double: true });
});

document.getElementById("right-click-btn").addEventListener("click", async () => {
  if (!selectedPoint) return;
  await runControl("Right click", "click", { ...selectedPoint, button: "right", double: false });
});

document.getElementById("scroll-up-btn").addEventListener("click", async () => {
  const amount = Math.abs(Number(scrollAmount.value || 0)) || 600;
  await runControl("Scroll up", "scroll", { amount });
});

document.getElementById("scroll-down-btn").addEventListener("click", async () => {
  const amount = Math.abs(Number(scrollAmount.value || 0)) || 600;
  await runControl("Scroll down", "scroll", { amount: -amount });
});

document.getElementById("paste-btn").addEventListener("click", async () => {
  const text = messageInput.value;
  if (!text.trim()) {
    setStatus("Write a message first.", "error");
    return;
  }
  await runControl("Paste", "paste", { text, restore_clipboard: false });
});

document.getElementById("paste-enter-btn").addEventListener("click", async () => {
  const text = messageInput.value;
  if (!text.trim()) {
    setStatus("Write a message first.", "error");
    return;
  }
  const pasted = await runControl("Paste", "paste", { text, restore_clipboard: false });
  if (pasted) await runPress("Enter", "enter");
});

document.getElementById("ctrl-c-btn").addEventListener("click", async () => {
  await runHotkey("Ctrl+C", ["ctrl", "c"]);
});

document.getElementById("enter-btn").addEventListener("click", async () => {
  await runPress("Enter", "enter");
});

document.getElementById("backspace-btn").addEventListener("click", async () => {
  await runPress("Backspace", "backspace");
});

document.getElementById("esc-btn").addEventListener("click", async () => {
  await runPress("Esc", "esc");
});

previewBtn.addEventListener("click", () => {
  if (mode !== "preview") {
    mode = "preview";
    updateModeButtons();
    triggerImmediatePoll();
  }
});

gridBtn.addEventListener("click", () => {
  if (mode !== "grid") {
    mode = "grid";
    updateModeButtons();
    triggerImmediatePoll();
  }
});

updateModeButtons();
updateControlAvailability();
resetOutput();
poll();
"""


def render_live_page(*, token: str, initial_mode: ObservationMode = "preview") -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Agent Computer Live</title>"
        f"<style>{_STYLE}</style></head><body>"
        f"{_BODY.format(token=token, initial_mode=initial_mode)}"
        f"<script>{_SCRIPT}</script></body></html>"
    )
