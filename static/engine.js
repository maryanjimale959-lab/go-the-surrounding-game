/* Go rules engine for the browser — a faithful port of engine.py.
   ---------------------------------------------------------------------
   Same maths, same results:

   * A group is an equivalence class of same-colour stones joined by the grid.
   * Liberties  L(G) = { empty points orthogonally adjacent to G }
   * Captured when |L(G)| = 0; a move may not be suicide after captures resolve.
   * Super-ko: a move may not recreate any position already seen.
   * Area (Chinese) scoring, with the neutral points (dame) shared out in
     filling order so that  S(B) + S(W) - komi == size*size  exactly.

   Boards are flat arrays indexed x*size + y with values 1 / -1 / 0.
   The JSON payload sent to the UI keeps engine.py's nested board[x][y] shape.
*/
(function (global) {
  "use strict";

  const BLACK = 1, WHITE = -1, EMPTY = 0;
  const LETTERS = "ABCDEFGHJKLMNOPQRST";    // Go convention skips the letter I

  function moveName(x, y) { return LETTERS[x] + (y + 1); }

  /* adjacency table per board size (built once, reused by every search) */
  const ADJ = new Map();
  function adj(size) {
    let table = ADJ.get(size);
    if (table) return table;
    table = new Array(size * size);
    for (let x = 0; x < size; x++) {
      for (let y = 0; y < size; y++) {
        const list = [];
        if (x + 1 < size) list.push((x + 1) * size + y);
        if (x - 1 >= 0) list.push((x - 1) * size + y);
        if (y + 1 < size) list.push(x * size + y + 1);
        if (y - 1 >= 0) list.push(x * size + y - 1);
        table[x * size + y] = list;
      }
    }
    ADJ.set(size, table);
    return table;
  }

  const newBoard = (size) => new Array(size * size).fill(EMPTY);
  const keyOf = (board) => board.join(",");

  function findGroup(board, size, idx) {
    const color = board[idx];
    if (color === EMPTY) return { stones: new Set(), liberties: new Set() };
    const A = adj(size);
    const stones = new Set([idx]);
    const liberties = new Set();
    const stack = [idx];
    while (stack.length) {
      const c = stack.pop();
      for (const n of A[c]) {
        const v = board[n];
        if (v === EMPTY) liberties.add(n);
        else if (v === color && !stones.has(n)) { stones.add(n); stack.push(n); }
      }
    }
    return { stones, liberties };
  }

  /* Place a stone on a copy and resolve captures.
     Returns {board, captured} or null when the point is occupied or the move
     would be suicide. */
  function simulate(board, size, x, y, color) {
    const idx = x * size + y;
    if (board[idx] !== EMPTY) return null;
    const nb = board.slice();
    nb[idx] = color;
    const A = adj(size);
    const enemy = -color;
    const captured = new Set();
    for (const n of A[idx]) {
      if (nb[n] === enemy && !captured.has(n)) {
        const g = findGroup(nb, size, n);
        if (!g.liberties.size) for (const s of g.stones) captured.add(s);
      }
    }
    for (const c of captured) nb[c] = EMPTY;
    if (!findGroup(nb, size, idx).liberties.size) return null;
    return { board: nb, captured };
  }

  /* Empty regions classified by the colour that borders them. */
  function territoryMap(board, size) {
    const A = adj(size);
    const seen = new Uint8Array(size * size);
    const owners = new Map();
    for (let start = 0; start < board.length; start++) {
      if (board[start] !== EMPTY || seen[start]) continue;
      const region = [start];
      seen[start] = 1;
      const borders = new Set();
      for (let i = 0; i < region.length; i++) {
        for (const n of A[region[i]]) {
          const v = board[n];
          if (v === EMPTY) { if (!seen[n]) { seen[n] = 1; region.push(n); } }
          else borders.add(v);
        }
      }
      const owner = borders.size === 1 && borders.has(BLACK) ? BLACK
                  : borders.size === 1 && borders.has(WHITE) ? WHITE
                  : "dame";
      for (const p of region) owners.set(p, owner);
    }
    return owners;
  }

  /* True when the move only turns ground the mover already owns into a stone.
     Under area scoring that point already counted for the mover, so the stone
     gains nothing — the moment a human passes. engine.py has the same rule,
     and it is what lets a game end on two passes with the borders closed. */
  function fillsOwnTerritory(board, size, x, y, color) {
    const idx = x * size + y;
    if (board[idx] !== EMPTY) return false;
    const sim = simulate(board, size, x, y, color);
    if (!sim || sim.captured.size) return false;
    return territoryMap(board, size).get(idx) === color;
  }

  /* Area scoring; `komi` is White's compensation for moving second.
     Neutral points are shared in filling order, Black first, so the count is
     exact: black_total + white_total - komi === size*size. */
  function scoreBoard(board, size, komi) {
    let blackStones = 0, whiteStones = 0;
    for (const v of board) { if (v === BLACK) blackStones++; else if (v === WHITE) whiteStones++; }
    const owners = territoryMap(board, size);
    let blackTerritory = 0, whiteTerritory = 0, dame = 0;
    owners.forEach((o) => {
      if (o === BLACK) blackTerritory++;
      else if (o === WHITE) whiteTerritory++;
      else dame++;
    });
    const blackDame = Math.ceil(dame / 2);
    const whiteDame = Math.floor(dame / 2);
    const blackTotal = blackStones + blackTerritory + blackDame;
    const whiteTotal = whiteStones + whiteTerritory + whiteDame + komi;
    const margin = blackTotal - whiteTotal;
    return {
      black_stones: blackStones,
      white_stones: whiteStones,
      black_territory: blackTerritory,
      white_territory: whiteTerritory,
      dame: dame,
      black_dame: blackDame,
      white_dame: whiteDame,
      komi: komi,
      black_total: blackTotal,
      white_total: whiteTotal,
      margin: Math.abs(margin),
      winner: margin > 0 ? "Black" : margin < 0 ? "White" : "Draw",
    };
  }

  class Game {
    constructor(size = 19, komi = 7.5) {
      this.size = size;
      this.komi = komi;
      this.board = newBoard(size);
      this.current = BLACK;
      this.passes = 0;
      this.captured_by = { 1: 0, "-1": 0 };
      this.move_number = 0;
      this.last_move = null;      // [x, y] or null
      this.over = false;
      this.result = null;
      this.history = [];
      this.positions = new Set([keyOf(this.board)]);
    }

    /* {ok, captured} | {ok:false, error} */
    isLegal(x, y) {
      if (this.over) return { ok: false, error: "game is over" };
      if (this.board[x * this.size + y] !== EMPTY)
        return { ok: false, error: "point is occupied" };
      const sim = simulate(this.board, this.size, x, y, this.current);
      if (!sim) return { ok: false, error: "suicide is not allowed" };
      if (this.positions.has(keyOf(sim.board)))
        return { ok: false, error: "ko: that move repeats the previous position" };
      return { ok: true, captured: sim.captured };
    }

    play(x, y) {
      const check = this.isLegal(x, y);
      if (!check.ok) return check;
      const sim = simulate(this.board, this.size, x, y, this.current);
      this._push();
      this.board = sim.board;
      this.captured_by[this.current] += sim.captured.size;
      this.passes = 0;
      this.move_number += 1;
      this.last_move = [x, y];
      this.positions.add(keyOf(sim.board));
      this.current = -this.current;
      return { ok: true, captured: sim.captured };
    }

    passMove() {
      if (this.over) return false;
      this._push();
      this.passes += 1;
      this.move_number += 1;
      this.last_move = null;
      if (this.passes >= 2) { this.over = true; this.result = this.score(); }
      this.current = -this.current;
      return true;
    }

    _push() {
      this.history.push({
        board: this.board.slice(),
        current: this.current,
        passes: this.passes,
        captured_by: { 1: this.captured_by[1], "-1": this.captured_by["-1"] },
        move_number: this.move_number,
        last_move: this.last_move,
      });
    }

    undo() {
      if (!this.history.length) return false;
      this.positions.delete(keyOf(this.board));
      const s = this.history.pop();
      this.board = s.board;
      this.current = s.current;
      this.passes = s.passes;
      this.captured_by = s.captured_by;
      this.move_number = s.move_number;
      this.last_move = s.last_move;
      this.over = false;
      this.result = null;
      return true;
    }

    territoryMap() { return territoryMap(this.board, this.size); }
    score() { return scoreBoard(this.board, this.size, this.komi); }

    finalScore() {
      if (!this.over) { this.over = true; this.result = this.score(); }
      return this.result;
    }
  }

  /* nested columns, engine.py's board[x][y] shape, for the JSON payload */
  function toNested(board, size) {
    const out = [];
    for (let x = 0; x < size; x++) {
      const col = new Array(size);
      for (let y = 0; y < size; y++) col[y] = board[x * size + y];
      out.push(col);
    }
    return out;
  }

  global.GoEngine = {
    BLACK, WHITE, EMPTY, LETTERS, moveName, adj, newBoard, keyOf,
    findGroup, simulate, territoryMap, fillsOwnTerritory, scoreBoard, toNested, Game,
  };
})(typeof window !== "undefined" ? window : globalThis);
