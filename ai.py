"""Math-based Go opponent.

The AI ranks every legal candidate move with a linear evaluation function:

    v(m) = w_cap·|C(m)|                     stones captured by the move
         + w_atari·A(m)                     enemy groups reduced to |L| = 1
         + w_lib·min(|L(G_m)|, 4)           liberties of the played group
         + w_conn·(K(m) - 1)                friendly groups merged by the move
         + w_rescue·R(m)                    escaping own atari
         + w_inf·(I_c(p_m) - I_e(p_m))      influence gained at the point
         - w_waste·max(0, I_c - I_e)(p_m)   penalty for filling own territory
         - w_risk·OwnAtari(m)               moving into a self-atari
         + shape(m)                         3rd/4th-line bonus, 1st-line penalty

Influence is an exponential-decay field over the board:

    I_c(p) = Σ_{s ∈ stones(c)} γ^d(p, s)        d = Manhattan distance

with γ < 1, so each stone's pull falls off geometrically with distance.
Hard mode additionally checks the opponent's strongest immediate reply:

    v_hard(m) = v(m) - w_reply · max_{m'} v_opp(m')

Before anything is scored, candidates are filtered: a point whose empty region
is bordered only by the mover's own colour adds nothing to S(mover), so it is
dropped.  When that leaves the list empty the AI returns None — a pass — which
is what lets a game reach its two-pass ending and be counted.
"""

from __future__ import annotations

import random

from engine import (BLACK, WHITE, EMPTY, _neighbours, find_group, region_owners,
                    simulate_move)

DECAY = 0.62
INFLUENCE_RADIUS = 6

W = {
    "capture": 14.0,
    "atari": 5.0,
    "liberty": 3.0,
    "connect": 4.0,
    "rescue": 8.0,
    "influence": 6.0,
    "waste": 5.0,
    "risk": 9.0,
    "reply": 0.85,
}

LEVELS = {
    "easy": {"noise": 9.0, "pick": 10, "lookahead": False},
    "medium": {"noise": 2.5, "pick": 3, "lookahead": False},
    "hard": {"noise": 0.4, "pick": 1, "lookahead": True},
}


def influence_map(board, color, decay=DECAY):
    """I_c(p) = sum of decay^manhattan_distance over all stones of `color`."""
    size = len(board)
    field = [[0.0] * size for _ in range(size)]
    for sx in range(size):
        for sy in range(size):
            if board[sx][sy] != color:
                continue
            seen = {(sx, sy)}
            frontier = [(sx, sy)]
            power = 1.0
            radius = 0
            while frontier and power > 0.02 and radius <= INFLUENCE_RADIUS:
                for x, y in frontier:
                    field[x][y] += power
                power *= decay
                nxt = []
                for x, y in frontier:
                    for n in _neighbours(size, x, y):
                        if n not in seen:
                            seen.add(n)
                            nxt.append(n)
                frontier = nxt
                radius += 1
    return field


def _edge_distance(size, x, y):
    return min(x, y, size - 1 - x, size - 1 - y)


def _shape_bonus(size, x, y):
    d = _edge_distance(size, x, y)
    if d == 0:
        return -6.0
    if d == 1:
        return -3.0
    if d in (2, 3):
        return 2.5
    return 0.0


class GoAI:
    def __init__(self, color, level="medium"):
        self.color = color
        self.level = level

    # ------------------------------------------------------------ core
    def _score_move(self, game, x, y, inf_me, inf_opp):
        color = self.color
        enemy = -color
        board = game.board
        size = game.size
        sim = simulate_move(board, x, y, color)
        if sim is None:
            return None
        nb, captured = sim
        if game._key(nb) in game.positions:  # ko / super-ko
            return None

        stones, libs = find_group(nb, x, y)
        score = W["capture"] * len(captured)
        score += W["liberty"] * min(len(libs), 4)

        # enemy groups left with a single liberty (in atari)
        seen_groups = set()
        for nx, ny in _neighbours(size, x, y):
            if nb[nx][ny] == enemy:
                group = frozenset(find_group(nb, nx, ny)[0])
                if group in seen_groups:
                    continue
                seen_groups.add(group)
                if len(find_group(nb, nx, ny)[1]) == 1:
                    score += W["atari"]

        # friendly groups merged by this stone (connectivity)
        my_groups = set()
        for nx, ny in _neighbours(size, x, y):
            if board[nx][ny] == color:
                my_groups.add(frozenset(find_group(board, nx, ny)[0]))
        score += W["connect"] * max(0, len(my_groups) - 1)

        # was one of my adjacent groups in atari before this move?
        for g in my_groups:
            _, libs_before = find_group(board, next(iter(g))[0], next(iter(g))[1])
            if len(libs_before) == 1 and len(libs) > 1:
                score += W["rescue"]
                break

        # moving into self-atari is bad unless it captures something
        if len(libs) == 1 and not captured:
            score -= W["risk"]

        # influence / territory terms
        gain = inf_me[x][y] - inf_opp[x][y]
        score += W["influence"] * gain
        if gain > 0:
            score -= W["waste"] * gain

        score += _shape_bonus(size, x, y)
        return score

    def _rank_candidates(self, game, inf_me, inf_opp):
        """Score every candidate that is worth a stone.

        A point inside the region the mover already owns is worth nothing under
        area scoring — that ground is already counted — so those points are
        dropped here rather than played.  When nothing else is left the mover
        has no move to make and passes, which is what closes a game.
        """
        owners = region_owners(game.board, game.size)
        scored = []
        for x, y in self._candidates(game):
            if owners.get((x, y)) == self.color:
                continue
            s = self._score_move(game, x, y, inf_me, inf_opp)
            if s is not None:
                scored.append((s, x, y))
        scored.sort(reverse=True)
        return scored

    def _candidates(self, game):
        board = game.board
        size = game.size
        if game.move_number == 0:
            c = size // 2
            offset = 3 if size >= 15 else 2
            pts = []
            for dx in (-offset, 0, offset):
                for dy in (-offset, 0, offset):
                    x, y = c + dx, c + dy
                    if 0 <= x < size and 0 <= y < size:
                        pts.append((x, y))
            return pts
        near = set()
        for sx in range(size):
            for sy in range(size):
                if board[sx][sy] == EMPTY:
                    continue
                for dx in range(-2, 3):
                    for dy in range(-2, 3):
                        x, y = sx + dx, sy + dy
                        if (
                            0 <= x < size
                            and 0 <= y < size
                            and board[x][y] == EMPTY
                            and abs(dx) + abs(dy) <= 3
                        ):
                            near.add((x, y))
        return sorted(near)

    # ------------------------------------------------------------ API
    def choose_move(self, game):
        """Return (x, y) or None to pass.

        None means "nothing on this board is worth another stone", which is
        how a game reaches its two-pass ending and gets counted.
        """
        inf_me = influence_map(game.board, self.color)
        inf_opp = influence_map(game.board, -self.color)
        scored = self._rank_candidates(game, inf_me, inf_opp)
        cfg = LEVELS[self.level]

        if not scored:
            return None

        if cfg["lookahead"] and len(scored) > 1:
            scored = self._refine_with_reply(game, scored[:12])

        pool = scored[: cfg["pick"]]
        if not pool:
            return None
        best = max(pool, key=lambda t: t[0] + random.gauss(0, cfg["noise"]))
        return (best[1], best[2])

    def _refine_with_reply(self, game, my_scored):
        """v_hard(m) = v(m) - w_reply * best immediate enemy reply."""
        enemy_ai = GoAI(-self.color, "medium")
        refined = []
        for s, x, y in my_scored:
            sim = simulate_move(game.board, x, y, self.color)
            if sim is None:
                continue
            nb = sim[0]
            fake = Game_view(game, nb)
            e_inf_me = influence_map(nb, -self.color)
            e_inf_opp = influence_map(nb, self.color)
            reply = enemy_ai._rank_candidates(fake, e_inf_me, e_inf_opp)
            threat = reply[0][0] if reply else 0.0
            refined.append((s - W["reply"] * max(0.0, threat), x, y))
        refined.sort(reverse=True)
        return refined


class Game_view:
    """Read-only shim: same board after a hypothetical move, for the reply search."""

    def __init__(self, game, board):
        self.size = game.size
        self.board = board
        self.positions = game.positions
        self.move_number = game.move_number
        self._key = game._key
