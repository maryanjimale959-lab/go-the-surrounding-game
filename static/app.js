"use strict";

const $ = (s) => document.querySelector(s);
const LETTERS = "ABCDEFGHJKLMNOPQRST";
const BLACK = 1, WHITE = -1;

var state = null;   // var (not let) so it is reachable as window.state for debugging
let busy = false;
let hover = null;                 // {x, y}
const pop = new Map();            // "x,y" -> animation start time
let animFrame = null;
let audio = null;

/* ------------------------------------------------------------------ api */
async function api(path, body = {}) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function refresh() {
  const res = await fetch("/api/state");
  apply(await res.json());
}

function apply(data) {
  if (!data.ok) {
    toast(data.error || "error");
    if (data.state) state = data.state;
    paint(); updatePanel();
    return;
  }
  const prev = state ? state.board : null;
  state = data.state;
  mode2P = state.mode === "2 Players";
  if (prev && prev.length === state.size) {
    for (let x = 0; x < state.size; x++)
      for (let y = 0; y < state.size; y++)
        if (state.board[x][y] !== 0 && prev[x][y] === 0) pop.set(x + "," + y, 0);
  }
  if (!state.over) showScoreDialog.shown = false;
  paint(); updatePanel();
  runAnim();
}

/* ------------------------------------------------------------------ sound */
function clickStone() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const t = audio.currentTime;
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(320, t);
    osc.frequency.exponentialRampToValueAtTime(90, t + 0.06);
    gain.gain.setValueAtTime(0.5, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.09);
    osc.connect(gain).connect(audio.destination);
    osc.start(t); osc.stop(t + 0.1);
  } catch (e) { /* audio is optional */ }
}

/* ------------------------------------------------------------------ board */
const canvas = $("#board");
const ctx = canvas.getContext("2d");
let L = null;                    // geometry of the last main-board paint

/* The scene: board on a table, stone bowls and lids in the free space. */
function scene() {
  const wrap = canvas.parentElement;
  const availW = Math.max(260, Math.min(wrap.clientWidth - 34, 1000));
  if (availW >= 640) {                       // desk: bowls flank the board
    const px = Math.min(availW * 0.58, 640);
    const W = availW, H = px * 1.12;
    const bx = (W - px) / 2, by = (H - px) / 2;
    const r = Math.min(bx * 0.40, px * 0.155);
    const cxL = bx * 0.5, cxR = W - bx * 0.5;
    return { W, H, px, bx, by, wide: true, bowls: [
      { color: BLACK, cx: cxL, cy: by + px * 0.30, r: r },
      { color: BLACK, cx: cxL, cy: by + px * 0.80, r: r * 0.86, lid: true },
      { color: WHITE, cx: cxR, cy: by + px * 0.30, r: r },
      { color: WHITE, cx: cxR, cy: by + px * 0.80, r: r * 0.86, lid: true },
    ] };
  }
  const px = availW - 6;                       // phone: bowls above the board
  const r = Math.max(15, px * 0.07);
  const band = r * 2.6 + 10;
  const W = availW;
  return { W, H: px + band + 6, px, bx: (W - px) / 2, by: band, wide: false, bowls: [
    { color: BLACK, cx: W / 2 - px * 0.23, cy: band * 0.52, r: r },
    { color: WHITE, cx: W / 2 + px * 0.23, cy: band * 0.52, r: r },
  ] };
}

function plainScene(px) {
  return { W: px, H: px, px, bx: 0, by: 0, wide: false, bowls: [] };
}

