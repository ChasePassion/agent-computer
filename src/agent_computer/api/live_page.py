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
.chips, .actions, .button-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.chip {
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
.card-meta, .help, .status, .label { color: var(--muted); font-size: 12px; }
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
.control-body { display: grid; gap: 10px; padding: 12px; background: var(--panel-2); }
.panel {
  display: grid; gap: 8px; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: #0f1721;
}
.panel h3 { margin: 0; font-size: 12px; color: var(--text); text-transform: uppercase; letter-spacing: .06em; }
.status { min-height: 18px; }
.status.error { color: var(--red); }
.status.ok { color: var(--green); }
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
@media (max-width: 720px) {
  .shell { width: min(100vw - 10px, 100%); padding-top: 6px; }
  .screen-body { min-height: 230px; padding: 10px; }
  .screen-frame { min-height: 210px; }
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
    if (!selectedPoint) setStatus("Tap the screen image to pick a point.");
  } catch (_error) {
    updatedLabel.textContent = "waiting";
    resolutionLabel.textContent = "-";
    cursorLabel.textContent = "-";
    screenMeta.textContent = "Waiting for daemon";
    setStatus("Waiting for daemon", "error");
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
