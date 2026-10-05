/* The browser opponent — a port of ai.py (evaluation function) and mcts.py
   (PUCT Monte-Carlo Tree Search, the Master level).
   ---------------------------------------------------------------------
   Easy / Medium / Hard rank every candidate move with one linear function:

     v(m) = 14*|cap| + 5*atari + 3*min(|L|,4) + 4*(links-1) + 8*escape
          + 6*(I_me - I_opp) - 5*waste - 9*self-atari + shape

   where influence is a geometric-decay field  I_c(p) = sum over stones of
   gamma^manhattan_distance  with gamma = 0.62.  Hard subtracts the opponent's
   best immediate reply:  v*(m) = v(m) - 0.85 * max v(opp reply).

   Master builds a search tree instead:
     selection  argmax  W/N + c*P(a)*sqrt(sum N)/(1+N)
     expansion  light heuristic policy prior (softmax, temperature 3)
     simulation fast playouts to two passes
     backup     area-score win signal up the tree

   Everything here is async and yields to the browser, so the page stays
   responsive and the "AI is thinking" animation keeps running.
*/
(function (global) {
  "use strict";

  const E = global.GoEngine;
  const BLACK = E.BLACK, WHITE = E.WHITE, EMPTY = E.EMPTY;
  const adj = E.adj, findGroup = E.findGroup, simulate = E.simulate, keyOf = E.keyOf;

  const DECAY = 0.62;
  const INFLUENCE_RADIUS = 6;
  const W = {
    capture: 14.0, atari: 5.0, liberty: 3.0, connect: 4.0, rescue: 8.0,
    influence: 6.0, waste: 5.0, risk: 9.0, reply: 0.85,
  };
  const LEVELS = {
    easy: { noise: 9.0, pick: 10, lookahead: false },
    medium: { noise: 2.5, pick: 3, lookahead: false },
    hard: { noise: 0.4, pick: 1, lookahead: true },
  };

  const CPUCT = 1.2;
  const POLICY_TEMP = 3.0;
  const MAX_SIMS = 20000;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* standard-normal sample (Box-Muller), like random.gauss(0, sigma) */
  function gauss(sigma) {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return sigma * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  function edgeDistance(size, x, y) {
    return Math.min(x, y, size - 1 - x, size - 1 - y);
  }
  function shapeBonus(size, x, y) {
    const d = edgeDistance(size, x, y);
    if (d === 0) return -6.0;
    if (d === 1) return -3.0;
    if (d === 2 || d === 3) return 2.5;
    return 0.0;
  }

  /* I_c(p) = sum of decay^distance over that colour's stones, radius 6 */
  function influenceMap(board, size, color) {
    const A = adj(size);
    const field = new Float64Array(size * size);
    for (let start = 0; start < board.length; start++) {
      if (board[start] !== color) continue;
      const seen = new Uint8Array(size * size);
      let frontier = [start];
      seen[start] = 1;
      let power = 1.0;
      for (let radius = 0; radius <= INFLUENCE_RADIUS && frontier.length && power > 0.02; radius++) {
        const next = [];
        for (const c of frontier) {
          field[c] += power;
          for (const n of A[c]) if (!seen[n]) { seen[n] = 1; next.push(n); }
        }
        power *= DECAY;
        frontier = next;
      }
    }
    return field;
  }

  function groupKey(stones) {
    return Array.from(stones).sort((a, b) => a - b).join(".");
  }

  /* ------------------------------------------------------------ greedy AI */
  class GoAI {
    constructor(color, level = "medium") {
      this.color = color;
      this.level = LEVELS[level] ? level : "medium";
    }

    _scoreMove(game, x, y, infMe, infOpp) {
      const color = this.color, enemy = -color;
      const size = game.size, board = game.board;
      const sim = simulate(board, size, x, y, color);
      if (!sim) return null;
      const nb = sim.board;
      if (game.positions.has(keyOf(nb))) return null;      // ko / super-ko
      const idx = x * size + y;
      const mine = findGroup(nb, size, idx);
      const libs = mine.liberties.size;
      const A = adj(size);

      let score = W.capture * sim.captured.size + W.liberty * Math.min(libs, 4);

      const seenGroups = new Set();
      for (const n of A[idx]) {
        if (nb[n] !== enemy) continue;
        const g = findGroup(nb, size, n);
        const k = groupKey(g.stones);
        if (seenGroups.has(k)) continue;
        seenGroups.add(k);
        if (g.liberties.size === 1) score += W.atari;
      }

      const myGroups = [];
      const groupSeen = new Set();
      for (const n of A[idx]) {
        if (board[n] !== color) continue;
        const g = findGroup(board, size, n);
        const k = groupKey(g.stones);
        if (groupSeen.has(k)) continue;
        groupSeen.add(k);
        myGroups.push({ libs: g.liberties.size });
      }
      score += W.connect * Math.max(0, myGroups.length - 1);

      for (const g of myGroups) {
        if (g.libs === 1 && libs > 1) { score += W.rescue; break; }
      }
      if (libs === 1 && !sim.captured.size) score -= W.risk;

      const gain = infMe[idx] - infOpp[idx];
      score += W.influence * gain;
      if (gain > 0) score -= W.waste * gain;

      return score + shapeBonus(size, x, y);
    }

    _candidates(game) {
      const size = game.size, board = game.board;
      if (game.move_number === 0) {
        const c = Math.floor(size / 2);
        const off = size >= 15 ? 3 : 2;
        const pts = [];
        for (let dx = -off; dx <= off; dx += off)
          for (let dy = -off; dy <= off; dy += off) {
            const x = c + dx, y = c + dy;
            if (x >= 0 && x < size && y >= 0 && y < size) pts.push([x, y]);
          }
        return pts;
      }
      const near = new Set();
      for (let x = 0; x < size; x++) {
        for (let y = 0; y < size; y++) {
          if (board[x * size + y] === EMPTY) continue;
          for (let dx = -2; dx <= 2; dx++) {
            for (let dy = -2; dy <= 2; dy++) {
              const nx = x + dx, ny = y + dy;
              if (nx < 0 || ny < 0 || nx >= size || ny >= size) continue;
              if (board[nx * size + ny] !== EMPTY) continue;
              if (Math.abs(dx) + Math.abs(dy) > 3) continue;
              near.add(nx * size + ny);
            }
          }
        }
      }
      return Array.from(near).sort((a, b) => a - b)
        .map((i) => [Math.floor(i / size), i % size]);
    }

    _rank(game, infMe, infOpp) {
      const scored = [];
      for (const [x, y] of this._candidates(game)) {
        const s = this._scoreMove(game, x, y, infMe, infOpp);
        if (s !== null) scored.push([s, x, y]);
      }
      scored.sort((a, b) => b[0] - a[0] || b[1] - a[1] || b[2] - a[2]);
      return scored;
    }

    async chooseMove(game) {
      const size = game.size;
      const infMe = influenceMap(game.board, size, this.color);
      const infOpp = influenceMap(game.board, size, -this.color);
      let scored = this._rank(game, infMe, infOpp);
      const cfg = LEVELS[this.level];
      if (!scored.length) return null;
      if (cfg.lookahead && scored.length > 1) {
        scored = await this._refineWithReply(game, scored.slice(0, 12));
        if (!scored.length) return null;
      }
      const pool = scored.slice(0, cfg.pick);
      let best = pool[0], bestScore = -Infinity;
      for (const cand of pool) {
        const v = cand[0] + gauss(cfg.noise);
        if (v > bestScore) { bestScore = v; best = cand; }
      }
      return { x: best[1], y: best[2] };
    }

    /* v_hard(m) = v(m) - 0.85 * best immediate enemy reply */
    async _refineWithReply(game, myScored) {
      const size = game.size;
      const enemyAi = new GoAI(-this.color, "medium");
      const view = { size, board: game.board, positions: game.positions, move_number: game.move_number };
      const refined = [];
      for (const [s, x, y] of myScored) {
        const sim = simulate(game.board, size, x, y, this.color);
        if (!sim) continue;
        view.board = sim.board;
        const eInfMe = influenceMap(sim.board, size, -this.color);
        const eInfOpp = influenceMap(sim.board, size, this.color);
        const reply = enemyAi._rank(view, eInfMe, eInfOpp);
        const threat = reply.length ? reply[0][0] : 0.0;
        refined.push([s - W.reply * Math.max(0.0, threat), x, y]);
        await sleep(0);                     // let the page breathe between replies
      }
      refined.sort((a, b) => b[0] - a[0] || b[1] - a[1] || b[2] - a[2]);
      return refined;
    }
  }

  /* ------------------------------------------------------------ MCTS */
  function applyInPlace(board, size, x, y, color) {
    const sim = simulate(board, size, x, y, color);
    if (!sim) return -1;
    for (let i = 0; i < board.length; i++) board[i] = sim.board[i];
    return sim.captured.size;
  }

  function candidatePoints(board, size) {
    const near = new Set();
    for (let x = 0; x < size; x++) {
      for (let y = 0; y < size; y++) {
        if (board[x * size + y] === EMPTY) continue;
        for (let dx = -2; dx <= 2; dx++) {
          for (let dy = -2; dy <= 2; dy++) {
            if (Math.abs(dx) + Math.abs(dy) > 3) continue;
            const nx = x + dx, ny = y + dy;
            if (nx < 0 || ny < 0 || nx >= size || ny >= size) continue;
            if (board[nx * size + ny] === EMPTY) near.add(nx * size + ny);
          }
        }
      }
    }
    if (!near.size) {
      const c = Math.floor(size / 2), off = size >= 15 ? 3 : 2;
      for (let dx = -off; dx <= off; dx += off)
        for (let dy = -off; dy <= off; dy += off) {
          const x = c + dx, y = c + dy;
          if (x >= 0 && x < size && y >= 0 && y < size) near.add(x * size + y);
        }
    }
    return near;
  }

  function lightScore(board, size, idx, color) {
    const x = Math.floor(idx / size), y = idx % size;
    const sim = simulate(board, size, x, y, color);
    if (!sim) return null;
    const libs = findGroup(sim.board, size, idx).liberties.size;
    let s = 12.0 * sim.captured.size + 2.0 * Math.min(libs, 4);
    if (libs === 1 && !sim.captured.size) s -= 6.0;
    if (edgeDistance(size, x, y) <= 1) s -= 2.0;
    let friends = 0;
    for (const n of adj(size)[idx]) if (board[n] === color) friends++;
    if (friends >= 2 && !sim.captured.size) s -= 2.5;
    return s + Math.random();
  }

  /* softmax policy prior over the candidate points */
  function policy(board, size, color) {
    const scored = [];
    for (const idx of candidatePoints(board, size)) {
      const s = lightScore(board, size, idx, color);
      if (s !== null) scored.push([s, idx]);
    }
    if (!scored.length) return [];
    let top = -Infinity;
    for (const [s] of scored) if (s > top) top = s;
    let z = 0;
    const exps = scored.map(([s, idx]) => {
      const e = Math.exp((s - top) / POLICY_TEMP);
      z += e;
      return [e, idx];
    });
    return exps.map(([e, idx]) => [e / z, idx]);
  }

  function playout(board, size, current, moveCap, komi, deadline) {
    const b = board.slice();
    let passes = 0;
    const cap = Math.min(Math.max(0, moveCap), size * size);
    for (let i = 0; i < cap; i++) {
      if (i % 12 === 11 && Date.now() > deadline) break;
      const scored = [];
      for (const idx of candidatePoints(b, size)) {
        const s = lightScore(b, size, idx, current);
        if (s !== null) scored.push([s, idx]);
      }
      if (!scored.length) break;
      scored.sort((p, q) => q[0] - p[0]);
      let played = false;
      if (scored[0][0] > 0.5) {
        const pick = scored[Math.floor(Math.random() * Math.min(3, scored.length))];
        const x = Math.floor(pick[1] / size), y = pick[1] % size;
        if (applyInPlace(b, size, x, y, current) >= 0) { passes = 0; played = true; }
      }
      if (!played) { passes += 1; if (passes >= 2) break; }
      current = -current;
    }
    return E.scoreBoard(b, size, komi);
  }

  class Node {
    constructor(move, parent, prior, player) {
      this.move = move;          // idx played, or null for the root
      this.parent = parent;
      this.children = [];
      this.visits = 0;
      this.wins = 0.0;
      this.prior = prior;
      this.untried = null;
      this.player = player;      // colour that PLAYED this.move
    }
    ucb(parentVisits) {
      const exploit = this.wins / (this.visits + 1e-9);
      const explore = CPUCT * this.prior * Math.sqrt(parentVisits) / (1.0 + this.visits);
      return exploit + explore;
    }
  }

  class MCTS {
    constructor(color, seconds = 3.0) {
      this.color = color;
      this.seconds = seconds;
    }

    async chooseMove(game) {
      const size = game.size, komi = game.komi;
      const deadline = Date.now() + this.seconds * 1000;
      const root = new Node(null, null, 1.0, -this.color);
      const moveCap = 2 * size * size;

      const priors = policy(game.board, size, this.color);
      for (const [prior, idx] of priors) {
        const x = Math.floor(idx / size), y = idx % size;
        const sim = simulate(game.board, size, x, y, this.color);
        if (!sim || game.positions.has(keyOf(sim.board))) continue;
        root.children.push(new Node(idx, root, prior, this.color));
      }
      root.untried = [];
      if (!root.children.length) return null;

      let sims = 0;
      while (Date.now() < deadline && sims < MAX_SIMS) {
        sims += 1;
        /* ---- selection ---- */
        let node = root;
        const path = [];
        for (;;) {
          if (node.untried === null && node !== root) node.untried = this._policyChildren(game, node, path);
          if (node.untried && node.untried.length) {
            const [prior, idx] = node.untried.shift();
            const child = new Node(idx, node, prior, -node.player);
            node.children.push(child);
            node = child;
            path.push([idx, node.player]);
            break;
          }
          if (!node.children.length) break;
          let bestChild = node.children[0];
          for (const c of node.children) if (c.ucb(node.visits) > bestChild.ucb(node.visits)) bestChild = c;
          node = bestChild;
          if (node.move !== null) path.push([node.move, node.player]);
        }

        /* ---- simulation ---- */
        const board = game.board.slice();
        let toPlay = this.color;
        for (const [idx, player] of path) {
          applyInPlace(board, size, Math.floor(idx / size), idx % size, player);
          toPlay = -player;
        }
        const result = playout(board, size, toPlay, moveCap + path.length, komi, deadline);
        const blackWon = result.black_total > result.white_total;
        const reward = (blackWon === (this.color === BLACK)) ? 1.0 : 0.0;

        /* ---- backup ---- */
        const own = (player) => (player === this.color ? reward : 1.0 - reward);
        node.visits += 1;
        node.wins += own(node.player);
        let up = node.parent;
        while (up !== null) {
          up.visits += 1;
          if (up.move !== null) up.wins += own(up.player);
          up = up.parent;
        }

        if (sims % 25 === 0) await sleep(0);      // keep the page alive
      }

      let best = root.children[0];
      for (const c of root.children) if (c.visits > best.visits) best = c;
      return { x: Math.floor(best.move / size), y: best.move % size };
    }

    _policyChildren(game, node, path) {
      const size = game.size;
      const board = game.board.slice();
      for (let i = 0; i < path.length - 1; i++) {
        const [idx, player] = path[i];
        applyInPlace(board, size, Math.floor(idx / size), idx % size, player);
      }
      applyInPlace(board, size, Math.floor(node.move / size), node.move % size, node.player);
      return policy(board, size, -node.player);
    }
  }

  global.GoAI_ = { GoAI, MCTS, influenceMap, policy, lightScore, candidatePoints };
})(typeof window !== "undefined" ? window : globalThis);
