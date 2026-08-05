# -*- coding: utf-8 -*-
import markupsafe
from odoo import http
from odoo.http import request


def _render_teleprompter(title, production, body_html):
    """Return a fully self-contained teleprompter HTML page as a string."""
    title      = markupsafe.escape(title)
    production = markupsafe.escape(production)
    # body_html comes from Odoo's Html field — already sanitised on save.

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title} — Teleprompter</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg: #000;
    --fg: #fff;
    --font-size: 52px;
    --line-height: 1.65;
  }}

  html, body {{
    background: var(--bg);
    color: var(--fg);
    height: 100%;
    overflow: hidden;
    font-family: 'Georgia', 'Times New Roman', serif;
    cursor: none;
  }}

  /* ── Mirror wrapper ─────────────────────────────── */
  #mirror-wrap {{
    width: 100%;
    height: 100%;
    transition: transform 0.2s ease;
  }}
  #mirror-wrap.mirrored {{ transform: scaleX(-1); }}

  /* ── Scroll viewport ────────────────────────────── */
  #viewport {{ position: fixed; inset: 0; overflow: hidden; }}

  /* ── Script content ─────────────────────────────── */
  #content {{
    padding: 6vh 10vw 60vh;
    font-size: var(--font-size);
    line-height: var(--line-height);
    will-change: transform;
  }}
  #content h1.script-title {{
    font-size: calc(var(--font-size) * 0.6);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    opacity: 0.35;
    margin-bottom: 0.25em;
  }}
  #content h1.production-name {{
    font-size: calc(var(--font-size) * 0.45);
    letter-spacing: 0.06em;
    opacity: 0.25;
    margin-bottom: 2em;
  }}

  /* Strip colours from pasted HTML — force white-on-black */
  #script-body * {{ background: transparent !important; color: inherit !important; }}
  #script-body p, #script-body div {{ margin-bottom: 0.6em; }}
  #script-body strong, #script-body b {{ opacity: 0.9; }}
  #script-body em, #script-body i {{ opacity: 0.75; font-style: italic; }}
  #script-body h1, #script-body h2, #script-body h3 {{
    font-size: 1em; font-weight: bold;
    text-transform: uppercase; letter-spacing: 0.1em;
    opacity: 0.45; margin: 1em 0 0.3em;
  }}

  /* ── Reading-line cue bar ───────────────────────── */
  #cue-line {{
    position: fixed; left: 0; right: 0; top: 38%;
    height: 4px;
    background: rgba(255,200,0,0.55);
    pointer-events: none; z-index: 10;
    box-shadow: 0 0 18px 4px rgba(255,200,0,0.25);
  }}

  /* ── HUD overlay ────────────────────────────────── */
  #hud {{
    position: fixed; bottom: 0; left: 0; right: 0;
    background: rgba(0,0,0,0.72);
    backdrop-filter: blur(6px);
    padding: 10px 24px;
    display: flex; align-items: center; gap: 14px;
    z-index: 20; opacity: 0;
    transition: opacity 0.35s ease;
    font-family: 'SF Mono', 'Consolas', monospace;
    font-size: 14px; cursor: default;
  }}
  body:hover #hud, #hud:focus-within {{ opacity: 1; }}
  body:hover {{ cursor: default; }}

  .hud-btn {{
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.22);
    color: #fff; border-radius: 6px;
    padding: 5px 14px; font-size: 13px;
    cursor: pointer; user-select: none;
    white-space: nowrap; transition: background 0.15s;
  }}
  .hud-btn:hover {{ background: rgba(255,255,255,0.25); }}
  .hud-btn.active {{ background: rgba(255,200,0,0.35); border-color: rgba(255,200,0,0.6); }}

  .hud-sep {{ width: 1px; height: 22px; background: rgba(255,255,255,0.18); flex-shrink: 0; }}
  .hud-label {{ opacity: 0.45; font-size: 12px; white-space: nowrap; }}
  #speed-val, #font-val {{ min-width: 2.5ch; text-align: center; opacity: 0.85; }}

  #progress-bar {{
    flex: 1; height: 3px;
    background: rgba(255,255,255,0.15);
    border-radius: 2px; overflow: hidden; cursor: pointer;
  }}
  #progress-fill {{
    height: 100%; background: rgba(255,200,0,0.7);
    width: 0%; transition: width 0.1s linear; border-radius: 2px;
  }}

  /* ── Pause overlay ──────────────────────────────── */
  #pause-overlay {{
    position: fixed; inset: 0;
    display: flex; align-items: center; justify-content: center;
    pointer-events: none; z-index: 15;
    opacity: 0; transition: opacity 0.3s ease;
  }}
  #pause-overlay.visible {{ opacity: 1; }}
  #pause-icon {{
    width: 80px; height: 80px;
    background: rgba(0,0,0,0.6); border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 32px;
  }}
