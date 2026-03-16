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
  --green: #7ee787;
  --blue: #79c0ff;
  --yellow: #f2cc60;
  --red: #ff8e8e;
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
.chips, .actions, .pill-row, .composer-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.chip, .pill {
  min-height: 32px; padding: 6px 10px; border: 1px solid var(--line); border-radius: 999px;
  background: rgba(255,255,255,.04); color: var(--muted); font-size: 12px;
}
.chip strong { color: var(--text); }
button, textarea {
  border: 1px solid var(--line); border-radius: 10px; background: #0a1119; color: var(--text); font: inherit;
}
button { min-height: 40px; min-width: 84px; padding: 10px 14px; background: rgba(255,255,255,.04); cursor: pointer; }
button.active { border-color: rgba(121,192,255,.4); color: var(--blue); background: rgba(121,192,255,.12); }
button[disabled], textarea:disabled { opacity: .55; cursor: not-allowed; }
.layout { display: grid; gap: 10px; }
.card-head {
  display: flex; gap: 12px; flex-wrap: wrap; justify-content: space-between; align-items: center;
  padding: 12px 14px; border-bottom: 1px solid var(--line);
}
.card-title { color: var(--blue); font-size: 13px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.card-meta, .session-line, .terminal-note, .composer-hint, .composer-error, .entry-meta { color: var(--muted); font-size: 12px; }
.screen-body { padding: 12px; min-height: min(62vh, 720px); }
.screen-frame {
  display: flex; align-items: center; justify-content: center; min-height: min(56vh, 660px);
  overflow: hidden; border: 1px solid var(--line); border-radius: 12px; background: #060b10;
}
img { display: block; width: 100%; height: auto; max-height: min(58vh, 700px); object-fit: contain; background: #05080d; }
.codex-body { display: grid; gap: 10px; padding: 12px; background: var(--panel-2); }
.pill.running, .entry-status.running, .entry-label.assistant { color: var(--green); }
.pill.idle, .pill.attach, .pill.managed, .entry-label.command, .entry-label.patch, .entry-label.mcp, .entry-label.web-search, .entry-label.tool { color: var(--blue); }
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
.composer { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: #0f1721; }
textarea { width: 100%; min-height: 82px; padding: 12px; resize: vertical; }
.composer-foot { display: flex; gap: 8px; flex-wrap: wrap; justify-content: space-between; align-items: center; }
.composer-error { min-height: 18px; color: var(--red); }
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
        </div>
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
        <div id="session-line" class="session-line">Waiting for Codex session</div>

        <div class="terminal">
          <div class="terminal-head">
            <div class="terminal-title">Transcript</div>
            <div id="terminal-note" class="terminal-note">Assistant replies, tool calls, plan changes, reasoning summaries, and errors appear here in one stream.</div>
          </div>
          <div id="terminal-body" class="terminal-body">
            <div class="terminal-empty">No Codex output yet.</div>
          </div>
        </div>

        <div class="composer">
          <form id="message-form">
            <textarea id="message-input" rows="3" placeholder="Send a message to the current Codex session"></textarea>
          </form>
          <div class="composer-foot">
            <div class="composer-actions">
              <button id="send-btn" type="submit" form="message-form">Send</button>
              <button id="interrupt-btn" type="button">Interrupt</button>
            </div>
            <div id="composer-hint" class="composer-hint">Live page can take over the current local Codex thread.</div>
          </div>
          <div id="message-error" class="composer-error"></div>
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
let lastOutputSeq = -1;
let pollTimer = null;
let submittingMessage = false;
let interruptingTurn = false;

const frame = document.getElementById("frame");
const modeLabel = document.getElementById("mode-label");
const updatedLabel = document.getElementById("updated-label");
const resolutionLabel = document.getElementById("resolution-label");
const cursorLabel = document.getElementById("cursor-label");
const previewBtn = document.getElementById("preview-btn");
const gridBtn = document.getElementById("grid-btn");
const screenMeta = document.getElementById("screen-meta");
const outputUpdatedLabel = document.getElementById("output-updated-label");
const outputStatusPill = document.getElementById("output-status-pill");
const sessionModePill = document.getElementById("session-mode-pill");
const sessionLine = document.getElementById("session-line");
const terminalNote = document.getElementById("terminal-note");
const terminalBody = document.getElementById("terminal-body");
const messageForm = document.getElementById("message-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const interruptBtn = document.getElementById("interrupt-btn");
const composerHint = document.getElementById("composer-hint");
const messageError = document.getElementById("message-error");

function liveStateUrl() { return `/live/state.json?token=${encodeURIComponent(token)}&mode=${encodeURIComponent(mode)}`; }
function liveMessageUrl() { return `/live/session/message?token=${encodeURIComponent(token)}`; }
function liveInterruptUrl() { return `/live/session/interrupt?token=${encodeURIComponent(token)}`; }
function parseTime(value) { const ms = Date.parse(value || ""); return Number.isNaN(ms) ? null : ms; }
function shortId(value) { const s = String(value || "").trim(); return !s ? "-" : (s.length <= 14 ? s : `${s.slice(0, 8)}…${s.slice(-4)}`); }
function normalizeKind(kind) { const v = String(kind || "assistant").trim(); return v === "web_search" ? "web-search" : ((v === "commentary" || v === "final") ? "assistant" : (v || "assistant")); }

function escapeHtml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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

function outputState(output) {
  if (!output || output.status === "no_output") return { text: "No Output", cls: "pill", detail: "Waiting for Codex session" };
  if (output.last_error && output.thread_status_type === "systemError") return { text: "Recoverable Error", cls: "pill error", detail: "The bridge closed; sending again will rebuild it" };
  if (output.status === "idle") return { text: "Idle", cls: "pill idle", detail: "Codex is idle" };
  const staleAfterSec = Number(output.stale_after_seconds || 15);
  const heartbeatMs = parseTime(output.heartbeat_at || output.updated_at);
  if (heartbeatMs !== null && Date.now() - heartbeatMs > staleAfterSec * 1000) return { text: "Possible Stall", cls: "pill stalled", detail: "Running without recent heartbeat" };
  if (Array.isArray(output?.thread_active_flags) && output.thread_active_flags.includes("waitingOnApproval")) return { text: "Waiting", cls: "pill waiting", detail: "Codex is waiting on approval" };
  return { text: "Running", cls: "pill running", detail: "Codex is actively producing output" };
}

function sessionState(output) {
  if (!output || output.session_mode === "none") return { text: "No Session", cls: "pill", detail: "Ready to start or resume a managed Codex session" };
  if (output.session_mode === "managed") return { text: "Managed", cls: "pill managed", detail: "Live page is controlling a managed local Codex session" };
  return { text: "Readonly", cls: "pill attach", detail: "Watching an existing local Codex session" };
}

function buildTimeline(output) {
  const rows = [];
  const recent = Array.isArray(output?.recent) ? output.recent : [];
  const activity = Array.isArray(output?.recent_activity) ? output.recent_activity : [];

  for (const item of recent) {
    rows.push({ id: `recent:${item.seq}`, sortAt: item.created_at || output?.updated_at || "", kind: item.kind === "tool" ? "tool" : "assistant", title: item.kind === "final" ? "Final reply" : "Assistant", status: item.kind === "final" ? "completed" : "info", text: item.text || "", meta: [item.created_at || ""].filter(Boolean) });
  }
  for (const item of activity) {
    const text = [item.detail || "", item.preview || ""].filter(Boolean).join("\\n\\n");
    const meta = [item.updated_at || "", ...(Array.isArray(item.meta) ? item.meta.filter(Boolean).map(String) : [])].filter(Boolean);
    rows.push({ id: `activity:${item.id}`, sortAt: item.created_at || item.updated_at || output?.updated_at || "", kind: normalizeKind(item.kind || "tool"), title: item.title || item.kind || "Activity", status: item.status || "info", text, meta });
  }
  if (output?.plan && (output.plan.text || output.plan.explanation || (Array.isArray(output.plan.steps) && output.plan.steps.length))) {
    const lines = [];
    if (output.plan.explanation) lines.push(output.plan.explanation);
    else if (output.plan.text) lines.push(output.plan.text);
    for (const step of Array.isArray(output.plan.steps) ? output.plan.steps : []) lines.push(`${step?.status ? `[${step.status}] ` : ""}${step?.step || ""}`.trim());
    rows.push({ id: "plan:current", sortAt: output.plan.updated_at || output.updated_at || "", kind: "plan", title: "Plan", status: "info", text: lines.join("\\n"), meta: [output.plan.updated_at || ""].filter(Boolean) });
  }
  if (output?.reasoning?.text) {
    rows.push({ id: "reasoning:current", sortAt: output.reasoning.updated_at || output.updated_at || "", kind: "reasoning", title: output.reasoning.kind === "raw" ? "Reasoning" : "Reasoning summary", status: "info", text: output.reasoning.text, meta: [output.reasoning.updated_at || ""].filter(Boolean) });
  }
  if (output?.active_text) {
    rows.push({ id: "assistant:active", sortAt: output.updated_at || output.heartbeat_at || "", kind: "assistant", title: "Assistant", status: "running", text: output.active_text, meta: [output.updated_at || ""].filter(Boolean) });
  }
  const hasMatchingError = activity.some((item) => (item.kind || "") === "error" && item.detail === output?.last_error);
  if (output?.last_error && !hasMatchingError) {
    rows.push({ id: "error:last", sortAt: output.updated_at || output.heartbeat_at || "", kind: "error", title: "Error", status: "failed", text: output.last_error, meta: [output.updated_at || ""].filter(Boolean) });
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

function updateButtons() {
  previewBtn.classList.toggle("active", mode === "preview");
  gridBtn.classList.toggle("active", mode === "grid");
  modeLabel.textContent = mode;
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
  composerHint.textContent = output?.can_send ? "Send from live. If the previous bridge died, the next send will rebuild it." : "Input is temporarily disabled in the current session state.";
  const canSend = Boolean(output?.can_send) && !submittingMessage;
  const canInterrupt = Boolean(output?.can_interrupt) && !interruptingTurn;
  messageInput.disabled = !canSend;
  sendBtn.disabled = !canSend;
  interruptBtn.disabled = !canInterrupt;
  renderTerminal(output);
  lastOutputSeq = output?.seq || 0;
}

function applyFrame(framePayload) {
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

function triggerImmediatePoll() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  poll();
}

async function parseErrorResponse(response) {
  try {
    const payload = await response.json();
    if (payload?.detail) return String(payload.detail);
    if (payload?.error?.message) return String(payload.error.message);
  } catch (_error) {}
  return `HTTP ${response.status}`;
}

async function poll() {
  try {
    const response = await fetch(liveStateUrl(), { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    applyFrame(payload.frame);
    applyOutput(payload.output);
  } catch (_error) {
    updatedLabel.textContent = "waiting";
    resolutionLabel.textContent = "-";
    cursorLabel.textContent = "-";
    outputStatusPill.textContent = "No Output";
    outputStatusPill.className = "pill";
    sessionModePill.textContent = "No Session";
    sessionModePill.className = "pill";
    sessionLine.textContent = "Waiting for daemon";
    terminalNote.textContent = "Waiting for daemon";
    outputUpdatedLabel.textContent = "Updated -";
    terminalBody.innerHTML = '<div class="terminal-empty">Waiting for daemon.</div>';
    messageInput.disabled = true;
    sendBtn.disabled = true;
    interruptBtn.disabled = true;
  } finally {
    pollTimer = window.setTimeout(poll, 1000);
  }
}

async function sendMessage(event) {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message || submittingMessage) return;
  submittingMessage = true;
  messageError.textContent = "";
  sendBtn.disabled = true;
  messageInput.disabled = true;
  try {
    const response = await fetch(liveMessageUrl(), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }) });
    if (!response.ok) throw new Error(await parseErrorResponse(response));
    messageInput.value = "";
    triggerImmediatePoll();
  } catch (error) {
    messageError.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    submittingMessage = false;
    triggerImmediatePoll();
  }
}

async function interruptTurn() {
  if (interruptingTurn) return;
  interruptingTurn = true;
  messageError.textContent = "";
  interruptBtn.disabled = true;
  try {
    const response = await fetch(liveInterruptUrl(), { method: "POST" });
    if (!response.ok) throw new Error(await parseErrorResponse(response));
    triggerImmediatePoll();
  } catch (error) {
    messageError.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    interruptingTurn = false;
    triggerImmediatePoll();
  }
}

previewBtn.addEventListener("click", () => { if (mode !== "preview") { mode = "preview"; updateButtons(); triggerImmediatePoll(); } });
gridBtn.addEventListener("click", () => { if (mode !== "grid") { mode = "grid"; updateButtons(); triggerImmediatePoll(); } });
messageForm.addEventListener("submit", sendMessage);
interruptBtn.addEventListener("click", interruptTurn);
updateButtons();
poll();
"""


def render_live_page(*, token: str, initial_mode: ObservationMode) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Agent Computer Live</title>"
        f"<style>{_STYLE}</style>"
        "</head><body>"
        + _BODY.format(token=token, initial_mode=initial_mode)
        + f"<script>{_SCRIPT}</script>"
        + "</body></html>"
    )
