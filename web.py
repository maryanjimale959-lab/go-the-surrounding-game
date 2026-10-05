"""Go web server — stdlib only.  Run:  python web.py  [port]

Open http://localhost:8763 (or the LAN URL printed at startup) to play in
any browser: desktop, tablet or phone on the same Wi-Fi.

The page itself needs no server: index.html + static/*.js hold a full port of
this engine, the AI and the MCTS, so the same files can sit on a static host
such as GitHub Pages (https://maryanjimale959-lab.github.io/go-the-surrounding-game/).
app.js probes /api/state at start-up and plays here when the answer is JSON.

API (JSON):
    GET  /api/state            full game state
    POST /api/new   {size, mode, level, human_color}
    POST /api/move  {x, y}        pass ai=false to keep the AI's reply for later
    POST /api/ai_move {}          let the AI play if it is its turn
    POST /api/pass  {}
    POST /api/undo  {}
    POST /api/score {}        end the game and count the board
"""

from __future__ import annotations

import json
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ai import GoAI
from engine import BLACK, Game, WHITE
from mcts import MCTS

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8763
ROOT = Path(__file__).parent
STATIC = ROOT / "static"
MCTS_SECONDS = 3.0

CREATOR = "Maryam J."

# whitelist: only these files are ever read off disk, from these two folders
ASSETS = {
    "index.html": "text/html; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
    "engine.js": "application/javascript; charset=utf-8",
    "ai.js": "application/javascript; charset=utf-8",
    "game_server.js": "application/javascript; charset=utf-8",
}

LOCK = threading.Lock()
S = {
    "game": Game(size=9),
    "ai_color": WHITE,
    "human_color": BLACK,
    "mode": "vs AI",
    "level": "medium",
}


def _apply_ai_settings(mode, level, human_color):
    S["mode"] = mode
    S["level"] = level
    S["human_color"] = human_color
    S["ai_color"] = None if mode == "2 Players" else -human_color


def _ai_mover():
    color = S["ai_color"]
    if color is None:
        return None
    if S["level"] == "master":
        return MCTS(color, seconds=MCTS_SECONDS)
    return GoAI(color, S["level"])


def _ai_turn():
    """Play the AI's move if it is its turn (caller holds LOCK)."""
    g = S["game"]
    mover = _ai_mover()
    if mover is None or g.over or g.current != S["ai_color"]:
        return
    mv = mover.choose_move(g)
    if mv is None:
        g.pass_move()
    else:
        g.play(*mv)


def state_payload():
    g = S["game"]
    d = {
        "size": g.size,
        "board": g.board,
        "turn": g.current,
        "move_number": g.move_number,
        "last_move": g.last_move,
        "passes": g.passes,
        "captured_by": {str(k): v for k, v in g.captured_by.items()},
        "over": g.over,
        "mode": S["mode"],
        "level": S["level"],
        "human_color": S["human_color"],
        "ai_color": S["ai_color"],
        "komi": g.komi,
        "creator": CREATOR,
    }
    if g.over:
        d["result"] = g.final_score()
        d["territory"] = {f"{x},{y}": ("B" if o == BLACK else "W" if o == -BLACK else "dame")
                          for (x, y), o in g.territory_map().items()}
    else:
        # The same count, live: so you can see you are ahead while you play
        # instead of only finding out at the end.
        d["estimate"] = g.score()
    return d


def ok(**extra):
    body = {"ok": True, "state": state_payload()}
    body.update(extra)
    return body


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    # ------------------------------------------------------------ helpers
    def _send(self, code, data, ctype="application/json"):
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _asset(self, rel):
        """Serve one whitelisted file: index.html from the repo root, the rest
        from static/ (the page refers to its scripts as `static/x.js` so the
        same markup works on a GitHub Pages sub-path)."""
        if rel not in ASSETS:
            self._send(404, {"ok": False, "error": "not found"})
            return
        base = ROOT if rel == "index.html" else STATIC
        try:
            self._send(200, (base / rel).read_bytes(), ASSETS[rel])
        except OSError:
            self._send(404, {"ok": False, "error": "not found"})

    # ------------------------------------------------------------ routes
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("", "/"):
            self._asset("index.html")
        elif path == "/index.html":
            self._asset("index.html")
        elif path.startswith("/static/"):
            self._asset(path[len("/static/"):])
        elif path == "/api/state":
            with LOCK:
                # If a previous request died before the AI answered, catch up now.
                if S["ai_color"] is not None and not S["game"].over \
                        and S["game"].current == S["ai_color"] and S["game"].move_number:
                    _ai_turn()
                self._send(200, ok())
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "bad json"})
            return
        path = self.path.split("?")[0]
        with LOCK:
            try:
                self._post(path, body)
            except Exception as exc:  # keep the server alive on errors
                self._send(500, {"ok": False, "error": str(exc)})

    def _post(self, path, body):
        g = S["game"]
        if path == "/api/new":
            size = int(body.get("size", 9))
            mode = body.get("mode", "vs AI")
            level = body.get("level", "medium")
            human = int(body.get("human_color", BLACK))
            if size not in (9, 13, 19) or level not in ("easy", "medium", "hard", "master") \
                    or mode not in ("vs AI", "2 Players") or human not in (BLACK, -BLACK):
                self._send(400, {"ok": False, "error": "invalid settings"})
                return
            S["game"] = Game(size=size)
            _apply_ai_settings(mode, level, human)
            _ai_turn()
            self._send(200, ok())
        elif path == "/api/move":
            x, y = int(body["x"]), int(body["y"])
            if S["ai_color"] is not None and g.current != S["human_color"]:
                self._send(400, {"ok": False, "error": "AI is to move"})
                return
            ok_move, info = g.play(x, y)
            if not ok_move:
                self._send(200, {"ok": False, "error": info, "state": state_payload()})
                return
            if body.get("ai", True):
                _ai_turn()
            self._send(200, ok())
        elif path == "/api/ai_move":
            # Lets the browser show the human's stone for a beat before answering.
            _ai_turn()
            self._send(200, ok())
        elif path == "/api/pass":
            g.pass_move()
            if not g.over and body.get("ai", True):
                _ai_turn()
            self._send(200, ok())
        elif path == "/api/undo":
            steps = 2 if S["ai_color"] is not None else 1
            did = False
            for _ in range(steps):
                if g.undo():
                    did = True
            self._send(200, ok(undid=did))
        elif path == "/api/score":
            g.final_score()
            self._send(200, ok())
        else:
            self._send(404, {"ok": False, "error": "not found"})


def lan_url():
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        ip = "127.0.0.1"
    return ip


def run():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Go is running:  http://localhost:{PORT}")
    print(f"On your phone:  http://{lan_url()}:{PORT}   (same Wi-Fi)")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
