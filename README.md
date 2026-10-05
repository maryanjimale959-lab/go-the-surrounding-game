# Go — the Surrounding Game

**Created by Maryam J.**

A complete implementation of the ancient board game **Go** (Baduk / Weiqi),
written from scratch with no third-party dependencies: the full rules, the
mathematics behind scoring and the AI, an interactive **Learn Go** course,
and three front-ends — a **browser game that needs no server at all**, a 3D
isometric **Tkinter desktop app**, and a **local web app** for the same Wi-Fi.

**Play it now, nothing to install:**
<https://maryanjimale959-lab.github.io/go-the-surrounding-game/>

```
# online: open the link above (the engine and AI run inside the page)
python web.py      # → http://localhost:8763   (same page, served by Python)
python main.py     # → desktop window with a 3D isometric wooden board
```

---

## Contents

1. [What is inside](#what-is-inside)
2. [Install and run](#install-and-run)
3. [How it works (architecture)](#how-it-works-architecture)
4. [The complete rules of Go](#the-complete-rules-of-go)
5. [The mathematics](#the-mathematics)
6. [The four AI levels](#the-four-ai-levels)
7. [Controls](#controls)
8. [Tests](#tests)
9. [Project layout](#project-layout)

---

## What is inside

| Feature | Where |
| --- | --- |
| Rules engine: groups, liberties, capture, suicide, super-ko, area scoring | `engine.py` |
| The same engine, ported to JavaScript so the page can play with no server | `static/engine.js` |
| Heuristic AI (Easy / Medium / Hard) built on influence fields and an evaluation function | `ai.py` → `static/ai.js` |
| MCTS "Master" AI (PUCT tree search + random playouts) | `mcts.py` → `static/ai.js` |
| Web server (stdlib HTTP + JSON API) | `web.py` |
| The game server re-implemented inside the browser (same JSON, same routes) | `static/game_server.js` |
| Web front-end: canvas board, animations, sound, dialogs | `index.html`, `static/` |
| Desktop app: isometric 3D board, sidebar, Learn course | `main.py`, `ui.py` |
| Rule + AI tests, self-play, and a Python↔JavaScript engine comparison | `tests.py`, `tests/`, `tests_js.py` |

No `pip install` is required for anything. Python 3.8+ is enough; Tkinter is
only needed for the desktop window (on Debian/Ubuntu: `sudo apt install python3-tk`).
The web game needs neither: it is plain HTML + JavaScript, so it runs on a
phone, a tablet, or a laptop that has no Python on it at all.

## Install and run

### Play it (no install)

Open <https://maryanjimale959-lab.github.io/go-the-surrounding-game/>. GitHub
Pages is a static host — it cannot run Python — so `game_server.js` takes
`web.py`'s job and the rules engine, the evaluation AI and the MCTS all run in
the tab. Every device gets its own board, and it keeps working on a phone on
mobile data.

### Run it from the source

```bash
git clone <this-repo-url>
cd go-the-surrounding-game

# the web app (recommended — it looks the best and works on any device)
python web.py                 # default port 8763
python web.py 9000            # or pick a port
```

The server prints two addresses:

```
Go is running:  http://localhost:8763
On your phone:  http://192.168.x.x:8763   (same Wi-Fi)
```

Open either one. The phone URL works because the server binds to `0.0.0.0`,
so any device on the same network can join — and there the board lives on the
server, so two people can pass the phone back and forth and both see the same
game.

`app.js` decides which backend to use by itself: it asks `api/state` at start-up
and takes the JSON answer (Python) or falls back to the in-page engine (Pages).
One probe, two deployments, identical markup.

```bash
python main.py                # desktop app instead
```

## How it works (architecture)

The project is layered so that the rules exist exactly once:

```
   ┌─────────────────────────┐  ┌─────────────────────┐  ┌─────────────────┐
   │ GitHub Pages, no server │  │ web.py  (HTTP+JSON) │  │ ui.py / main.py │
   │ engine/ai/MCTS run here │  │ static/ canvas board│  │ Tkinter window  │
   └────────────┬────────────┘  └──────────┬──────────┘  └────────┬────────┘
                ▼                          ▼                      ▼
     static/engine.js ◄── identical rules ──►  engine.py   Game(size, komi)
     static/ai.js     ◄──  identical math  ──►  ai.py / mcts.py
                (the rules exist exactly once per language — tests_js.py proves
                 that the Python and JavaScript copies can never quietly differ)
```

**A move, step by step (web app):**

1. You click an intersection. `app.js` converts the pixel position back into
   grid coordinates (`x`, `y`) and asks for `api/move`.
2. `web.py` holds a single shared `Game` object behind a `threading.Lock`, so
   two browsers can never corrupt the same board. Opened from Pages there is no
   server, and `game_server.js` answers the same route from the same fields.
3. `Game.play(x, y)` asks `is_legal()` — occupied? suicide? does the resulting
   position repeat an earlier one (super-ko)? If anything fails, the reason
   string travels back to the browser and appears as a toast.
4. If the move is legal, `simulate_move()` places the stone on a **copy** of
   the board, resolves captures (`|L(G)| = 0`), and only then is the copy
   committed. The previous position is pushed onto a history stack, which is
   what makes Undo work.
5. Because you are playing Black and the AI is White, `_ai_turn()` runs the
   selected engine (`GoAI` or `MCTS`) inside the same request and appends the
   AI's move. The JSON response therefore contains **both** stones, so the
   board never shows a half-finished turn. (`ai:false` holds the reply back for
   one beat, which is what lets you see your own stone land first.)
6. The front-end diffs the returned board against the previous one, pops the
   new stones in with a 140 ms `easeOutBack` animation, and plays a short
   WebAudio "click" — the sound of a stone hitting wood.

**Coordinates.** The board is `board[x][y]` where `x` is the file (letter,
`A..T` skipping `I` by Go convention) and `y` is the rank counted from the
top, so `engine.move_name(19, 3, 3)` returns `"D4"`. Both boards print `1`
on the top row and `A` on the left column.

**Three front-ends, one brain.** The Tkinter app calls `Game` and `GoAI`
directly in-process — no HTTP, no JSON. The Python server does the same over
JSON. The Pages build calls `static/engine.js`, which is the same rules
ported line for line: groups, the capture-before-suicide order, super-ko keys,
the dame split, the identical score dictionary. `python tests_js.py` replays
24 random games through both engines and diffs every field, so the two can
never quietly disagree about who captured what.

**Search that does not freeze the page.** `ai.js` and the MCTS are `async` and
`await sleep(0)` between iterations, so the board, the "AI is thinking" pulse
and the phone's own UI stay responsive while thousands of playouts run. Master
budgets 2.5 seconds on a phone instead of blocking.

## The complete rules of Go

These are the rules the engine enforces — all of them.

### 1. Board, stones, first move
* Go is played on the **intersections** of the lines, not inside the squares.
  Standard sizes are 19×19, 13×13 and 9×9; this game supports all three.
* One player takes the **black** stones, the other the **white** stones.
  **Black always plays first.**
* Because moving second is a real disadvantage, White is compensated with
  **komi** — extra points added at counting time. This game uses **7.5**
  (the modern standard). The half point guarantees the game cannot end tied,
  and it means Black has to lead the board by **8 or more** to win: surrounding
  more points than your opponent is not, by itself, winning the game.

### 2. Placing and immutability
* On your turn you place exactly one stone of your colour on any empty
  intersection, or you **pass**.
* Once placed, a stone never moves. It leaves the board only when captured.
* Two consecutive passes end the game.

### 3. Liberties and groups
* The **liberties** of a stone are its empty *orthogonal* neighbours — up,
  down, left, right. Diagonals never count.
* Stones of the same colour that touch orthogonally form one **group**, and
  the group shares every liberty of its stones. A connected chain of five
  stones is one living unit, not five.

### 4. Capture
* When the last liberty of a group is filled, the whole group is **removed**
  from the board immediately. The capturer sets the stones aside as prisoners —
  under area scoring they are not added to the score, they simply stop counting
  for the player who lost them, and the points they used to hold become
  territory.
* A single stone in the corner has 2 liberties, on the edge 3, in the middle
  4 — which is why corners are the cheapest place to start a territory fight.

### 5. Suicide is forbidden
* You may not play a move after which your own new group has zero liberties.
* **Exception that is not suicide:** if the stone you place captures one or
  more enemy groups, those stones are removed *first*, and they may open the
  liberties your move needed. Capture always resolves before the suicide
  check.

### 6. Ko — no instant recapture
* If a single stone is captured in a shape where the opponent could
  immediately recapture and restore the earlier board, that recapture is
  forbidden until something else has been played.
* This game enforces the stricter **super-ko** rule: a move is illegal if the
  resulting position equals **any** position that has already occurred in the
  game, not just the previous one. Positions are stored as immutable tuple
  keys in a set, so the check is O(1).

### 7. Life, eyes and seki (strategy the rules imply)
* A group with **two separate eyes** — two independent empty regions the
  opponent can never fill simultaneously — can never be captured. Such a
  group is *alive*.
* A group with only one eye (or a false eye) is *dead* and is counted as
  prisoner material at the end.
* **Seki** is a shared life where neither player can fill a liberty without
  dying; the points stay neutral.

### 8. Ending and scoring
* The game ends after two passes in a row, or the moment you press **Count score**.
* **Passing is a rule, not a courtesy.** A point inside a region your own
  stones already border is counted for you whether or not you stand on it, so
  under area scoring it gains exactly nothing:

  ```
  p ∈ territory(c)  ⟹  S(c) unchanged when c plays at p  ⟹  c should pass
  ```

  Both AI engines implement this by dropping those points from their candidate
  lists (`_rank_candidates` in `ai.py`, the root children in `mcts.py`, and the
  same two places in `static/ai.js`). When a side is left with nothing
  worthwhile it passes, which is what closes a game — otherwise the AI answers
  forever, 20+ points stay neutral, and the count collapses to
  *stones + half the dame + komi*, which always favours White.
* Every empty region bordered by exactly one colour becomes that colour's
  **territory**. Regions touching both colours are **dame** (neutral points).
  A game can end while dame are still open, so they are shared out in filling
  order (Black first) rather than thrown away.
* The side panel shows a **running count** while you play, using this same
  formula. While more than a quarter of the board is still dame that number is
  noise (it is half the board split down the middle plus komi), so the panel
  reports only the ground each side has actually *enclosed*, and switches to
  the full count — komi included, and who is ahead by how much — once the
  borders are closing.
* This game counts with **area scoring (Chinese rules)**:

  ```
  Score(Black) = stones on board(Black) + territory(Black) + neutral(Black)
  Score(White) = stones on board(White) + territory(White) + neutral(White) + komi(7.5)
  ```

* The higher total wins. Captures are not added on top: a stone you take is a
  stone that stops counting for your opponent.
* **Komi is the one thing that surprises people.** White's 7.5 compensates for
  moving second, so Black has to lead by more than 7.5 — it is entirely
  possible to surround more of the board and still lose. Both front ends print
  the count before and after komi and say plainly when komi decided the game,
  and name the winner as *you* / *the AI* rather than as a bare colour.
  (Japanese *territory* scoring differs only in how prisoners are tallied —
  with correct play the winner is nearly always the same.)

### 9. Handicap and komi variants (context)
* Against a much stronger player, the weaker side places handicap stones on
  the star points first and White plays the first normal move. Komi is then
  usually reduced or removed. The star points drawn on this board
  (9×9: 3 points + centre, 13×13: 9, 19×19: 9) are exactly the handicap
  anchors.

## The mathematics

**Groups as equivalence classes.** With adjacency graph *B*, a group is a
connected component of same-colour stones (found by DFS), and

```
L(G) = { p ∈ B : p is empty and adjacent to some stone of G }
G is captured  ⟺  |L(G)| = 0
move is legal  ⟺  point empty  ∧  (captures ≠ ∅  ∨  |L(own group)| ≥ 1)  ∧  position ∉ history
```

**Board partition (the invariant the score dialog prints).**

```
stones(B) + stones(W) + territory(B) + territory(W) + dame = size²
```

**Area scoring (Chinese rules, komi for White).**

```
S(B) = stones(B) + territory(B) + neutral(B)
S(W) = stones(W) + territory(W) + neutral(W) + 7.5
S(B) + S(W) − komi = size²
margin = |S(B) − S(W)|
```

Territory is computed by a flood fill over the empty points: each connected
empty region collects the set of colours touching it, and a region is owned
only when that set has exactly one member. Regions touched by both colours
(or by nothing) are *dame* — neutral points. A game can end on two passes
while those points are still open, so they are shared out in filling order
(Black fills first) instead of being dropped, which is what keeps the
invariant above exact.

**Komi, and why "ahead on the board" is not the same as winning.** White is
given 7.5 points for letting Black move first, and the half point removes the
possibility of a draw. Black therefore has to lead by more than 7.5: a player
who surrounds more of the board and still loses by komi is counted correctly,
and both the web and desktop score dialogs say so out loud, showing the count
before and after komi. Captures are never added on top — a stone you take is a
stone that stops counting for your opponent.

**Influence fields.** Every stone radiates a field that decays geometrically
with Manhattan distance *d*:

```
I_c(p) = Σ_{s ∈ stones(c)} γ^d(p,s),    γ = 0.62
```

`I_B(p) − I_W(p)` is the local control margin at point *p*, and it is what the
AI "sees" when it decides whether an area is worth invading or extending.

**Move evaluation.** Each candidate move *m* is scored by a weighted linear
function over features measured on the simulated board — captures |C|, enemy
groups pushed into atari *A*, own liberties |L|, merged friendly groups *K*,
atari escapes *R*, influence swing, shape (3rd/4th-line bonus, 1st-line
penalty) and self-atari risk:

```
v(m) = 14·|C| + 5·A + 3·min(|L|,4) + 4·(K−1) + 8·R
     + 6·(I_B−I_W)(p) − 5·max(0, I_B−I_W)(p) − 9·selfatari + shape
```

**Hard mode** adds one ply of defence — it discounts a move by the best reply
the opponent has:

```
v_hard(m) = v(m) − 0.85 · max_{m′ legal for opponent} v(m′)
```

**Master mode** is PUCT Monte-Carlo Tree Search (`mcts.py`). A softmax over
the light heuristic gives each move a prior `P(a)`, tree selection uses

```
child = argmax  W/N + c·P(a)·√ΣN / (1 + N)
```

random playouts are finished with the heuristic and scored by the area
formula above, and the most-visited root move is played. The search is
**time-boxed** (3 seconds, checked inside every playout) so a 19×19 board can
never stall the game.

**Every level keeps the same endgame rule.** Candidates are filtered *before*
they are scored: a point whose empty region is bordered only by the mover's own
colour is already counted for the mover, so it is dropped. If that leaves no
candidate at all, the engine returns `None` — a pass — and two passes end the
game. (`engine.fills_own_territory()` is the same test on its own; the tests use
it to check a single point, and it is what a *human* should be doing at the end
of a game.)

Difficulty, in one sentence: Easy and Medium are the same function with more
score noise and a wider pick-set; Hard adds the defence ply; Master abandons
the single-ply view for tree search.

## The four AI levels

| Level | Engine | What it is good at | Cost per move |
| --- | --- | --- | --- |
| Easy | `GoAI` + noise 9, pick-width 10 | beginner opponents, teaches captures | instant |
| Medium | `GoAI` + noise 2.5, pick-width 3 | sensible shape, takes obvious captures | instant |
| Hard | `GoAI` + 1-ply defence | answers your threats, punishes greed | ~0.1–0.5 s |
| Master | `MCTS` PUCT, 3 s budget | reads whole sequences, best on 9×9 | 3 s |

## Controls

| Control | What it does |
| --- | --- |
| Click intersection | Place your stone (illegal moves are explained on screen) |
| **Mode** | Play vs AI, or **2 Players** hot-seat on one board |
| **AI level** | Easy, Medium, Hard, or **Master** (MCTS tree search) |
| **You play** | Black (moves first) or White (receives 7.5 komi) |
| **Board** | 9×9, 13×13 or 19×19 — applied when you press New Game |
| New Game | Reset with the current settings |
| Pass | Give up your turn — two passes in a row end the game |
| Undo | Take back your move and the AI's reply |
| Count score | End the game now and count the board (asks for confirmation) |
| **Learn Go** | 8-lesson interactive course: liberties, capture, suicide, ko, territory, MCTS, and the endgame pass |
| Rules & Math | The full rule set plus every equation the engine and AI use |

## Tests

```bash
python tests.py        # rules, AI self-play, MCTS
python tests_js.py     # the JavaScript engine must agree with the Python one
node tests/game_server.test.js     # the in-browser server + all four AI levels
```

`tests.py` covers: liberty counting, group merging, capture of a whole group,
the suicide ban, the capture-that-is-not-suicide exception, super-ko rejection,
undo, the territory flood fill, the `size²` partition invariant, the fact that
komi can flip a board lead, which single points are worth a stone and which are
own ground (`fills_own_territory`), a full heuristic-AI self-play game, and MCTS
legality plus a capture-sense check (the Master must take a free stone).

It also checks that the AI *closes* a game: at each of the three heuristic
levels, an AI-vs-AI game must reach two consecutive passes with real territory
on both sides and at most 8 neutral points left. Before the endgame filter
existed these games never ended on passes at all — 19 to 38 of the 81 points
were still open, so the count degenerated into stones plus half the dame plus
komi, and White won every time.

`tests_js.py` plays 24 random games (with passes and undos mixed in) in Python,
replays the exact same move lists in `static/engine.js` under Node, and diffs
board, turn, move count, passes, prisoners, last move, the full legal-move list,
the per-point "is this own ground" flags and the score breakdown. It asserts
`S(B) + S(W) − komi == size²` on both sides. `tests/game_server.test.js` then
drives `game_server.js` through the same JSON routes the page uses, times every
AI level on 9×9 and 19×19, and repeats the two-pass closing check in JavaScript.

The web front-ends were additionally verified end-to-end in a headless browser,
twice: against `python web.py`, and against a plain static file server with no
backend at all (the GitHub Pages case) — load, play, AI pacing, undo, pass,
Count score, the result naming the winner, territory shading, Master on a phone
viewport, and no console errors. A third run plays a whole game to its natural
two-pass end and checks the side panel's running count and the "the AI has
passed — pass too" hint.

## Project layout

```
index.html  the web page (also what GitHub Pages serves)
main.py     desktop entry point (Tkinter)
web.py      optional local web server (stdlib HTTP + JSON API)
ui.py       Tkinter board, sidebar, dialogs (rules text lives here)
static/     web front-end
  app.js        canvas board, bowls, dialogs, Learn course, backend probe
  engine.js     the rules, ported from engine.py
  ai.js         evaluation AI + PUCT MCTS, ported from ai.py / mcts.py
  game_server.js  web.py's routes, running inside the tab
  style.css     theme
engine.py   rules: groups, liberties, captures, ko, suicide, scoring
ai.py       influence-field + evaluation-function opponent (Easy–Hard)
mcts.py     PUCT Monte-Carlo Tree Search opponent (Master)
tests.py    rule-engine tests, AI self-play, MCTS checks
tests_js.py Python ↔ JavaScript engine comparison
tests/      JavaScript-side tests (compare_engine.js, game_server.test.js)
```

## Beginner strategy

* Play **corners → sides → centre**: enclosing territory gets more expensive
  toward the middle.
* Keep your groups connected; cut your opponent's groups apart.
* A group with two separate eyes can never be captured — fight to make eyes.
* Don't crawl on the first line early; it earns almost no influence.
* Use **9×9 vs Easy AI** to learn captures, then climb the ladder to Hard and
  Master.

---

Created by **Maryam J.** — rules engine, heuristic AI and MCTS written from
scratch in pure Python.