function renderBoard(g, size, board, S, opts = {}) {
  const dpr = window.devicePixelRatio || 1;
  const cell = S.px / (size + 1.1), pad = cell * 1.05;
  const bx = S.bx, by = S.by, px = S.px;
  const atX = (i) => bx + pad + i * cell;
  const atY = (i) => by + pad + i * cell;
  const span = cell * (size - 1);

  /* ---- the wooden board */
  const corner = px * 0.022;
  if (S.wide) {                       // thickness of the board against the table
    roundRect(g, bx + px * 0.004, by + px * 0.02, px, px, corner);
    g.fillStyle = "#a3702c"; g.fill();
  }
  g.save();
  g.shadowColor = "rgba(46, 24, 6, 0.5)";
  g.shadowBlur = px * 0.045; g.shadowOffsetY = px * 0.014;
  roundRect(g, bx, by, px, px, corner);
  g.fillStyle = "#d8a44e"; g.fill();
  g.restore();

  const face = g.createLinearGradient(bx, by, bx + px, by + px);
  face.addColorStop(0, "#f7d79f");
  face.addColorStop(0.45, "#eabf74");
  face.addColorStop(1, "#dda955");
  roundRect(g, bx, by, px, px, corner);
  g.fillStyle = face; g.fill();

  g.save();
  roundRect(g, bx, by, px, px, corner); g.clip();
  g.strokeStyle = "rgba(150, 96, 26, 0.08)";
  for (let i = 0; i < 16; i++) {
    g.lineWidth = (1 + (i % 4) * 0.8) * dpr;
    const yy = by + (i / 16) * px;
    g.beginPath(); g.moveTo(bx, yy);
    g.bezierCurveTo(bx + px * 0.3, yy + 4 * dpr, bx + px * 0.7, yy - 4 * dpr, bx + px, yy);
    g.stroke();
  }
  // bevel: light along the top edge, shade along the bottom
  const bev = g.createLinearGradient(0, by, 0, by + px);
  bev.addColorStop(0, "rgba(255, 240, 208, 0.5)");
  bev.addColorStop(0.1, "rgba(255, 240, 208, 0)");
  bev.addColorStop(0.9, "rgba(120, 72, 16, 0)");
  bev.addColorStop(1, "rgba(120, 72, 16, 0.18)");
  roundRect(g, bx, by, px, px, corner); g.fillStyle = bev; g.fill();
  g.restore();

  g.strokeStyle = "rgba(126, 82, 22, 0.45)"; g.lineWidth = Math.max(1, dpr);
  roundRect(g, bx + 0.5, by + 0.5, px - 1, px - 1, corner); g.stroke();

  /* ---- grid */
  g.strokeStyle = "rgba(78, 50, 10, 0.72)";
  g.lineWidth = Math.max(1, dpr * 0.9);
  for (let i = 0; i < size; i++) {
    line(g, atX(i), atY(0), atX(i), atY(size - 1));
    line(g, atX(0), atY(i), atX(size - 1), atY(i));
  }
  g.lineWidth = Math.max(1.5, 1.6 * dpr);
  g.strokeRect(atX(0), atY(0), span, span);

  g.fillStyle = "rgba(64, 40, 8, 0.92)";
  for (const [sx, sy] of stars(size)) {
    g.beginPath(); g.arc(atX(sx), atY(sy), Math.max(2, cell * 0.06), 0, 7); g.fill();
  }

  /* ---- territory */
  if (opts.territory) {
    for (const key in opts.territory) {
      const o = opts.territory[key];
      if (o !== "B" && o !== "W") continue;
      const [x, y] = key.split(",").map(Number);
      g.fillStyle = o === "B" ? "rgba(46, 92, 60, 0.55)" : "rgba(70, 110, 160, 0.55)";
      diamond(g, atX(x), atY(y), cell * 0.16); g.fill();
    }
  }

  /* ---- coordinates */
  if (opts.labels) {
    g.fillStyle = "rgba(84, 56, 14, 0.8)";
    g.font = `${Math.round(cell * 0.34)}px Georgia`;
    g.textAlign = "center"; g.textBaseline = "middle";
    for (let i = 0; i < size; i++) {
      g.fillText(LETTERS[i], atX(i), by + pad * 0.42);
      g.fillText(String(size - i), bx + pad * 0.4, atY(i));
    }
  }

  /* ---- stones */
  const now = performance.now();
  for (let x = 0; x < size; x++)
    for (let y = 0; y < size; y++)
      if (board[x][y]) {
        let scale = 1;
        const key = x + "," + y;
        if (opts.anim && pop.has(key)) {
          const t = Math.min(1, (now - pop.get(key)) / 140);
          scale = 0.55 + 0.45 * easeOutBack(t);
        }
        stone(g, atX(x), atY(y), cell * 0.47 * scale, board[x][y]);
      }

  if (opts.hover && board[opts.hover.x][opts.hover.y] === 0) {
    g.save(); g.globalAlpha = 0.45;
    stone(g, atX(opts.hover.x), atY(opts.hover.y), cell * 0.47, opts.hoverColor);
    g.restore();
  }

  if (opts.last && board[opts.last[0]][opts.last[1]]) {
    g.strokeStyle = board[opts.last[0]][opts.last[1]] === WHITE ? "#d84c4c" : "#f7f2e4";
    g.lineWidth = Math.max(1.6, 1.8 * dpr);
    g.beginPath(); g.arc(atX(opts.last[0]), atY(opts.last[1]), cell * 0.17, 0, 7); g.stroke();
  }

  /* ---- bowls and lids */
  for (const b of opts.bowls || []) bowl(g, b);

  return { cell, pad, bx, by };
}

