from __future__ import annotations

from typing import Literal

ObservationMode = Literal["preview", "grid"]


def render_live_page(*, token: str, initial_mode: ObservationMode) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Computer Live</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #08111b;
      --bg-soft: #102235;
      --panel: rgba(10, 18, 29, 0.88);
      --panel-strong: rgba(12, 22, 34, 0.96);
      --panel-alt: rgba(20, 34, 50, 0.82);
      --text: #eef5ff;
      --muted: #9eb2c8;
      --border: rgba(150, 188, 222, 0.16);
      --accent: #63d7b0;
      --accent-strong: #88f1d0;
      --warning: #ffb55f;
      --idle: #6cb6ff;
      --shadow: 0 18px 60px rgba(0, 0, 0, 0.28);
      --radius: 18px;
      --radius-sm: 12px;
      --font-ui: "Cascadia Code", "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top left, rgba(59, 130, 246, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(16, 185, 129, 0.16), transparent 24%),
        linear-gradient(180deg, var(--bg-soft), var(--bg));
      color: var(--text);
      font: 15px/1.55 var(--font-ui);
    }}
    .shell {{
      width: min(1100px, calc(100vw - 20px));
      margin: 0 auto;
      padding: 12px 0 18px;
    }}
    .bar {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      padding: 12px;
      margin-bottom: 12px;
      background: rgba(8, 17, 27, 0.84);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(16px);
    }}
    .status-cluster {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .metric {{
      min-height: 40px;
      padding: 8px 12px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.04);
      color: var(--muted);
      font-size: 13px;
    }}
    .metric strong {{
      color: var(--text);
      font-weight: 600;
    }}
    .controls {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    button {{
      min-height: 44px;
      min-width: 88px;
      padding: 10px 14px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
      font: inherit;
      cursor: pointer;
      transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
    }}
    button:hover {{
      transform: translateY(-1px);
      border-color: rgba(136, 241, 208, 0.4);
    }}
    button.active {{
      border-color: rgba(136, 241, 208, 0.48);
      background: rgba(99, 215, 176, 0.14);
      color: var(--accent-strong);
    }}
    .layout {{
      display: grid;
      gap: 12px;
    }}
    .card {{
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .card-header {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.03);
    }}
    .card-title {{
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--accent-strong);
    }}
    .card-meta {{
      color: var(--muted);
      font-size: 13px;
    }}
    .screen-body {{
      padding: 12px;
      min-height: min(62vh, 720px);
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0));
    }}
    .screen-frame {{
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: min(56vh, 660px);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: var(--radius-sm);
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0)),
        rgba(6, 10, 16, 0.9);
      overflow: hidden;
    }}
    img {{
      display: block;
      width: 100%;
      height: auto;
      max-height: min(58vh, 700px);
      object-fit: contain;
      background: #05080d;
    }}
    .output-body {{
      display: grid;
      gap: 12px;
      padding: 14px;
      min-height: 230px;
      background:
        linear-gradient(180deg, rgba(99, 215, 176, 0.04), transparent 18%),
        rgba(8, 14, 22, 0.82);
    }}
    .output-topline {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 6px 12px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.05);
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }}
    .badge.running {{
      color: var(--accent-strong);
      border-color: rgba(136, 241, 208, 0.36);
      background: rgba(99, 215, 176, 0.14);
    }}
    .badge.idle {{
      color: var(--idle);
      border-color: rgba(108, 182, 255, 0.3);
      background: rgba(108, 182, 255, 0.14);
    }}
    .badge.no-output {{
      color: var(--muted);
    }}
    .badge.stalled {{
      color: var(--warning);
      border-color: rgba(255, 181, 95, 0.3);
      background: rgba(255, 181, 95, 0.12);
    }}
    .latest-block {{
      padding: 14px;
      border: 1px solid rgba(99, 215, 176, 0.18);
      border-radius: var(--radius-sm);
      background: var(--panel-alt);
    }}
    .latest-label {{
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .latest-text {{
      white-space: normal;
      word-break: break-word;
      color: var(--text);
      font-size: 15px;
      line-height: 1.6;
    }}
    .recent-wrap {{
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: rgba(255, 255, 255, 0.03);
      overflow: hidden;
    }}
    .recent-header {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .recent-list {{
      max-height: 280px;
      overflow: auto;
    }}
    .recent-item {{
      display: grid;
      gap: 6px;
      padding: 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }}
    .recent-item:last-child {{
      border-bottom: 0;
    }}
    .recent-meta {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      color: var(--muted);
      font-size: 12px;
    }}
    .recent-kind {{
      color: var(--accent-strong);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .recent-text {{
      white-space: normal;
      word-break: break-word;
      color: var(--text);
      font-size: 14px;
      line-height: 1.55;
    }}
    .rich-text {{
      color: inherit;
    }}
    .rich-text code.inline-code {{
      display: inline-block;
      padding: 1px 6px;
      margin: 0 1px;
      border: 1px solid rgba(136, 241, 208, 0.14);
      border-radius: 8px;
      background: rgba(99, 215, 176, 0.09);
      color: var(--accent-strong);
      font: 0.96em/1.45 var(--font-ui);
      vertical-align: baseline;
    }}
    .rich-text pre.code-block {{
      margin: 10px 0 0;
      padding: 12px;
      overflow: auto;
      border: 1px solid rgba(136, 241, 208, 0.1);
      border-radius: 12px;
      background: rgba(4, 9, 14, 0.82);
      color: #dff7f0;
      font: 13px/1.55 var(--font-ui);
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .rich-text pre.code-block code {{
      color: inherit;
      font: inherit;
    }}
    .empty {{
      padding: 14px;
      color: var(--muted);
      font-size: 14px;
    }}
    @media (max-width: 720px) {{
      body {{
        font-size: 16px;
      }}
      .shell {{
        width: min(100vw - 12px, 100%);
        padding-top: 8px;
      }}
      .bar {{
        padding: 10px;
      }}
      .status-cluster {{
        gap: 8px;
      }}
      .metric {{
        min-height: 38px;
        padding: 8px 10px;
      }}
      .screen-body {{
        min-height: 240px;
        padding: 10px;
      }}
      .screen-frame {{
        min-height: 220px;
      }}
      .output-body {{
        min-height: 200px;
        padding: 12px;
      }}
      .recent-list {{
        max-height: 240px;
      }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      * {{
        transition: none !important;
        scroll-behavior: auto !important;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="bar">
      <div class="status-cluster">
        <div class="metric">Mode <strong id="mode-label">{initial_mode}</strong></div>
        <div class="metric">Screen <strong id="updated-label">warming up</strong></div>
        <div class="metric">Resolution <strong id="resolution-label">-</strong></div>
        <div class="metric">Cursor <strong id="cursor-label">-</strong></div>
      </div>
      <div class="controls">
        <button id="preview-btn" type="button">Preview</button>
        <button id="grid-btn" type="button">Grid</button>
      </div>
    </div>

    <div class="layout">
      <section class="card">
        <div class="card-header">
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
        <div class="card-header">
          <div class="card-title">Codex Output</div>
          <div class="card-meta" id="output-updated-label">Updated -</div>
        </div>
        <div class="output-body">
          <div class="output-topline">
            <div id="output-status-badge" class="badge no-output">No Output</div>
            <div class="card-meta" id="output-meta">Waiting for Codex session</div>
          </div>

          <div class="latest-block">
            <span class="latest-label">Latest Output</span>
            <div id="latest-output-text" class="latest-text">No Codex output yet.</div>
          </div>

          <div class="recent-wrap">
            <div class="recent-header">Recent Window</div>
            <div id="recent-list" class="recent-list">
              <div class="empty">No recent output yet.</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>

  <script>
    const token = {token!r};
    let mode = {initial_mode!r};
    let lastFrameSeq = -1;
    let lastOutputSeq = -1;
    let pollTimer = null;

    const frame = document.getElementById("frame");
    const modeLabel = document.getElementById("mode-label");
    const updatedLabel = document.getElementById("updated-label");
    const resolutionLabel = document.getElementById("resolution-label");
    const cursorLabel = document.getElementById("cursor-label");
    const previewBtn = document.getElementById("preview-btn");
    const gridBtn = document.getElementById("grid-btn");
    const screenMeta = document.getElementById("screen-meta");
    const outputStatusBadge = document.getElementById("output-status-badge");
    const outputUpdatedLabel = document.getElementById("output-updated-label");
    const outputMeta = document.getElementById("output-meta");
    const latestOutputText = document.getElementById("latest-output-text");
    const recentList = document.getElementById("recent-list");

    function updateButtons() {{
      previewBtn.classList.toggle("active", mode === "preview");
      gridBtn.classList.toggle("active", mode === "grid");
      modeLabel.textContent = mode;
    }}

    function liveStateUrl() {{
      return `/live/state.json?token=${{encodeURIComponent(token)}}&mode=${{encodeURIComponent(mode)}}`;
    }}

    function parseTime(value) {{
      if (!value) {{
        return null;
      }}
      const ms = Date.parse(value);
      return Number.isNaN(ms) ? null : ms;
    }}

    function describeOutputState(output) {{
      if (!output || output.status === "no_output") {{
        return {{
          text: "No Output",
          className: "badge no-output",
          detail: "Waiting for Codex session",
        }};
      }}
      if (output.status === "idle") {{
        return {{
          text: "Idle",
          className: "badge idle",
          detail: "Codex is not actively producing output",
        }};
      }}
      const staleAfterSec = Number(output.stale_after_seconds || 15);
      const heartbeatMs = parseTime(output.heartbeat_at || output.updated_at);
      if (heartbeatMs !== null && Date.now() - heartbeatMs > staleAfterSec * 1000) {{
        return {{
          text: "Possible Stall",
          className: "badge stalled",
          detail: "Running, but no recent heartbeat",
        }};
      }}
      return {{
        text: "Running",
        className: "badge running",
        detail: "Codex is actively moving",
      }};
    }}

    function renderRecent(output) {{
      const recent = Array.isArray(output?.recent) ? output.recent : [];
      if (recent.length === 0) {{
        recentList.innerHTML = '<div class="empty">No recent output yet.</div>';
        return;
      }}

      recentList.innerHTML = "";
      const fragment = document.createDocumentFragment();
      for (const item of recent) {{
        const row = document.createElement("div");
        row.className = "recent-item";

        const meta = document.createElement("div");
        meta.className = "recent-meta";

        const kind = document.createElement("span");
        kind.className = "recent-kind";
        kind.textContent = item.kind || "commentary";
        meta.appendChild(kind);

        const at = document.createElement("span");
        at.textContent = item.created_at || "-";
        meta.appendChild(at);

        const text = document.createElement("div");
        text.className = "recent-text";
        text.innerHTML = renderRichText(item.text || "");

        row.appendChild(meta);
        row.appendChild(text);
        fragment.appendChild(row);
      }}
      recentList.appendChild(fragment);
    }}

    function escapeHtml(value) {{
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }}

    function renderRichText(value) {{
      const source = String(value || "");
      if (!source) {{
        return "";
      }}

      const blocks = [];
      let html = escapeHtml(source).replace(/```([\\s\\S]*?)```/g, (_, code) => {{
        const index = blocks.length;
        const trimmed = String(code || "").replace(/^\\n+/, "").replace(/\\n+$/, "");
        blocks.push(`<pre class="code-block"><code>${{trimmed}}</code></pre>`);
        return `@@CODEBLOCK${{index}}@@`;
      }});

      html = html.replace(/`([^`\\n]+)`/g, '<code class="inline-code">$1</code>');
      html = html.replace(/\\n/g, "<br>");
      html = html.replace(/@@CODEBLOCK(\\d+)@@/g, (_, index) => blocks[Number(index)] || "");
      return `<div class="rich-text">${{html}}</div>`;
    }}

    function applyOutput(output) {{
      const state = describeOutputState(output);
      outputStatusBadge.textContent = state.text;
      outputStatusBadge.className = state.className;
      outputMeta.textContent = state.detail;
      outputUpdatedLabel.textContent = `Updated ${{output?.updated_at || "-"}}`;
      latestOutputText.innerHTML = renderRichText(output?.latest_text || "No Codex output yet.");
      if ((output?.seq || 0) !== lastOutputSeq) {{
        renderRecent(output);
        recentList.scrollTop = recentList.scrollHeight;
        lastOutputSeq = output?.seq || 0;
      }}
    }}

    function applyFrame(framePayload) {{
      updatedLabel.textContent = framePayload.updated_at || "-";
      resolutionLabel.textContent = `${{framePayload.desktop_width || framePayload.width}}x${{framePayload.desktop_height || framePayload.height}}`;
      const cursor = framePayload.mouse_position;
      cursorLabel.textContent = cursor ? `(${{cursor.x}}, ${{cursor.y}})` : "-";
      screenMeta.textContent = `Watching latest ${{mode}} frame`;
      if (framePayload.frame_seq !== lastFrameSeq) {{
        frame.src = `${{framePayload.image_url}}&ts=${{Date.now()}}`;
        lastFrameSeq = framePayload.frame_seq;
      }}
    }}

    async function poll() {{
      try {{
        const response = await fetch(liveStateUrl(), {{ cache: "no-store" }});
        if (!response.ok) {{
          throw new Error(`HTTP ${{response.status}}`);
        }}
        const payload = await response.json();
        applyFrame(payload.frame);
        applyOutput(payload.output);
      }} catch (error) {{
        updatedLabel.textContent = "waiting";
        resolutionLabel.textContent = "-";
        cursorLabel.textContent = "-";
        outputStatusBadge.textContent = "No Output";
        outputStatusBadge.className = "badge no-output";
        outputMeta.textContent = "Waiting for daemon";
        outputUpdatedLabel.textContent = "Updated -";
      }} finally {{
        pollTimer = window.setTimeout(poll, 1000);
      }}
    }}

    function restartPolling(nextMode) {{
      mode = nextMode;
      lastFrameSeq = -1;
      updateButtons();
      if (pollTimer !== null) {{
        window.clearTimeout(pollTimer);
      }}
      poll();
    }}

    previewBtn.addEventListener("click", () => restartPolling("preview"));
    gridBtn.addEventListener("click", () => restartPolling("grid"));

    updateButtons();
    poll();
  </script>
</body>
</html>"""
