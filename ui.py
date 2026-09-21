"""Go — natural wooden 3D board, interactive course, math-based AI.

Run with:  python main.py
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from ai import GoAI
from engine import BLACK, WHITE, EMPTY, COLOR_NAMES, LETTERS, Game, move_name

# ---------------------------------------------------------------- palette
ROOT_BG = "#E8E2D1"   # warm cream
CARD_BG = "#F7F2E4"   # panel card
CARD_LINE = "#D8CFB6"
INK = "#3A3226"
MUTED = "#8A7F68"
GREEN = "#3E7C59"
RED = "#B5493A"

WOOD = "#DDA95A"
WOOD_GRAIN = "#D49F4E"
WOOD_EDGE_R = "#A87B32"
WOOD_EDGE_L = "#8C6425"
GRID = "#5A4413"
SHADOW = "#B8873C"

TERR_B = "#9DBE7C"
TERR_W = "#8FAFC9"

B_STONE = dict(side="#0A0C0F", top="#22262E", rim="#000000", hi="#6A7383")
W_STONE = dict(side="#C9C2B0", top="#F8F6EF", rim="#ADA48D", hi="#FFFFFF")
GHOST_B = dict(side="#8C8060", top="#8C8060", rim="#7A7050", hi="#8C8060")
GHOST_W = dict(side="#F0E6C8", top="#F0E6C8", rim="#D8CCA8", hi="#F0E6C8")

RULES_TEXT = """\n
══════════════════════  GO — RULES, INSTRUCTIONS & MATH  ══════════════════════

THE GAME
Go is a strategy board game for two players, played on a grid of
19×19, 13×13 or 9×9 lines. One player takes BLACK, the other WHITE.
Black always moves first. White receives compensation points ("komi")
for moving second — in this game komi = 7.5, which prevents draws.

OBJECTIVE
Surround more territory (empty intersections) than your opponent,
plus the stones you keep alive on the board (area scoring).

HOW TO PLAY
• Click an empty intersection to place your stone there.
• Stones never move once placed — they are only removed when captured.
• PASS hands the turn over without playing. Two passes in a row end
  the game and scoring begins.