/* Glossy lens-shaped stone with a contact shadow. */
function stone(g, cx, cy, r, color) {
  g.save();
  g.shadowColor = "rgba(52, 30, 8, 0.5)";
  g.shadowBlur = r * 0.42; g.shadowOffsetY = r * 0.2;
  const grad = g.createRadialGradient(cx - r * 0.34, cy - r * 0.42, r * 0.12, cx, cy, r * 1.08);
  if (color === BLACK) {
    grad.addColorStop(0, "#79838f");
    grad.addColorStop(0.3, "#2d333c");
    grad.addColorStop(0.72, "#0d1015");
    grad.addColorStop(1, "#04060a");
  } else {
    grad.addColorStop(0, "#ffffff");
    grad.addColorStop(0.5, "#f6f2e7");
    grad.addColorStop(0.85, "#ddd5c2");
    grad.addColorStop(1, "#b0a891");
  }
  g.fillStyle = grad;
  g.beginPath(); g.ellipse(cx, cy, r, r * 0.94, 0, 0, 7); g.fill();
  g.restore();

  g.strokeStyle = color === BLACK ? "rgba(0,0,0,0.85)" : "rgba(150,142,120,0.75)";
  g.lineWidth = 1;
  g.beginPath(); g.ellipse(cx, cy, r, r * 0.94, 0, 0, 7); g.stroke();

  // specular gloss
  g.save();
  const hi = g.createRadialGradient(cx - r * 0.33, cy - r * 0.42, 0, cx - r * 0.33, cy - r * 0.42, r * 0.62);
  hi.addColorStop(0, color === BLACK ? "rgba(255,255,255,0.42)" : "rgba(255,255,255,0.95)");
  hi.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = hi;
  g.beginPath(); g.ellipse(cx - r * 0.3, cy - r * 0.4, r * 0.42, r * 0.3, -0.5, 0, 7); g.fill();
  g.restore();
}

/* Ceramic go-bowl (bowl = prisoners, lid = a single resting stone). */
function bowl(g, b) {
  const { cx, cy, r, color, lid } = b;
  const rad = r * 0.44;
  g.save();
  g.translate(cx, cy);

  g.save();
  g.rotate((color === BLACK ? -1 : 1) * 0.05);
  g.shadowColor = "rgba(38, 18, 4, 0.55)";
  g.shadowBlur = r * 0.5; g.shadowOffsetY = r * 0.22;
  const body = g.createLinearGradient(-r, -r, r, r);
  if (lid) {
    body.addColorStop(0, "#96633a"); body.addColorStop(0.5, "#74452a"); body.addColorStop(1, "#4d2b16");
  } else {
    body.addColorStop(0, "#82502d"); body.addColorStop(0.5, "#5e351c"); body.addColorStop(1, "#3a1e0c");
  }
  roundRect(g, -r, -r, 2 * r, 2 * r, rad); g.fillStyle = body; g.fill();
  g.shadowColor = "transparent";

  g.lineWidth = Math.max(1, r * 0.05);
  g.strokeStyle = "rgba(255, 216, 168, 0.22)";
  roundRect(g, -r * 0.97, -r * 0.97, r * 1.94, r * 1.94, rad); g.stroke();

  if (lid) {
    g.strokeStyle = "rgba(34, 15, 4, 0.4)"; g.lineWidth = Math.max(1, r * 0.07);
    roundRect(g, -r * 0.6, -r * 0.6, r * 1.2, r * 1.2, rad * 0.75); g.stroke();
    stone(g, 0, -r * 0.06, r * 0.3, color);
  } else {
    const well = g.createRadialGradient(0, -r * 0.25, r * 0.08, 0, 0, r * 1.15);
    well.addColorStop(0, "#5c3517"); well.addColorStop(1, "#1d0e04");
    roundRect(g, -r * 0.80, -r * 0.80, r * 1.6, r * 1.6, rad * 0.9);
    g.fillStyle = well; g.fill();

    g.save();
    roundRect(g, -r * 0.80, -r * 0.80, r * 1.6, r * 1.6, rad * 0.9); g.clip();
    const sr = r * 0.25;
    /* a heaped bowl: base ring, then a middle ring, then the crown */
    const rings = [
      { rr: 1.55, n: 8, off: 0.0, z: 0.94 },
      { rr: 0.78, n: 5, off: 0.35, z: 1.0 },
      { rr: 0.0, n: 1, off: 0.0, z: 1.04 },
    ];
    for (const ring of rings) {
      for (let i = 0; i < ring.n; i++) {
        const a = ring.rr === 0 ? 0 : (i / ring.n) * Math.PI * 2 + ring.off;
        stone(g, Math.cos(a) * sr * ring.rr * 2.0,
              Math.sin(a) * sr * ring.rr * 1.7 - r * 0.04,
              sr * ring.z, color);
      }
    }
    g.restore();
  }
  g.restore();

  if (!lid && b.label) {
    g.fillStyle = "rgba(255, 240, 214, 0.8)";
    g.font = `${Math.max(9, Math.round(r * 0.26))}px Georgia`;
    g.textAlign = "center"; g.textBaseline = "top";
    g.fillText(b.label, 0, r * 1.12);
  }
  g.restore();
}