</style>
</head>
<body>

<div id="viewport">
  <div id="mirror-wrap" class="mirrored">
    <div id="content">
      <h1 class="script-title">{title}</h1>
      <h1 class="production-name">{production}</h1>
      <div id="script-body">{body_html}</div>
    </div>
  </div>
</div>

<div id="cue-line"></div>
<div id="pause-overlay"><div id="pause-icon">⏸</div></div>

<div id="hud">
  <button class="hud-btn" id="btn-play" title="Space">▶ Play</button>
  <div class="hud-sep"></div>
  <span class="hud-label">Speed</span>
  <button class="hud-btn" id="btn-speed-down" title="↓">−</button>
  <span id="speed-val">60</span>
  <button class="hud-btn" id="btn-speed-up" title="↑">+</button>
  <div class="hud-sep"></div>
  <span class="hud-label">Size</span>
  <button class="hud-btn" id="btn-font-down" title="[">A−</button>
  <span id="font-val">52</span>
  <button class="hud-btn" id="btn-font-up" title="]">A+</button>
  <div class="hud-sep"></div>
  <button class="hud-btn active" id="btn-mirror" title="M">⇔ Mirror</button>
  <div class="hud-sep"></div>
  <div id="progress-bar" title="Click to seek"><div id="progress-fill"></div></div>
  <button class="hud-btn" id="btn-reset" title="R">↑ Top</button>
  <button class="hud-btn" id="btn-fs" title="F">⛶ Full</button>
</div>

