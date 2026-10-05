/* The game server, in the page.
   ---------------------------------------------------------------------
   web.py and this file speak the same JSON:

     GET  state      -> the whole game
     POST new        {size, mode, level, human_color}
     POST move       {x, y, ai:false}   ai:false keeps the reply for later
     POST ai_move    {}                 let the AI answer now
     POST pass       {ai:false}
     POST undo       {}                 two plies in AI mode
     POST score      {}                 stop now and count the board

   When the page is opened from GitHub Pages there is no Python behind it, so
   the browser runs the engine, the AI and the MCTS itself.  Opened through
   `python web.py` the real server answers and this file is not used.
*/
(function (global) {
  "use strict";

  const E = global.GoEngine, AI = global.GoAI_;
  const BLACK = E.BLACK, WHITE = E.WHITE;
  const CREATOR = "Maryam J.";
  const MCTS_SECONDS = 2.5;
  const SIZES = [9, 13, 19];
  const LEVELS = ["easy", "medium", "hard", "master"];

  const S = {
    game: new E.Game(9),
    ai_color: WHITE,
    human_color: BLACK,
    mode: "vs AI",
    level: "medium",
  };

  function applySettings(mode, level, humanColor) {
    S.mode = mode;
    S.level = level;
    S.human_color = humanColor;
    S.ai_color = mode === "2 Players" ? null : -humanColor;
  }

  function statePayload() {
    const g = S.game;
    const d = {
      size: g.size,
      board: E.toNested(g.board, g.size),
      turn: g.current,
      move_number: g.move_number,
      last_move: g.last_move,
      passes: g.passes,
      captured_by: { "1": g.captured_by[1], "-1": g.captured_by["-1"] },
      over: g.over,
      mode: S.mode,
      level: S.level,
      human_color: S.human_color,
      ai_color: S.ai_color,
      komi: g.komi,
      creator: CREATOR,
    };
    if (g.over) {
      d.result = g.finalScore();
      d.territory = {};
      g.territoryMap().forEach(function (o, idx) {
        const x = Math.floor(idx / g.size), y = idx % g.size;
        d.territory[x + "," + y] = o === BLACK ? "B" : o === WHITE ? "W" : "dame";
      });
    }
    return d;
  }

  function mover() {
    if (S.ai_color === null) return null;
    return S.level === "master" ? new AI.MCTS(S.ai_color, MCTS_SECONDS)
                                : new AI.GoAI(S.ai_color, S.level);
  }

  async function aiTurn() {
    const g = S.game, m = mover();
    if (!m || g.over || g.current !== S.ai_color) return;
    const mv = await m.chooseMove(g);
    if (!mv) g.passMove();
    else g.play(mv.x, mv.y);
  }

  async function handle(path, body) {
    body = body || {};
    const g = S.game;
    if (path === "/api/state") {
      if (S.ai_color !== null && !g.over && g.current === S.ai_color && g.move_number) await aiTurn();
      return { ok: true, state: statePayload() };
    }
    if (path === "/api/new") {
      const size = Number(body.size) || 9;
      const mode = body.mode === "2 Players" ? "2 Players" : "vs AI";
      const level = LEVELS.indexOf(body.level) >= 0 ? body.level : "medium";
      const human = Number(body.human_color) === WHITE ? WHITE : BLACK;
      if (SIZES.indexOf(size) < 0) return { ok: false, error: "invalid settings" };
      S.game = new E.Game(size);
      applySettings(mode, level, human);
      await aiTurn();
      return { ok: true, state: statePayload() };
    }
    if (path === "/api/move") {
      if (S.ai_color !== null && g.current !== S.human_color)
        return { ok: false, error: "AI is to move", state: statePayload() };
      const played = g.play(Number(body.x), Number(body.y));
      if (!played.ok) return { ok: false, error: played.error, state: statePayload() };
      if (body.ai !== false) await aiTurn();
      return { ok: true, state: statePayload() };
    }
    if (path === "/api/ai_move") {
      await aiTurn();
      return { ok: true, state: statePayload() };
    }
    if (path === "/api/pass") {
      g.passMove();
      if (!g.over && body.ai !== false) await aiTurn();
      return { ok: true, state: statePayload() };
    }
    if (path === "/api/undo") {
      const steps = S.ai_color !== null ? 2 : 1;
      let did = false;
      for (let i = 0; i < steps; i++) if (g.undo()) did = true;
      return { ok: true, undid: did, state: statePayload() };
    }
    if (path === "/api/score") {
      g.finalScore();
      return { ok: true, state: statePayload() };
    }
    return { ok: false, error: "not found" };
  }

  global.GoLocalServer = { handle: handle, statePayload: statePayload, settings: S };
})(typeof window !== "undefined" ? window : globalThis);