function paint() {
  if (!state) return;
  const dpr = window.devicePixelRatio || 1;
  const S = scene();
  S.cell = S.px / (state.size + 1.1);
  S.pad = S.cell * 1.05;
  const cb = state.captured_by || {};
  for (const b of S.bowls) {
    if (b.lid) continue;
    b.count = cb[String(b.color)] || 0;
    b.label = b.count ? b.count + " taken" : "";
  }
  canvas.width = Math.round(S.W * dpr);
  canvas.height = Math.round(S.H * dpr);
  canvas.style.width = S.W + "px";
  canvas.style.height = S.H + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, S.W, S.H);
  L = S;
  renderBoard(ctx, state.size, state.board, S, {
    labels: true,
    hover: state.over ? null : hover,
    hoverColor: state.turn,
    last: state.last_move,
    territory: state.territory,
    anim: true,
    bowls: S.bowls,
  });
}

function runAnim() {
  if (animFrame) return;
  const now = performance.now();
  pop.forEach((v, k) => { if (!v) pop.set(k, now); });
  if (!pop.size) return;
  const step = () => {
    const t = performance.now();
    for (const [k, v] of pop) if (t - v > 160) pop.delete(k);
    paint();
    animFrame = pop.size ? requestAnimationFrame(step) : null;
  };
  animFrame = requestAnimationFrame(step);
}

function line(g, x1, y1, x2, y2) { g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke(); }
function diamond(g, cx, cy, r) { g.beginPath(); g.moveTo(cx, cy - r); g.lineTo(cx + r, cy); g.lineTo(cx, cy + r); g.lineTo(cx - r, cy); g.closePath(); }
function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  if (g.roundRect) g.roundRect(x, y, w, h, r);
  else g.rect(x, y, w, h);
}
function easeOutBack(t) { const c = 1.7; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); }
function stars(size) {
  if (size === 9) return [[2, 2], [6, 2], [2, 6], [6, 6], [4, 4]];
  if (size === 13) return [3, 6, 9].flatMap((x) => [3, 6, 9].map((y) => [x, y]));
  return [3, 9, 15].flatMap((x) => [3, 9, 15].map((y) => [x, y]));
}

/* ------------------------------------------------------------------ input */
function posFromEvent(ev) {
  if (!L) return null;
  const rect = canvas.getBoundingClientRect();
  const x = Math.round((ev.clientX - rect.left - L.bx - L.pad) / L.cell);
  const y = Math.round((ev.clientY - rect.top - L.by - L.pad) / L.cell);
  if (x < 0 || y < 0 || x >= state.size || y >= state.size) return null;
  return { x, y };
}

