# Go — the Surrounding Game

**Created by Maryam J.**

A complete implementation of the ancient board game **Go** (Baduk / Weiqi),
written from scratch with no third-party dependencies: the full rules, the
mathematics behind scoring and the AI, an interactive **Learn Go** course,
and two front-ends — a 3D isometric **Tkinter desktop app** and a modern
responsive **web app** you can play from phone, tablet or PC.

```
python web.py      # → http://localhost:8763   (play in the browser)
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
| Heuristic AI (Easy / Medium / Hard) built on influence fields and an evaluation function | `ai.py` |
| MCTS "Master" AI (PUCT tree search + random playouts) | `mcts.py` |
| Web server (stdlib HTTP + JSON API) | `web.py` |
| Web front-end: canvas board, animations, sound, dialogs | `static/` |
| Desktop app: isometric 3D board, sidebar, Learn course | `main.py`, `ui.py` |
| Rule + AI tests and a full self-play game | `tests.py` |

No `pip install` is required for anything. Python 3.8+ is enough; Tkinter is
only needed for the desktop window (on Debian/Ubuntu: `sudo apt install python3-tk`).

## Install and run

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
so any device on the same network can join — the game state lives on the
server, so two people can also pass the phone back and forth.

```bash
python main.py                # desktop app instead
```

## How it works (architecture)

The project is layered so that the rules exist exactly once:

```
        ┌───────────────────────────┐        ┌──────────────────────────┐
        │  web.py  (HTTP + JSON)    │        │  ui.py / main.py        │
        │  static/  (canvas board)  │        │  Tkinter window          │
        └─────────────┬─────────────┘        └───────────┬──────────────┘
                      │                                  │
                      ▼                                  ▼
                 ┌────────────────────────────────────────────┐
                 │  engine.py   Game(size, komi)              │
                 │  the only place a move can be accepted     │
                 └───────┬──────────────────────┬─────────────┘
                         │                      │
                         ▼                      ▼
                    ai.py (heuristic)      mcts.py (PUCT search)
```

**A move, step by step (web app):**

1. You click an intersection. `app.js` converts the pixel position back into
   grid coordinates (`x`, `y`) and `POST`s `/api/move`.
2. `web.py` holds a single shared `Game` object behind a `threading.Lock`, so
   two browsers can never corrupt the same board.
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
   board never shows a half-finished turn.
6. The front-end diffs the returned board against the previous one, pops the
   new stones in with a 140 ms `easeOutBack` animation, and plays a short
   WebAudio "click" — the sound of a stone hitting wood.

**Coordinates.** The board is `board[x][y]` where `x` is the file (letter,
`A..T` skipping `I` by Go convention) and `y` is the rank counted from the
top, so `engine.move_name(19, 3, 3)` returns `"D16"`.

**Two front-ends, one brain.** The Tkinter app calls `Game` and `GoAI`
directly in-process — no HTTP, no JSON. Both apps render the same rules and
report the same legality reasons.

## The complete rules of Go

These are the rules the engine enforces — all of them.

### 1. Board, stones, first move
* Go is played on the **intersections** of the lines, not inside the squares.
  Standard sizes are 19×19, 13×13 and 9×9; this game supports all three.
* One player takes the **black** stones, the other the **white** stones.
  **Black always plays first.**
* Because moving second is a real disadvantage, White is compensated with
  **komi** — extra points added at counting time. This game uses **7.5**
  (the modern standard). The half point guarantees the game cannot end tied.

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
  from the board immediately, and the capturing player keeps the stones as
  prisoners for scoring purposes.
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
* The game ends after two passes in a row, or the moment you press **Score**.
* Every empty region bordered by exactly one colour becomes that colour's
  **territory**. Regions touching both colours are **dame** (neutral points)
  and belong to nobody.
* This game counts with **area scoring (Chinese rules)**:

  ```
  Score(Black) = stones on board(Black) + territory(Black)
  Score(White) = stones on board(White) + territory(White) + komi(7.5)
  ```

* The higher total wins; the margin is printed with the full breakdown.
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
S(B) = stones(B) + territory(B)
S(W) = stones(W) + territory(W) + 7.5
margin = |S(B) − S(W)|
```

Territory is computed by a flood fill over the empty points: each connected
empty region collects the set of colours touching it, and a region is owned
only when that set has exactly one member.

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
| Score | End the game now and count the board (asks for confirmation) |
| **Learn Go** | 7-lesson interactive course: liberties, capture, suicide, ko, territory, MCTS |
| Rules & Math | The full rule set plus every equation the engine and AI use |

## Tests

```bash
python tests.py
```

Covers: liberty counting, group merging, capture of a whole group, the
suicide ban, the capture-that-is-not-suicide exception, super-ko rejection,
undo, the territory flood fill, the `size²` partition invariant, a full
heuristic-AI self-play game, and MCTS legality plus a capture-sense check
(the Master must take a free stone). The web API was additionally verified
end-to-end in a headless browser: play-on-load vs AI, Master on 19×19 as
White, scoring, game-over hints, and the two-player mode staying silent.

## Project layout

```
main.py     desktop entry point (Tkinter)
web.py      web server entry point (stdlib HTTP + JSON API)
ui.py       Tkinter board, sidebar, dialogs (rules text lives here)
static/     web front-end: index.html, app.js, style.css
engine.py   rules: groups, liberties, captures, ko, suicide, scoring
ai.py       influence-field + evaluation-function opponent (Easy–Hard)
mcts.py     PUCT Monte-Carlo Tree Search opponent (Master)
tests.py    rule-engine tests, AI self-play, MCTS checks
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
