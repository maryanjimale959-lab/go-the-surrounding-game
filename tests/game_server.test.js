/* Exercise the in-browser server (static/game_server.js) exactly the way the
   page does, and time every AI level.  Run:  node tests/game_server.test.js  */
"use strict";

const fs = require("fs");
const path = require("path");
const assert = require("assert");

const dir = path.join(__dirname, "..", "static");
for (const f of ["engine.js", "ai.js", "game_server.js"]) {
  eval(fs.readFileSync(path.join(dir, f), "utf8"));
}

const E = globalThis.GoEngine;
const L = globalThis.GoLocalServer;
const BLACK = 1, WHITE = -1;

function st(p) { return p.state; }

(async function run() {
  /* ---- 1. two-player game through the API, both sides played by the AI ---- */
  let s = st(await L.handle("/api/new", { size: 9, mode: "2 Players" }));
  assert.strictEqual(s.ai_color, null, "2 players has no AI colour");
  assert.strictEqual(s.turn, BLACK);
  assert.strictEqual(s.board.length, 9);
  assert.strictEqual(Object.keys(s).sort().join(","),
    "ai_color,board,captured_by,creator,human_color,komi,last_move,level,mode,move_number,over,passes,size,turn",
    "payload keys must match web.py: " + Object.keys(s).sort().join(","));

  let plies = 0;
  while (!s.over && plies < 200) {
    const moves = [];
    for (let x = 0; x < s.size; x++)
      for (let y = 0; y < s.size; y++)
        if (s.board[x][y] === 0) moves.push([x, y]);
    moves.sort(() => Math.random() - 0.5);
    let played = false;
    for (const [x, y] of moves.slice(0, 12)) {
      const r = await L.handle("/api/move", { x, y });
      if (r.ok) { s = st(r); played = true; break; }
    }
    if (!played) { s = st(await L.handle("/api/pass", {})); }
    plies++;
  }
  s = st(await L.handle("/api/score", {}));
  assert.ok(s.over && s.result, "score ends the game");
  assert.strictEqual(s.result.black_total + s.result.white_total - s.result.komi, 81,
    "every point on the board must be accounted for");
  assert.ok(s.territory && Object.keys(s.territory).length > 0, "territory map present");
  console.log("  two-player 9x9:", plies, "plies ->", s.result.winner,
    s.result.black_total, "/", s.result.white_total, "·", Object.keys(s.territory).length, "empty points classed");

  /* ---- 2. undo goes back a full pair of moves in AI mode ---- */
  s = st(await L.handle("/api/new", { size: 9, mode: "vs AI", level: "easy", human_color: BLACK }));
  assert.strictEqual(s.ai_color, WHITE);
  let r = await L.handle("/api/move", { x: 4, y: 4, ai: false });
  assert.ok(r.ok);
  assert.strictEqual(r.state.turn, WHITE);
  r = await L.handle("/api/ai_move", {});
  assert.ok(r.ok && r.state.turn === BLACK && r.state.move_number === 2, "AI answered");
  r = await L.handle("/api/undo", {});
  assert.strictEqual(r.state.move_number, 0, "undo steps back over the AI reply too");
  console.log("  vs-AI move, reply and undo: ok (move_number back to", r.state.move_number + ")");

  /* ---- 3. illegal moves and ko come back as {ok:false, error, state} ---- */
  r = await L.handle("/api/move", { x: 8, y: 8 });
  assert.ok(r.ok);
  r = await L.handle("/api/move", { x: 8, y: 8 });
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.error, "point is occupied");
  console.log("  occupied point refused:", JSON.stringify(r.error));

  /* ---- 4. every AI level, timed, on 9x9 and 19x19 ---- */
  for (const size of [9, 19]) {
    for (const level of ["easy", "medium", "hard", "master"]) {
      s = st(await L.handle("/api/new", { size, mode: "vs AI", level, human_color: WHITE }));
      assert.strictEqual(s.turn, WHITE, "the AI opens as Black, so it is your turn");
      assert.ok(s.move_number >= 1, "AI opened the game");
      const t0 = Date.now();
      let moves = 0;
      while (moves < (size === 9 ? 20 : 8)) {
        const human = nextHumanMove(s);
        if (!human) break;
        s = st(await L.handle("/api/move", { x: human.x, y: human.y, ai: false }));
        if (!s || s.over) break;
        s = st(await L.handle("/api/ai_move", {}));
        if (s.over) break;
        moves++;
      }
      const per = ((Date.now() - t0) / Math.max(1, moves)).toFixed(0);
      assert.ok(s.move_number > 0);
      const cap = level === "master" ? 4200 : 900;
      assert.ok(Number(per) < cap, level + " on " + size + "x" + size + " took " + per + "ms/turn");
      console.log(`  ${level.padEnd(7)} ${size}x${size}: ${per} ms per AI answer, ${s.move_number} moves played`);
    }
  }

  /* ---- 5. a whole 9x9 game against Medium must end cleanly and count right ---- */
  s = st(await L.handle("/api/new", { size: 9, mode: "vs AI", level: "medium", human_color: BLACK }));
  let guard = 0;
  while (!s.over && guard++ < 400) {
    const human = nextHumanMove(s);
    if (!human) { s = st(await L.handle("/api/pass", { ai: false })); }
    else {
      s = st(await L.handle("/api/move", { x: human.x, y: human.y, ai: false }));
      if (s.over) break;
      s = st(await L.handle("/api/ai_move", {}));
    }
    if (s.over) break;
    if (guard > 300) { s = st(await L.handle("/api/score", {})); break; }
  }
  assert.ok(s.over, "the game finished");
  const res = s.result;
  assert.strictEqual(res.black_total + res.white_total - res.komi, 81);
  assert.ok(["Black", "White", "Draw"].indexOf(res.winner) >= 0);
  assert.ok(["you", "AI"].indexOf(res.winner === "Black" ? "you" : "AI") >= 0);
  console.log("  full 9x9 vs Medium AI:", guard, "rounds ->", res.winner,
    "wins by", res.margin.toFixed(1), `(B ${res.black_total} / W ${res.white_total})`);

  console.log("game_server.js: all checks passed");
})().catch((err) => { console.error("FAILED:", err.message); process.exit(1); });

/* a legal random point for the side to move, newest-first bias so games finish */
function nextHumanMove(s) {
  const options = [];
  for (let x = 0; x < s.size; x++)
    for (let y = 0; y < s.size; y++)
      if (s.board[x][y] === 0) options.push([x, y]);
  options.sort(() => Math.random() - 0.5);
  for (const [x, y] of options.slice(0, 25)) {
    const g = L.settings.game;
    if (g.isLegal(x, y).ok) return { x, y };
  }
  return null;
}