canvas.addEventListener("mousemove", (ev) => {
  if (!state || state.over) { hover = null; return; }
  const p = posFromEvent(ev);
  const same = p && hover && p.x === hover.x && p.y === hover.y;
  hover = p && state.board[p.x][p.y] === 0 ? p : null;
  if (!same) paint();
});
canvas.addEventListener("mouseleave", () => { hover = null; paint(); });
canvas.addEventListener("click", async (ev) => {
  if (busy || !state) return;
  if (state.over) { hint("Game over — press New Game to play again."); return; }
  const p = posFromEvent(ev);
  if (!p || state.board[p.x][p.y] !== 0) return;
  if (state.ai_color !== null && state.turn !== state.human_color) return;
  busy = true; updatePanel();
  clickStone();
  try {
    apply(await api("/api/move", p));
  } catch (e) {
    hint("Server unreachable — reload the page.");
  } finally {
    busy = false; updatePanel();
  }
});

let hintTimer = null;
function hint(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(hintTimer);
  hintTimer = setTimeout(() => t.classList.add("hidden"), 2600);
}

/* ------------------------------------------------------------------ panel */
function updatePanel() {
  if (!state) return;
  const turnEl = $("#turn");
  const dot = state.turn === BLACK ? "●" : "○";
  const who = state.turn === BLACK ? "Black" : "White";
  if (state.over) {
    turnEl.textContent = "Game over";
    turnEl.classList.remove("thinking");
  } else if (busy && state.ai_color !== null && state.turn === state.ai_color) {
    turnEl.textContent = dot + " AI is thinking…";
    turnEl.classList.add("thinking");
  } else {
    const suffix = state.ai_color !== null && state.turn === state.human_color ? " — your move" : "";
    turnEl.textContent = dot + " " + who + suffix;
    turnEl.classList.remove("thinking");
  }
  $("#thinking").classList.toggle("hidden", !(busy && state.ai_color !== null));
  const cb = state.captured_by;
  $("#meta").innerHTML =
    `Moves: ${state.move_number} &nbsp;·&nbsp; Komi: ${state.komi}<br>` +
    `Captured — ● Black: ${cb["1"] || 0} &nbsp; ○ White: ${cb["-1"] || 0}` +
    (state.over && state.result
      ? `<br><b>${state.result.winner}</b> wins by ${state.result.margin.toFixed(1)}`
      : "");
  $("#ai-only").classList.toggle("hidden", mode2P);
  $("#m-ai").classList.toggle("on", !mode2P);
  $("#m-2p").classList.toggle("on", mode2P);
  if (state.over) showScoreDialog();
}

function log(msg, err = false) {
  const li = document.createElement("li");
  li.innerHTML = msg;
  if (err) li.className = "err";
  const ul = $("#log");
  ul.prepend(li);
  while (ul.children.length > 30) ul.lastChild.remove();
}

let toastTimer = null;
function toast(msg) {
  const t = $("#toast");
  t.textContent = "Illegal — " + msg;
  t.classList.remove("hidden");
  log(msg, true);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 2600);
}

/* ------------------------------------------------------------------ buttons */
let mode2P = false;
$("#m-ai").onclick = () => { mode2P = false; updatePanel(); };
$("#m-2p").onclick = () => { mode2P = true; updatePanel(); };

$("#btn-new").onclick = async () => {
  busy = true; updatePanel();
  try {
    apply(await api("/api/new", {
      size: +$("#size").value,
      mode: mode2P ? "2 Players" : "vs AI",
      level: $("#level").value,
      human_color: +$("#color").value,
    }));
    log(`<b>New game</b> · ${$("#size").value}×${$("#size").value} · ${mode2P ? "2 players" : $("#level").value + " AI"}`);
  } catch (e) {
    hint("Could not start a game — reload the page.");
  } finally {
    busy = false; updatePanel();
  }
};

$("#btn-pass").onclick = async () => {
  if (busy || !state || state.over) return;
  busy = true; updatePanel();
  try {
    apply(await api("/api/pass"));
    log("Pass");
  } catch (e) {
    hint("Server unreachable — reload the page.");
  } finally {
    busy = false; updatePanel();
  }
};

