/* Replay random games in the browser engine and print its view of each final
   position, so tests_js.py can diff it against engine.py.

   node tests/compare_engine.js < games.json      (JSON array on stdin)
   each game: {size, moves: [[x,y] | "pass" | "undo"]}
*/
"use strict";

const fs = require("fs");
const path = require("path");

const dir = path.join(__dirname, "..", "static");
eval(fs.readFileSync(path.join(dir, "engine.js"), "utf8"));

const E = globalThis.GoEngine;

function snapshot(g) {
  const legal = [];
  const fillB = [], fillW = [];
  for (let x = 0; x < g.size; x++)
    for (let y = 0; y < g.size; y++) {
      if (g.isLegal(x, y).ok) legal.push([x, y]);
      if (E.fillsOwnTerritory(g.board, g.size, x, y, 1)) fillB.push([x, y]);
      if (E.fillsOwnTerritory(g.board, g.size, x, y, -1)) fillW.push([x, y]);
    }
  legal.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return {
    board: E.toNested(g.board, g.size),
    turn: g.current,
    move_number: g.move_number,
    passes: g.passes,
    captured_by: { "1": g.captured_by[1], "-1": g.captured_by["-1"] },
    last_move: g.last_move ? [g.last_move[0], g.last_move[1]] : null,
    over: g.over,
    legal: legal,
    fill_black: fillB,
    fill_white: fillW,
    score: g.over ? g.finalScore() : null,
  };
}

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", () => {
  const games = JSON.parse(input || "[]");
  const out = games.map((game) => {
    const g = new E.Game(game.size);
    for (const move of game.moves) {
      if (move === "pass") g.passMove();
      else if (move === "undo") g.undo();
      else g.play(move[0], move[1]);
      if (g.over) break;
    }
    return snapshot(g);
  });
  process.stdout.write(JSON.stringify(out));
});