<script>
(function () {{
  'use strict';

  const SPEED_STEP = 5, SPEED_MIN = 5, SPEED_MAX = 300;
  const FONT_STEP  = 4, FONT_MIN  = 20, FONT_MAX  = 120;

  let playing = false, speed = 60, fontSize = 52, mirrored = true;
  let scrollY = 0, lastTs = null, rafId = null;

  const content    = document.getElementById('content');
  const mirrorWrap = document.getElementById('mirror-wrap');
  const progFill   = document.getElementById('progress-fill');
  const progBar    = document.getElementById('progress-bar');
  const pauseOv    = document.getElementById('pause-overlay');
  const pauseIcon  = document.getElementById('pause-icon');
  const speedVal   = document.getElementById('speed-val');
  const fontVal    = document.getElementById('font-val');
  const btnPlay    = document.getElementById('btn-play');
  const btnMirror  = document.getElementById('btn-mirror');

  function maxScroll() {{ return Math.max(0, content.offsetHeight - window.innerHeight); }}

  function applyScroll() {{
    content.style.transform = `translateY(${{-scrollY}}px)`;
    const pct = maxScroll() > 0 ? (scrollY / maxScroll()) * 100 : 0;
    progFill.style.width = pct.toFixed(1) + '%';
  }}

  function setSpeed(v) {{
    speed = Math.max(SPEED_MIN, Math.min(SPEED_MAX, v));
    speedVal.textContent = speed;
  }}

  function setFontSize(v) {{
    fontSize = Math.max(FONT_MIN, Math.min(FONT_MAX, v));
    document.documentElement.style.setProperty('--font-size', fontSize + 'px');
    fontVal.textContent = fontSize;
  }}

  function setMirror(v) {{
    mirrored = v;
    mirrorWrap.classList.toggle('mirrored', mirrored);
    btnMirror.classList.toggle('active', mirrored);
  }}

  function setPlaying(v) {{
    playing = v;
    btnPlay.textContent = playing ? '⏸ Pause' : '▶ Play';
    pauseIcon.textContent = playing ? '⏸' : '▶';
    pauseOv.classList.toggle('visible', !playing);
    if (playing) {{
      lastTs = null;
      rafId = requestAnimationFrame(tick);
    }} else {{
      if (rafId) cancelAnimationFrame(rafId);
      rafId = null;
    }}
  }}

  function tick(ts) {{
    if (!playing) return;
    if (lastTs !== null) {{
      const dt = (ts - lastTs) / 1000;
      scrollY = Math.min(scrollY + speed * dt, maxScroll());
      applyScroll();
      if (scrollY >= maxScroll()) {{ setPlaying(false); return; }}
    }}
    lastTs = ts;
    rafId = requestAnimationFrame(tick);
  }}

  btnPlay.addEventListener('click', () => setPlaying(!playing));
  document.getElementById('btn-speed-down').addEventListener('click', () => setSpeed(speed - SPEED_STEP));
  document.getElementById('btn-speed-up').addEventListener('click',   () => setSpeed(speed + SPEED_STEP));
  document.getElementById('btn-font-down').addEventListener('click',  () => setFontSize(fontSize - FONT_STEP));
  document.getElementById('btn-font-up').addEventListener('click',    () => setFontSize(fontSize + FONT_STEP));
  btnMirror.addEventListener('click', () => setMirror(!mirrored));

  document.getElementById('btn-reset').addEventListener('click', () => {{
    setPlaying(false); scrollY = 0; applyScroll();
  }});

  document.getElementById('btn-fs').addEventListener('click', () => {{
    if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {{}});
    else document.exitFullscreen().catch(() => {{}});
  }});

  progBar.addEventListener('click', (e) => {{
    const rect = progBar.getBoundingClientRect();
    scrollY = ((e.clientX - rect.left) / rect.width) * maxScroll();
    applyScroll();
  }});

  document.addEventListener('keydown', (e) => {{
    switch (e.key) {{
      case ' ': case 'k': e.preventDefault(); setPlaying(!playing); break;
      case 'ArrowUp':   case 'ArrowLeft':  e.preventDefault(); setSpeed(speed - SPEED_STEP); break;
      case 'ArrowDown': case 'ArrowRight': e.preventDefault(); setSpeed(speed + SPEED_STEP); break;
      case '[': setFontSize(fontSize - FONT_STEP); break;
      case ']': setFontSize(fontSize + FONT_STEP); break;
      case 'm': case 'M': setMirror(!mirrored); break;
      case 'r': case 'R': setPlaying(false); scrollY = 0; applyScroll(); break;
      case 'f': case 'F':
        if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {{}});
        else document.exitFullscreen().catch(() => {{}});
        break;
    }}
  }});

  window.addEventListener('wheel', (e) => {{
    if (!playing) {{
      scrollY = Math.max(0, Math.min(scrollY + e.deltaY * 0.8, maxScroll()));
      applyScroll();
    }}
  }}, {{ passive: true }});

  let touchY = null;
  window.addEventListener('touchstart', (e) => {{ touchY = e.touches[0].clientY; }}, {{ passive: true }});
  window.addEventListener('touchmove',  (e) => {{
    if (!playing && touchY !== null) {{
      scrollY = Math.max(0, Math.min(scrollY + (touchY - e.touches[0].clientY), maxScroll()));
      applyScroll();
      touchY = e.touches[0].clientY;
    }}
  }}, {{ passive: true }});

  // Init
  setSpeed(60); setFontSize(52); setMirror(true); applyScroll();
  pauseOv.classList.add('visible');
}})();
</script>
</body>
</html>"""


class TeleprompterController(http.Controller):

    # ── Authenticated route (browser tab, user already logged in) ────────────
    @http.route(
        '/video/script/<int:script_id>/teleprompter',
        type='http',
        auth='user',
        website=False,
    )
    def teleprompter(self, script_id, **kwargs):
        script = request.env['video.script'].browse(script_id)
        if not script.exists():
            return request.not_found()
        return request.make_response(
            _render_teleprompter(
                script.name,
                script.production_id.name or '',
                script.full_script or '<p><em>No script content.</em></p>',
            ),
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )

    # ── Public token route (IoT display — no Odoo session required) ──────────
    @http.route(
        '/video/teleprompter/<string:token>',
        type='http',
        auth='public',
        website=False,
    )
    def teleprompter_public(self, token, **kwargs):
        if not token or len(token) < 32:
            return request.not_found()
        script = request.env['video.script'].sudo().search(
            [('teleprompter_token', '=', token), ('state', '=', 'approved')],
            limit=1,
        )
        if not script:
            return request.not_found()
        return request.make_response(
            _render_teleprompter(
                script.name,
                script.production_id.name or '',
                script.full_script or '<p><em>No script content.</em></p>',
            ),
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )
