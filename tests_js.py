"""Cross-check static/engine.js against engine.py.

The browser build must not drift from the Python reference: same legal moves,
same captures, same board, same score.  Random games are played in Python;
after every ply both engines are compared.

    python tests_js.py
"""

from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from engine import BLACK, EMPTY, WHITE, Game, fills_own_territory

ROOT = Path(__file__).parent
NODE_SCRIPT = ROOT / "tests" / "compare_engine.js"


def replay_in_node(games):
    """games: list of {size, moves:[[x,y] | 'pass' | 'undo' | 'score']}"""
    payload = json.dumps(games)
    out = subprocess.run(
        ["node", str(NODE_SCRIPT)],
        input=payload, capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr or out.stdout)
    return json.loads(out.stdout)


def trace_game(size, rng, plies):
    """Play a random game and return (moves, python_final_snapshot)."""
    g = Game(size=size)
    moves = []
    for _ in range(plies):
        empties = [(x, y) for x in range(size) for y in range(size) if g.board[x][y] == EMPTY]
        legal = []
        for x, y in empties:
            ok, _reason, _cap = g.is_legal(x, y)
            if ok:
                legal.append((x, y))
        roll = rng.random()
        if not legal or roll < 0.06:
            moves.append("pass")
            g.pass_move()
        elif roll < 0.10 and g.move_number:
            moves.append("undo")
            g.undo()
        else:
            x, y = rng.choice(legal)
            moves.append([x, y])
            g.play(x, y)
        if g.over:
            break
    return moves, snapshot(g)


def snapshot(g):
    fills = {BLACK: [], WHITE: []}
    for c in (BLACK, WHITE):
        for x in range(g.size):
            for y in range(g.size):
                if fills_own_territory(g.board, g.size, x, y, c):
                    fills[c].append([x, y])
    return {
        "board": g.board,
        "turn": g.current,
        "move_number": g.move_number,
        "passes": g.passes,
        "captured_by": {str(k): v for k, v in g.captured_by.items()},
        "last_move": list(g.last_move) if g.last_move else None,
        "over": g.over,
        "legal": sorted([[x, y] for x in range(g.size) for y in range(g.size)
                         if g.is_legal(x, y)[0]]),
        "fill_black": fills[BLACK],
        "fill_white": fills[WHITE],
        "score": g.final_score() if g.over else None,
    }


def main():
    rng = random.Random(20260921)
    games = []
    expected = []
    for size in (5, 7, 9, 13):
        for _ in range(6):
            moves, snap = trace_game(size, rng, plies=size * size // 2)
            games.append({"size": size, "moves": moves})
            expected.append(snap)

    results = replay_in_node(games)
    failures = 0
    for i, (exp, got) in enumerate(zip(expected, results)):
        for field in ("board", "turn", "move_number", "passes", "captured_by",
                      "last_move", "over", "legal", "fill_black", "fill_white",
                      "score"):
            if exp[field] != got.get(field):
                failures += 1
                print(f"MISMATCH game {i} field {field}:")
                print("  python:", json.dumps(exp[field])[:400])
                print("  js    :", json.dumps(got.get(field))[:400])
        if exp["score"] and got.get("score"):
            size = games[i]["size"]
            assert exp["score"]["black_total"] + exp["score"]["white_total"] \
                - exp["score"]["komi"] == size ** 2, "python invariant broken"
            assert got["score"]["black_total"] + got["score"]["white_total"] \
                - got["score"]["komi"] == size ** 2, "js invariant broken"
    print(f"{len(games)} random games replayed in node: "
          + ("all identical to engine.py" if not failures else f"{failures} MISMATCHES"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