$("#btn-undo").onclick = async () => {
  if (busy || !state || state.move_number === 0) return;
  busy = true; updatePanel();
  try {
    apply(await api("/api/undo"));
    log("Undo");
  } catch (e) {
    hint("Server unreachable — reload the page.");
  } finally {
    busy = false; updatePanel();
  }
};

$("#btn-score").onclick = async () => {
  if (busy || !state || state.over) return;
  if (!confirm("End the game now and count the board?")) return;
  busy = true; updatePanel();
  try {
    apply(await api("/api/score"));
    log("Score requested — game ended");
  } catch (e) {
    hint("Server unreachable — reload the page.");
  } finally {
    busy = false; updatePanel();
  }
};

/* ------------------------------------------------------------------ dialogs */
const RULES_HTML = `
<h3>How to play</h3>
<pre>Black and White take turns placing stones on the LINE INTERSECTIONS.
Black goes first; White gets 7.5 komi compensation for moving second.
Stones never move — they are only removed when captured.
The game ends after two passes in a row, then the board is counted.
</pre>
<h3>The rules, in math</h3>
<pre class="formula">Liberties    L(G) = { p empty : p orthogonally adjacent to group G }
Capture      |L(G)| = 0  ⟹  G is removed from the board
Suicide      legal ⟺ after captures, |L(own group)| ≥ 1
Ko           new position ∉ { every position so far }  (super-ko)
Area score   S(B) = stones(B) + territory(B)
             S(W) = stones(W) + territory(W) + komi (7.5)
             stones(B)+stones(W)+terr(B)+terr(W)+dame = size²
</pre>
<h3>The math behind the AI</h3>
<pre class="formula">Influence    I_c(p) = Σ γ^d(p,s)      γ = 0.62, d = Manhattan distance
Move value   v(m) = 14·|cap| + 5·atari + 3·min(|L|,4) + 4·links + 8·escape
                  + 6·ΔI − 5·waste − 9·self-atari + shape
Hard mode    v*(m) = v(m) − 0.85·max v(opponent reply)
Master mode  PUCT tree search:
             child = argmax  W/N + c·P(a)·√ΣN/(1+N)
             + random playouts scored by the area formula above</pre>
`;

$("#btn-rules").onclick = () => {
  $("#rules-text").innerHTML = RULES_HTML;
  $("#dlg-rules").showModal();
};

function showScoreDialog() {
  const r = state.result;
  if (!r || showScoreDialog.shown) return;
  showScoreDialog.shown = true;
  $("#score-text").innerHTML = `
<pre class="formula">Black:  ${r.black_stones} stones + ${r.black_territory} territory            = ${r.black_total.toFixed(1)}
White:  ${r.white_stones} stones + ${r.white_territory} territory + ${r.komi} komi = ${r.white_total.toFixed(1)}
Neutral points (dame): ${r.dame}

Winner: ${r.winner} by ${r.margin.toFixed(1)} points</pre>`;
  $("#dlg-score").showModal();
  log(`<b>${r.winner}</b> wins by ${r.margin.toFixed(1)} points`);
}