• UNDO takes back your last move (and the AI's reply).
• FINAL SCORE ends the game immediately and counts the board.
• LEARN GO is a guided, interactive course through every rule below.

RULE 1 — LIBERTIES
A stone's open neighbours (up/down/left/right — never diagonally) are
its liberties. Connected stones of one colour form a group G that
shares all its liberties:
    L(G) = { p empty : p is orthogonally adjacent to some stone of G }

RULE 2 — CAPTURE
    |L(G)| = 0   ⟹   the whole group G is removed from the board.

RULE 3 — NO SUICIDE
A move is legal only if, after the opponent's captured stones are
removed first, your own group still has |L(G)| ≥ 1.

RULE 4 — KO
After a capture you may not immediately recapture to recreate the
previous position. This game enforces the stricter super-ko:
    position(new) ∉ { all positions so far }

RULE 5 — PASSING & END OF GAME
Two consecutive passes end the game. Each empty region touching
exactly one colour becomes that colour's territory; regions touching
both colours (or nothing) are neutral points — dame. Because a game can
end while dame are still open, they are shared out in filling order
(Black first) so that no point of the board is simply thrown away.

SCORING (area / Chinese rules)
    S(Black) = stones(B) + territory(B) + neutral(B)
    S(White) = stones(W) + territory(W) + neutral(W) + 7.5
    S(Black) + S(White) - 7.5 = size²   (every point is accounted for)

WHO WINS — AND THE ONE TRICK ABOUT KOMI
Add the two totals; the larger one wins. White's 7.5 komi is compensation for
letting Black move first, so a Black player who finishes ahead on the board by
7 points or fewer still loses. Captures are never added on top: a stone you
take is simply a stone that stops counting for your opponent.

THE MATHEMATICS THE AI USES
• Influence field — every stone pulls on nearby points with
  geometrically decaying strength (γ = 0.62, d = Manhattan distance):
      I_c(p) = Σ_{s ∈ stones(c)}  γ^d(p,s)
• Move value — each candidate move m is scored by a weighted sum of
  simulated board features:
      v(m) = 14·|captures| + 5·|atari threats| + 3·min(|L|, 4)
           + 4·(groups joined − 1) + 8·(atari escape)
           + 6·(I_c − I_e)(p) − 5·max(0, I_c − I_e)(p)
           − 9·(self-atari) + shape(p)
  shape rewards the 3rd/4th lines and penalises the 1st line.
• Hard mode looks one move ahead for you:
      v*(m) = v(m) − 0.85 · max over your opponent's replies v(m′)
• Difficulty = noise added to v(m) and how many top moves are eligible.

TIPS FOR BEGINNERS
• Corner → side → centre: enclosing territory is cheapest in corners.
• Keep your groups connected; cut your opponent's groups apart.
• A group with two separate "eyes" can never be captured — make eyes!
• Never play on the first line in the opening; it earns almost nothing.
"""


# ================================================================ board view
class BoardView(tk.Canvas):
    """Isometric (3D-looking) wooden Go board rendered on a Canvas."""

    MARGIN = 0.85  # grid units of wood beyond the outer lines

    def __init__(self, master, size, width_px=620, **kw):
        super().__init__(master, bg=ROOT_BG, highlightthickness=0, **kw)
        self.size = size
        m = self.MARGIN
        self.a = width_px / (2 * (size - 1 + 2 * m))       # half-width per grid step
        self.b = self.a * 0.55                              # vertical squash
        self.rx = self.a * 0.52                             # stone radius (x)
        self.ry = self.rx * 0.60                            # stone radius (y)
        self.sh = self.rx * 0.34                            # stone thickness
        self.thick = max(10, self.a * 0.8)                  # board thickness
        pad = 30
        self.pad_l = 26                                     # label space
        W = int(2 * (size - 1 + 2 * m) * self.a) + 2 * self.pad_l
        H = int((size - 1 + 2 * m) * 2 * self.b) + int(self.thick) + 2 * pad
        self.configure(width=W, height=H)
        self.ox = W / 2
        self.oy = pad + 2 * m * self.b

    def P(self, x, y):
        return self.ox + (x - y) * self.a, self.oy + (x + y) * self.b

    def unproject(self, px, py):
        u = (px - self.ox) / self.a
        v = (py - self.oy) / self.b
        x = round((u + v) / 2)
        y = round((v - u) / 2)
        if not (0 <= x < self.size and 0 <= y < self.size):
            return None
        cx, cy = self.P(x, y)
        if ((px - cx) / self.a) ** 2 + ((py - cy) / self.b) ** 2 > 0.8:
            return None
        return x, y

    # ------------------------------------------------------------- drawing
    def draw(self, board, last=None, hover=None, markers=None, territory=None):
        self.delete("all")
        size = self.size
        m = self.MARGIN
        hi = size - 1 + m
        lo = -m

        # wood top face + grain
        A, B, C, D = self.P(lo, lo), self.P(hi, lo), self.P(hi, hi), self.P(lo, hi)
        self.create_polygon(*A, *B, *C, *D, fill=WOOD, outline="")
        t = lo
        k = 0
        while t <= hi:
            c = WOOD_GRAIN if k % 2 == 0 else "#D9A552"
            p1, p2 = self.P(t, lo), self.P(t, hi)
            self.create_line(p1[0], p1[1], p2[0], p2[1], fill=c, width=max(2, int(self.a * 0.18)))
            t += 0.55
            k += 1
        # side faces (board thickness)
        self.create_polygon(*B, *C, C[0], C[1] + self.thick, B[0], B[1] + self.thick,
                            fill=WOOD_EDGE_R, outline="")
        self.create_polygon(*C, *D, D[0], D[1] + self.thick, C[0], C[1] + self.thick,
                            fill=WOOD_EDGE_L, outline="")

        # grid
        g0, g1 = self.P(0, 0), self.P(size - 1, size - 1)
        for i in range(size):
            w = 2 if i in (0, size - 1) else 1
            p1, p2 = self.P(i, 0), self.P(i, size - 1)
            self.create_line(*p1, *p2, fill=GRID, width=w)
            p1, p2 = self.P(0, i), self.P(size - 1, i)
            self.create_line(*p1, *p2, fill=GRID, width=w)

        # star points
        for sx, sy in self.star_points(size):
            px, py = self.P(sx, sy)
            r = max(2, self.a * 0.11)
            self.create_oval(px - r, py - r * 0.7, px + r, py + r * 0.7, fill=GRID, outline=GRID)

        # territory shading
        if territory:
            for (x, y), owner in territory.items():
                if owner not in (BLACK, WHITE):
                    continue
                c = TERR_B if owner == BLACK else TERR_W
                pts = self.P(x - 0.34, y) + self.P(x, y - 0.34) + self.P(x + 0.34, y) + self.P(x, y + 0.34)
                self.create_polygon(*pts, fill=c, outline="")

        # coordinates
        font = ("Georgia", max(8, int(self.a * 0.42)))
        for i in range(size):
            px, py = self.P(i, lo - 0.45)
            self.create_text(px, py, text=LETTERS[i], fill=MUTED, font=font)
            px, py = self.P(lo - 0.45, i)
            self.create_text(px, py, text=str(i + 1), fill=MUTED, font=font)

        # stones, far to near
        stones = [(x, y) for x in range(size) for y in range(size) if board[x][y] != EMPTY]
        for x, y in sorted(stones, key=lambda p: p[0] + p[1]):
            self._stone(x, y, board[x][y])

        # last-move marker
        if last and board[last[0]][last[1]] != EMPTY:
            px, py = self.P(*last)
            r = max(2.5, self.rx * 0.28)
            col = RED if board[last[0]][last[1]] == WHITE else "#F2E9E4"
            self.create_oval(px - r, py - r * 0.8, px + r, py + r * 0.8, outline=col, width=2)

        # markers (learn mode)
        for mx, my, kind in markers or []:
            self._marker(mx, my, kind)

        # hover ghost
        if hover:
            hx, hy, hc = hover
            if board[hx][hy] == EMPTY:
                self.draw_ghost(hx, hy, hc)

    def draw_ghost(self, x, y, color):
        self._stone(x, y, color, ghost=True, tag="ghost")

    def clear_ghost(self):
        self.delete("ghost")

    def _stone(self, x, y, color, ghost=False, tag=None):
        px, py = self.P(x, y)
        rx, ry, sh = self.rx, self.ry, self.sh
        pal = (GHOST_B if ghost else B_STONE) if color == BLACK else (GHOST_W if ghost else W_STONE)
        kw = {"tags": (tag,)} if tag else {}
        if not ghost:
            self.create_oval(px - rx + rx * 0.12, py - ry + sh + ry * 0.45,
                             px + rx + rx * 0.12, py + ry + sh + ry * 0.45,
                             fill=SHADOW, outline="", **kw)
        self.create_oval(px - rx, py - ry + sh, px + rx, py + ry + sh, fill=pal["side"], outline="", **kw)
        self.create_oval(px - rx, py - ry, px + rx, py + ry, fill=pal["top"], outline=pal["rim"], **kw)
        hr, hrr = rx * 0.34, ry * 0.34
        self.create_oval(px - rx * 0.34 - hr, py - ry * 0.42 - hrr,
                         px - rx * 0.34 + hr, py - ry * 0.42 + hrr, fill=pal["hi"], outline="", **kw)

    def _marker(self, x, y, kind):
        px, py = self.P(x, y)
        r = max(3, self.a * 0.16)
        if kind == "lib":
            self.create_oval(px - r, py - r * 0.75, px + r, py + r * 0.75,
                             fill="#5FA46E", outline="#2E5B3F")
        elif kind == "danger":
            self.create_oval(px - r, py - r * 0.75, px + r, py + r * 0.75,
                             fill="#E0484D", outline="#7E1F22")
        elif kind == "x":
            w = max(2, self.a * 0.1)
            self.create_line(px - r, py - r * 0.75, px + r, py + r * 0.75, fill=RED, width=w)
            self.create_line(px - r, py + r * 0.75, px + r, py - r * 0.75, fill=RED, width=w)
        elif isinstance(kind, str) and kind.startswith("t:"):
            self.create_text(px, py, text=kind[2:], fill="#222", font=("Georgia", int(self.a * 0.6), "bold"))

    @staticmethod
    def star_points(size):
        if size == 9:
            return [(2, 2), (6, 2), (2, 6), (6, 6), (4, 4)]
        if size == 13:
            e = [3, 6, 9]
            return [(x, y) for x in e for y in e]
        if size == 19:
            e = [3, 9, 15]
            return [(x, y) for x in e for y in e]
        return []


# ================================================================ main app
class GoApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Go — the Surrounding Game")
        root.configure(bg=ROOT_BG)
        root.resizable(False, False)

        self.canvas_frame = tk.Frame(root, bg=ROOT_BG)
        self.canvas_frame.pack(side="left", padx=(14, 0), pady=14)
        self.panel = tk.Frame(root, bg=CARD_BG, highlightbackground=CARD_LINE,
                              highlightthickness=1, width=270)
        self.panel.pack(side="left", fill="y", padx=(10, 14), pady=14)
        self.panel.pack_propagate(False)

        self.view = None
        self.game = None
        self.ai = None
        self.busy = False
        self.human_color = BLACK

        self.mode = tk.StringVar(value="vs AI")
        self.level = tk.StringVar(value="Medium")
        self.color_menu = tk.StringVar(value="Black")
        self.size_menu = tk.StringVar(value="9×9")

        self._build_panel()
        self.new_game()

    # ------------------------------------------------------------ panel
    def _build_panel(self):
        p = self.panel

        def label(text, **kw):
            return tk.Label(p, text=text, bg=CARD_BG, fg=kw.pop("fg", INK), **kw)

        label("G O", font=("Georgia", 26, "bold")).pack(pady=(8, 0))
        label("the surrounding game", font=("Georgia", 10, "italic"), fg=MUTED).pack(pady=(0, 2))
        label("created by Maryam J.", font=("Segoe UI", 9), fg=GREEN).pack(pady=(0, 12))

        def section(text):
            label(text, font=("Segoe UI", 9, "bold"), fg=MUTED).pack(anchor="w", pady=(8, 1))

        def option(values, var, command=None):
            om = tk.OptionMenu(p, var, *values, command=command)
            om.configure(bg="#EFE8D4", fg=INK, activebackground="#E2D8BC", relief="flat",
                         font=("Segoe UI", 10), highlightthickness=0, width=16, anchor="w")
            om["menu"].configure(bg="#F7F2E4", fg=INK, activebackground="#E2D8BC",
                                 font=("Segoe UI", 10))
            om.pack(fill="x", pady=1)
            return om

        section("MODE")
        seg = tk.Frame(p, bg=CARD_BG)
        seg.pack(fill="x")
        self.rb_ai = tk.Radiobutton(seg, text="vs AI", variable=self.mode, value="vs AI",
                                    command=self._mode_changed, bg=CARD_BG, fg=INK,
                                    selectcolor=GREEN, activebackground=CARD_BG, font=("Segoe UI", 10))
        self.rb_2p = tk.Radiobutton(seg, text="2 Players", variable=self.mode, value="2 Players",
                                    command=self._mode_changed, bg=CARD_BG, fg=INK,
                                    selectcolor=GREEN, activebackground=CARD_BG, font=("Segoe UI", 10))
        self.rb_ai.pack(side="left", padx=(0, 8))
        self.rb_2p.pack(side="left")

        section("AI LEVEL")
        self.opt_level = option(["Easy", "Medium", "Hard"], self.level)
        section("YOU PLAY")
        self.opt_color = option(["Black", "White"], self.color_menu)
        section("BOARD")
        option(["9×9", "13×13", "19×19"], self.size_menu)

        tk.Frame(p, bg=CARD_LINE, height=1).pack(fill="x", pady=10)

        self._button("New Game", self.new_game, GREEN, "#FFFFFF")
        row = tk.Frame(p, bg=CARD_BG)
        row.pack(fill="x", pady=3)
        b = self._button_in(row, "Pass", self.on_pass)
        b.pack(side="left", expand=True, fill="x", padx=(0, 3))
        b = self._button_in(row, "Undo", self.on_undo)
        b.pack(side="left", expand=True, fill="x", padx=3)
        b = self._button_in(row, "Score", self.on_score_now)
        b.pack(side="left", expand=True, fill="x", padx=(3, 0))
        self._button("Learn Go — guided course", self.open_learn, "#7A9E5F", "#FFFFFF")
        self._button("Rules, Instructions & Math", self.show_rules, "#EFE8D4", INK)

        tk.Frame(p, bg=CARD_LINE, height=1).pack(fill="x", pady=10)

        self.turn_label = label("", font=("Segoe UI", 13, "bold"))
        self.turn_label.pack(anchor="w")
        self.info_label = label("", font=("Segoe UI", 10), fg=MUTED, justify="left")
        self.info_label.pack(anchor="w", pady=(2, 0))
        self.msg_label = label("", font=("Segoe UI", 10), fg=RED, wraplength=240, justify="left")
        self.msg_label.pack(anchor="w", pady=(4, 0))

        label("Black moves first · White is given +7.5 komi\ntwo passes end the game",
              font=("Segoe UI", 9), fg=MUTED, justify="left").pack(side="bottom", pady=6)

    def _button(self, text, cmd, bg, fg):
        b = tk.Button(self.panel, text=text, command=cmd, bg=bg, fg=fg, relief="flat",
                      activebackground=bg, activeforeground=fg, font=("Segoe UI", 10, "bold"),
                      padx=10, pady=6, cursor="hand2")
        b.pack(fill="x", pady=3)
        return b

    def _button_in(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg="#EFE8D4", fg=INK, relief="flat",
                         activebackground="#E2D8BC", activeforeground=INK,
                         font=("Segoe UI", 10, "bold"), padx=8, pady=5, cursor="hand2")

    def _mode_changed(self):
        ai = self.mode.get() == "vs AI"
        state = "normal" if ai else "disabled"
        self.opt_level.configure(state=state)
        self.opt_color.configure(state=state)

    # ------------------------------------------------------------ game flow
    def new_game(self):
        size = int(self.size_menu.get().split("×")[0])
        if self.view is not None:
            self.view.destroy()
        width = {9: 600, 13: 640, 19: 680}[size]
        self.view = BoardView(self.canvas_frame, size, width_px=width)
        self.view.pack()
        self.view.bind("<Button-1>", self.on_click)
        self.view.bind("<Motion>", self.on_motion)
        self.view.bind("<Leave>", lambda e: self.view.clear_ghost())

        self.game = Game(size=size)
        two_players = self.mode.get() == "2 Players"
        self.human_color = BLACK if self.color_menu.get() == "Black" else WHITE
        self.ai = None if two_players else GoAI(-self.human_color, self.level.get().lower())
        self.busy = False
        self.set_message("")
        self.redraw()
        self.update_status()
        if self.ai and self.game.current != self.human_color:
            self.schedule_ai()

    def on_pass(self):
        if self.busy or self.game.over:
            return
        self.game.pass_move()
        self.redraw()
        self.update_status()
        if self.game.over:
            self.show_score("Both players passed — game over.")
        elif self.ai:
            self.schedule_ai()

    def on_undo(self):
        if self.busy:
            return
        steps = 2 if (self.ai and self.game.move_number % 2 == 0) else 1
        did = False
        for _ in range(steps):
            if self.game.undo():
                did = True
        self.redraw()
        self.update_status()
        if not did:
            self.set_message("Nothing to undo.")

    def on_score_now(self):
        if self.busy:
            return
        self.show_score("Score on request:")

    def try_move(self, x, y):
        ok, info = self.game.play(x, y)
        if not ok:
            self.set_message(f"Illegal move — {info}.")
            return False
        self.set_message("")
        self.redraw()
        self.update_status()
        if self.ai and not self.game.over:
            self.schedule_ai()
        return True

    def schedule_ai(self):
        self.busy = True
        self.update_status()
        self.root.after(80, self.ai_move)

    def ai_move(self):
        move = self.ai.choose_move(self.game)
        self.busy = False
        if move is None:
            self.game.pass_move()
            self.set_message("AI passes.")
        else:
            self.game.play(*move)
        self.redraw()
        self.update_status()
        if self.game.over:
            self.show_score("Both players passed — game over.")

    # ------------------------------------------------------------ input
    def human_can_play(self):
        if self.busy or self.game.over:
            return False
        return self.ai is None or self.game.current == self.human_color

    def on_click(self, event):
        if not self.human_can_play():
            return
        pos = self.view.unproject(event.x, event.y)
        if pos:
            self.try_move(*pos)

    def on_motion(self, event):
        self.view.clear_ghost()
        if not self.human_can_play():
            return
        pos = self.view.unproject(event.x, event.y)
        if pos and self.game.board[pos[0]][pos[1]] == EMPTY:
            ok, _, _ = self.game.is_legal(*pos)
            if ok:
                self.view.draw_ghost(pos[0], pos[1], self.game.current)

    # ------------------------------------------------------------ render
    def redraw(self, hover=None):
        g = self.game
        territory = None
        if g.over:
            territory = g.territory_map()
        self.view.draw(g.board, last=g.last_move, hover=hover, territory=territory)

    # ------------------------------------------------------------ status
    def set_message(self, text):
        self.msg_label.configure(text=text)

    def update_status(self):
        g = self.game
        if g.over:
            res = g.final_score()
            if res["winner"] == "Draw":
                text = "Game over — draw"
            else:
                w = BLACK if res["winner"] == "Black" else WHITE
                name = self.name_of(w)
                text = f"Game over — {name} {'win' if name == 'You' else 'wins'} by {res['margin']:.1f}"
            self.turn_label.configure(text=text, fg=GREEN)
        else:
            who = COLOR_NAMES[g.current]
            dot = "●" if g.current == BLACK else "○"
            if self.ai and g.current != self.human_color:
                text = f"{dot} {who} (AI) is thinking…"
            elif self.ai:
                text = f"{dot} {who} (you) to move"
            else:
                text = f"{dot} {who} to move"
            self.turn_label.configure(text=text, fg=INK)
        cap = (f"Prisoners taken — Black: {g.captured_by[BLACK]}   "
               f"White: {g.captured_by[WHITE]}")
        lines = [cap]
        if g.move_number:
            lines.append(f"Last move: {move_name(g.size, *g.last_move)}"
                         if g.last_move else "Last move: pass")
        lines.append(f"Moves played: {g.move_number}")
        lines.append(f"Komi +{g.komi} to White, so Black must lead the board by more than {g.komi}")
        self.info_label.configure(text="\n".join(lines))

    # ------------------------------------------------------------ dialogs
    def show_rules(self):
        win = tk.Toplevel(self.root)
        win.title("Go — Rules, Instructions & Math")
        win.geometry("660x640")
        win.configure(bg=CARD_BG)
        text = tk.Text(win, bg="#FBF8EF", fg=INK, wrap="word", padx=20, pady=16,
                       font=("Consolas", 10), relief="flat")
        bar = ttk.Scrollbar(win, command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.insert("1.0", RULES_TEXT)
        text.configure(state="disabled")

    def name_of(self, color):
        """Who is behind a colour, so the result never reads as a bare 'White wins'."""
        if self.ai is None:
            return "Black" if color == BLACK else "White"
        return "You" if color == self.human_color else "The AI"

    def show_score(self, headline):
        res = self.game.final_score()
        lines = [
            headline,
            "",
            f"● Black ({self.name_of(BLACK)}):  {res['black_stones']} stones + {res['black_territory']} area "
            f"+ {res['black_dame']} neutral = {res['black_total']:.1f}",
            f"○ White ({self.name_of(WHITE)}):  {res['white_stones']} stones + {res['white_territory']} area "
            f"+ {res['white_dame']} neutral + {res['komi']} komi = {res['white_total']:.1f}",
            f"Check: {res['black_total']:.1f} + {res['white_total'] - res['komi']:.1f} = "
            f"{self.game.size ** 2} points on the board",
            "",
        ]
        winner = res["winner"]
        if winner == "Draw":
            lines.append("Result: a perfect draw.")
        else:
            w = BLACK if winner == "Black" else WHITE
            name = self.name_of(w)
            lines.append(f"{name} {'win' if name == 'You' else 'wins'} by {res['margin']:.1f} points")
            board_lead = res["black_total"] - (res["white_total"] - res["komi"])
            if winner == "White" and board_lead > 0:
                lines.append(
                    f"{self.name_of(BLACK)} surrounded {board_lead:.1f} more points, but White's "
                    f"{res['komi']} komi for moving second is added on top and decides the game."
                )
        messagebox.showinfo("Final score", "\n".join(lines))

    def open_learn(self):
        LearnDialog(self.root)


# ================================================================ learn mode
LESSONS = [
    dict(
        title="1 · The board and the stones",
        text="Go is played on the intersections of the lines, not inside the squares.\n\n"
             "Black and White alternate, and Black always moves first. Once placed, a "
             "stone never moves — it can only be captured.\n\n"
             "The goal: surround more empty territory than your opponent.\n\n"
             "Try it: click any empty intersection to place a black stone.",
        setup=[], current=BLACK, markers=[], free=True,
        done="Good! That stone sits on an intersection and will stay there for now.",
    ),
    dict(
        title="2 · Liberties — L(G)",
        text="Every stone breathes through its orthogonal neighbours — never diagonally. "
             "Those open points are its liberties:\n\n"
             "    L(G) = { p empty : p adjacent to G }\n\n"
             "The green dots are this black stone's 4 liberties. Connected stones form one "
             "group that shares all its liberties.",
        setup=[(4, 4, BLACK)], current=WHITE, markers=[(3, 4, "lib"), (5, 4, "lib"),
                                                       (4, 3, "lib"), (4, 5, "lib")],
    ),
    dict(
        title="3 · Capture — |L(G)| = 0",
        text="When the last liberty of a group is filled, the whole group is removed:\n\n"
             "    |L(G)| = 0   ⟹   G leaves the board\n\n"
             "You play White. The black stone has exactly one liberty left (green dot). "
             "Click it and watch the capture.",
        setup=[(4, 4, BLACK), (3, 4, WHITE), (5, 4, WHITE), (4, 3, WHITE)],
        current=WHITE, markers=[(4, 5, "lib")],
        asks=[dict(point=(4, 5), expect="play")],
        done="Captured! |L| became 0, so the black stone is removed and counts as a "
             "prisoner.",
    ),
    dict(
        title="4 · No suicide",
        text="You may not place a stone that leaves your own group with zero liberties — "
             "unless the move captures first and opens them.\n\n"
             "You play Black. The red ✕ at the corner has no liberties for you — "
             "click it and see what the rules engine says.",
        setup=[(1, 0, WHITE), (0, 1, WHITE)], current=BLACK, markers=[(0, 0, "x")],
        asks=[dict(point=(0, 0), expect="illegal")],
        done="Exactly — the engine rejected the suicide. You must play elsewhere.",
    ),
    dict(
        title="5 · Ko — no instant recapture",
        text="After a capture, recreating the previous position is forbidden — the ko rule "
             "(this game uses the stricter super-ko: no position may ever repeat).\n\n"
             "You play Black: first capture the lone white stone (green dot). "
             "Then, as White, try the instant recapture — the rules will block it.",
        setup=[(3, 2, BLACK), (2, 3, BLACK), (3, 4, BLACK), (3, 3, WHITE),
               (4, 2, WHITE), (4, 4, WHITE), (5, 3, WHITE)],
        current=BLACK, markers=[(4, 3, "lib")],
        asks=[dict(point=(4, 3), expect="play", hint="Black captures at the green dot."),
              dict(point=(3, 3), expect="illegal", hint="Now White tries the ko square — "
              "it recreates the previous position.")],
        markers_after={1: [(3, 3, "lib")]},
        done="The recapture recreates an earlier position, so it is illegal. White must "
             "play elsewhere first — that is the ko fight.",
    ),
    dict(
        title="6 · Territory and scoring",
        text="Two passes end the game. An empty region touching exactly one colour becomes "
             "territory (shaded here); regions touching both are dame (neutral), shared out "
             "in filling order.\n\n"
             "    S(B) = stones(B) + territory(B) + neutral(B)\n"
             "    S(W) = stones(W) + territory(W) + neutral(W) + 7.5 (komi)\n\n"
             "    S(B) + S(W) - 7.5 = size²\n\n"
             "Here Black's wall owns the left, White's wall the right, and the middle "
             "column is dame. Remember the komi: Black has to be ahead by more than 7.5 "
             "to actually win.",
        setup=[(3, y, BLACK) for y in range(9)] + [(5, y, WHITE) for y in range(9)],
        current=BLACK, markers=[], territory=True,
    ),
    dict(
        title="7 · The math the AI plays with",
        text="The opponent you can play is built from equations:\n\n"
             "Influence — each stone radiates power that decays geometrically with "
             "Manhattan distance d (γ = 0.62):\n"
             "    I_c(p) = Σ γ^d(p,s)\n\n"
             "Move value — captures, threats, liberties, connections:\n"
             "    v(m) = 14·|cap| + 5·atari + 3·min(|L|,4)\n"
             "         + 4·(links−1) + 8·escape + 6·ΔI\n"
             "         − 5·own-territory waste − 9·self-atari + shape\n\n"
             "Hard mode also answers ahead:\n"
             "    v*(m) = v(m) − 0.85·max v(m′) over opponent replies\n\n"
             "Difficulty = noise on v(m) + how many top moves are eligible.\n\n"
             "You know the rules and the math — go play!",
        setup=[(4, 4, BLACK), (2, 2, WHITE), (6, 6, BLACK), (6, 2, WHITE), (2, 6, BLACK)],
        current=WHITE, markers=[],
    ),
]


class LearnDialog:
    def __init__(self, root):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.title("Learn Go — interactive course")
        self.win.configure(bg=ROOT_BG)
        self.idx = 0

        self.view = None
        self.game = None

        card = tk.Frame(self.win, bg=CARD_BG, highlightbackground=CARD_LINE, highlightthickness=1)
        card.pack(side="right", fill="y", padx=(0, 12), pady=12)
        self.view_frame = tk.Frame(self.win, bg=ROOT_BG)
        self.view_frame.pack(side="left", padx=12, pady=12)

        w = 300
        tk.Label(card, text="Learn Go", bg=CARD_BG, fg=INK, font=("Georgia", 20, "bold")).pack(pady=(14, 0))
        self.count_label = tk.Label(card, text="", bg=CARD_BG, fg=MUTED, font=("Segoe UI", 9))
        self.count_label.pack()
        self.title_label = tk.Label(card, text="", bg=CARD_BG, fg=GREEN, font=("Georgia", 13, "bold"),
                                    wraplength=w - 30, justify="left", anchor="w")
        self.title_label.pack(fill="x", padx=15, pady=(10, 2))
        self.body = tk.Label(card, text="", bg=CARD_BG, fg=INK, font=("Segoe UI", 10),
                             wraplength=w - 24, justify="left", anchor="w")
        self.body.pack(fill="x", padx=12)
        self.status = tk.Label(card, text="", bg=CARD_BG, fg=GREEN, font=("Segoe UI", 10, "bold"),
                               wraplength=w - 24, justify="left")
        self.status.pack(fill="x", padx=12, pady=(8, 0))

        row = tk.Frame(card, bg=CARD_BG)
        row.pack(side="bottom", fill="x", padx=12, pady=12)
        tk.Button(row, text="← Back", command=self.back, bg="#EFE8D4", fg=INK, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10, pady=5, cursor="hand2").pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(row, text="Next →", command=self.next, bg=GREEN, fg="#FFFFFF", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10, pady=5, cursor="hand2").pack(side="left", expand=True, fill="x", padx=4)
        tk.Button(row, text="Done", command=self.win.destroy, bg="#EFE8D4", fg=INK, relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10, pady=5, cursor="hand2").pack(side="left", expand=True, fill="x", padx=(4, 0))

        self.load(0)
        self.win.bind("<Escape>", lambda e: self.win.destroy())

    # ------------------------------------------------------------ lessons
    def load(self, idx):
        self.idx = idx
        lesson = LESSONS[idx]
        self.ask_step = 0
        self.solved = not lesson.get("asks") and not lesson.get("free")

        size = 9
        self.game = Game(size=size)
        for x, y, c in lesson["setup"]:
            self.game.board[x][y] = c
        self.game.positions = {self.game._key(self.game.board)}
        self.game.current = lesson["current"]

        if self.view is not None:
            self.view.destroy()
        self.view = BoardView(self.view_frame, size, width_px=520)
        self.view.pack()
        self.view.bind("<Button-1>", self.on_click)
        self.view.bind("<Motion>", self.on_motion)
        self.view.bind("<Leave>", lambda e: self.view.clear_ghost())

        self.count_label.configure(text=f"Lesson {idx + 1} of {len(LESSONS)}")
        self.title_label.configure(text=lesson["title"])
        self.body.configure(text=lesson["text"])
        self.status.configure(text=lesson.get("hint", ""), fg=MUTED)
        self.render()

    def markers(self):
        lesson = LESSONS[self.idx]
        after = lesson.get("markers_after", {}).get(self.ask_step)
        return after if after is not None else lesson.get("markers", [])

    def render(self, hover=None):
        lesson = LESSONS[self.idx]
        territory = None
        if lesson.get("territory"):
            territory = self.game.territory_map()
        self.view.draw(self.game.board, last=self.game.last_move, hover=hover,
                       markers=self.markers(), territory=territory)

    def on_motion(self, event):
        self.view.clear_ghost()
        pos = self.view.unproject(event.x, event.y)
        if pos and self.game.board[pos[0]][pos[1]] == EMPTY:
            self.view.draw_ghost(pos[0], pos[1], self.game.current)

    def on_click(self, event):
        lesson = LESSONS[self.idx]
        pos = self.view.unproject(event.x, event.y)
        if pos is None:
            return
        x, y = pos

        if lesson.get("free"):
            ok, info = self.game.play(x, y)
            if ok:
                self.solved = True
                self.status.configure(text=lesson["done"], fg=GREEN)
                self.render()
            else:
                self.status.configure(text=f"Illegal — {info}.", fg=RED)
                self.render()
            return

        asks = lesson.get("asks")
        if not asks:
            self.status.configure(text="Read the lesson, then press Next →", fg=MUTED)
            return
        if self.ask_step >= len(asks):
            return

        ask = asks[self.ask_step]
        if (x, y) != tuple(ask["point"]):
            self.status.configure(text=ask.get("hint", lesson.get("hint", "Try the marked point.")),
                                  fg=MUTED)
            return

        ok, info, _c = self.game.is_legal(x, y)
        if ask["expect"] == "illegal":
            self.status.configure(text=f"Illegal — {info}.", fg=RED)
            self.ask_step += 1
            if self.ask_step >= len(asks):
                self.solved = True
                self.status.configure(text=lesson["done"], fg=GREEN)
            return
        if not ok:
            self.status.configure(text=f"Illegal — {info}.", fg=RED)
            return
        self.game.play(x, y)
        self.ask_step += 1
        if self.ask_step >= len(asks):
            self.solved = True
            self.status.configure(text=lesson["done"], fg=GREEN)
        else:
            nxt = asks[self.ask_step]
            self.status.configure(text=nxt.get("hint", "Keep going…"), fg=MUTED)
        self.render()

    def next(self):
        if self.idx + 1 < len(LESSONS):
            self.load(self.idx + 1)
        else:
            self.win.destroy()

    def back(self):
        if self.idx > 0:
            self.load(self.idx - 1)


# ================================================================ entry point
def run():
    root = tk.Tk()
    GoApp(root)
    root.mainloop()