/* ------------------------------------------------------------------ learn */
const LESSONS = [
  { t: "1 · The board and the stones",
    d: "Go is played on the intersections of the lines, not in the squares.\n\nBlack and White alternate, Black first. Once placed, a stone never moves — it can only be captured.\n\nThe goal: surround more territory than your opponent.",
    s: [[2, 2, BLACK], [6, 6, BLACK], [6, 2, WHITE], [2, 6, WHITE], [4, 4, BLACK]] },
  { t: "2 · Liberties — L(G)",
    d: "A stone's open orthogonal neighbours (never diagonal) are its liberties:\n\n    L(G) = { p empty : p adjacent to G }\n\nConnected stones form one group that shares every liberty.",
    s: [[4, 4, BLACK]], marks: [[3, 4], [5, 4], [4, 3], [4, 5]] },
  { t: "3 · Capture — |L(G)| = 0",
    d: "Fill the last liberty of a group and the whole group is removed:\n\n    |L(G)| = 0 ⟹ G leaves the board\n\nWhite surrounds one black stone; the marked point is its last liberty.",
    s: [[4, 4, BLACK], [3, 4, WHITE], [5, 4, WHITE], [4, 3, WHITE]], marks: [[4, 5]] },
  { t: "4 · No suicide",
    d: "You may not place a stone that leaves your own group with zero liberties — unless the move captures first and opens them.",
    s: [[1, 0, WHITE], [0, 1, WHITE]], marks: [[0, 0]] },
  { t: "5 · Ko — no instant recapture",
    d: "After a capture, recreating the previous position is forbidden:\n\n    position(new) ∉ { positions so far }\n\nBlack captures the lone white stone; White must play elsewhere before recapturing.",
    s: [[3, 2, BLACK], [2, 3, BLACK], [3, 4, BLACK], [3, 3, WHITE], [4, 2, WHITE], [4, 4, WHITE], [5, 3, WHITE]], marks: [[4, 3]] },
  { t: "6 · Territory & scoring",
    d: "Two passes end the game. Regions touching one colour only become territory:\n\n    S(B) = stones(B) + territory(B)\n    S(W) = stones(W) + territory(W) + 7.5\n\nThe shaded diamonds show each side's territory; the middle column is neutral dame.",
    s: [0, 1, 2, 3, 4, 5, 6, 7, 8].flatMap((y) => [[3, y, BLACK], [5, y, WHITE]]), terr: true },
  { t: "7 · The math of the Master",
    d: "Easy/Medium/Hard use the evaluation function; Master runs PUCT Monte-Carlo Tree Search:\n\n    child = argmax W/N + c·P(a)·√ΣN/(1+N)\n\nthousands of random playouts, each scored by the area formula, feed the win rates W/N. Try it on 9×9!",
    s: [[4, 4, BLACK], [2, 6, WHITE], [6, 2, WHITE]] },
];
let lessonIdx = 0;

function renderLesson() {
  const L = LESSONS[lessonIdx];
  $("#lesson-title").textContent = L.t;
  $("#lesson-body").textContent = L.d;
  $("#lesson-nav").innerHTML = "";
  const size = 9;
  const board = Array.from({ length: size }, () => Array(size).fill(0));
  for (const [x, y, c] of L.s) board[x][y] = c;
  const mini = $("#mini-board");
  const dpr = window.devicePixelRatio || 1;
  const px = Math.min(320, window.innerWidth * 0.7);
  mini.width = px * dpr; mini.height = px * dpr;
  mini.style.width = px + "px"; mini.style.height = px + "px";
  const g = mini.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  let territory = null;
  if (L.terr) {
    territory = {};
    for (let x = 0; x < size; x++)
      for (let y = 0; y < size; y++) {
        if (board[x][y]) continue;
        if (x < 3) territory[x + "," + y] = "B";
        else if (x > 5) territory[x + "," + y] = "W";
        else territory[x + "," + y] = "dame";
      }
  }
  renderBoard(g, size, board, plainScene(px), { labels: false, territory });
  if (L.marks) {
    const cell = px / (size + 1.1), pad = cell * 1.05;
    for (const [x, y] of L.marks) {
      g.fillStyle = "#2e8b57";
      g.beginPath();
      g.arc(pad + x * cell, pad + y * cell, cell * 0.16, 0, 7);
      g.fill();
    }
  }
  const prevB = document.createElement("button");
  prevB.textContent = "← Back"; prevB.disabled = lessonIdx === 0;
  prevB.onclick = () => { lessonIdx--; renderLesson(); };
  const nextB = document.createElement("button");
  nextB.textContent = lessonIdx === LESSONS.length - 1 ? "Done" : "Next →";
  nextB.className = "primary";
  nextB.onclick = () => {
    if (lessonIdx === LESSONS.length - 1) $("#dlg-learn").close();
    else { lessonIdx++; renderLesson(); }
  };
  const nav = $("#lesson-nav");
  nav.append(prevB, nextB);
}

$("#btn-learn").onclick = () => {
  if (!$("#lesson-nav")) {
    $("#dlg-learn-body").innerHTML = `
      <h2 id="lesson-title"></h2>
      <canvas id="mini-board" class="mini-board"></canvas>
      <pre id="lesson-body"></pre>
      <div id="lesson-nav" class="lesson-nav"></div>
      <form method="dialog" style="margin-top:8px"><button class="primary" style="width:100%">Close</button></form>`;
  }
  lessonIdx = 0;
  renderLesson();
  $("#dlg-learn").showModal();
};

/* ------------------------------------------------------------------ boot */
window.addEventListener("resize", paint);
refresh();
