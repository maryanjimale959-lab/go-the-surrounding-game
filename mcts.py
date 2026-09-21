"""Monte-Carlo Tree Search (PUCT) Go player — the "Master" level.

While Easy/Medium/Hard pick moves greedily from the evaluation function,
Master builds a search tree:

    selection    child = argmax  W/N + c_puct · P(a) · √ΣN / (1 + N)
    expansion    new children from a light heuristic policy P(a) (softmax)
    simulation   fast random-ish playouts to two passes
    evaluation   area scoring: S(B) vs S(W) + komi
    backup       propagate the win signal up the tree

The policy prior for each candidate move is

    score(m) = 12·|captures| + 2·min(|L|, 4) − 6·self-atari + ε

with ε random tie-break noise, turned into P(a) by a softmax.
"""

from __future__ import annotations

import math
import random
import time

from engine import (BLACK, WHITE, EMPTY, Game, _neighbours, copy_board,
                    find_group, simulate_move)

CPUCT = 1.2
POLICY_TEMP = 3.0
MAX_SIMS = 20000


# ------------------------------------------------------------------ board ops
def _apply(board, x, y, color):
    """Apply a legal move in place; returns captured count."""
    size = len(board)
    sim = simulate_move(board, x, y, color)
    if sim is None:
        return -1
    nb, captured = sim
    for row_i in range(size):
        board[row_i][:] = nb[row_i]
    return len(captured)


def _candidate_points(board, color, min_dist=2):
    size = len(board)
    near = set()
    for sx in range(size):
        for sy in range(size):
            if board[sx][sy] == EMPTY:
                continue
            for dx in range(-min_dist, min_dist + 1):
                for dy in range(-min_dist, min_dist + 1):
                    if abs(dx) + abs(dy) > min_dist + 1:
                        continue
                    x, y = sx + dx, sy + dy
                    if 0 <= x < size and 0 <= y < size and board[x][y] == EMPTY:
                        near.add((x, y))
    if not near:  # empty board: offer the centre and star points
        c = size // 2
        off = 3 if size >= 15 else 2
        for dx in (-off, 0, off):
            for dy in (-off, 0, off):
                if 0 <= c + dx < size and 0 <= c + dy < size:
                    near.add((c + dx, c + dy))
    return near


def _light_score(board, x, y, color):
    sim = simulate_move(board, x, y, color)
    if sim is None:
        return None
    nb, captured = sim
    _, libs = find_group(nb, x, y)
    s = 12.0 * len(captured) + 2.0 * min(len(libs), 4)
    if len(libs) == 1 and not captured:
        s -= 6.0
    d = min(x, y, len(board) - 1 - x, len(board) - 1 - y)
    if d <= 1:
        s -= 2.0
    friends = sum(1 for nx, ny in _neighbours(len(board), x, y) if board[nx][ny] == color)
    if friends >= 2 and not captured:
        s -= 2.5  # don't crowd our own stones in playouts
    return s + random.random()


def _policy(board, color, forbidden=()):
    """Return [(score, prior, x, y)] softmax-ranked candidate moves."""
    scored = []
    for x, y in _candidate_points(board, color):
        if (x, y) in forbidden:
            continue
        s = _light_score(board, x, y, color)
        if s is not None:
            scored.append((s, x, y))
    if not scored:
        return []
    top = max(s for s, _, _ in scored)
    exps = [(math.exp((s - top) / POLICY_TEMP), x, y) for s, x, y in scored]
    z = sum(e for e, _, _ in exps)
    return [(e / z, x, y) for e, x, y in exps]


# ------------------------------------------------------------------ playout
def _playout(board, current, moves_done, move_cap, deadline=None):
    size = len(board)
    board = copy_board(board)
    passes = 0
    cap = min(max(0, move_cap), size * size)
    for i in range(cap):
        if deadline is not None and i % 12 == 11 and time.time() > deadline:
            break
        scored = []
        for x, y in _candidate_points(board, current):
            s = _light_score(board, x, y, current)
            if s is not None:
                scored.append((s, x, y))
        scored.sort(reverse=True)
        played = False
        if scored and scored[0][0] > 0.5:
            _, x, y = random.choice(scored[: min(3, len(scored))])
            if _apply(board, x, y, current) >= 0:
                passes = 0
                played = True
        if not played:
            passes += 1
            if passes >= 2:
                break
        current = -current
    g = Game(size=size)
    g.board = board
    res = g.score()
    return res


# ------------------------------------------------------------------ tree
class Node:
    __slots__ = ("move", "parent", "children", "visits", "wins", "prior",
                 "untried", "player")

    def __init__(self, move, parent, prior, player):
        self.move = move
        self.parent = parent
        self.children = []
        self.visits = 0
        self.wins = 0.0
        self.prior = prior
        self.untried = None
        self.player = player  # colour that PLAYED self.move

    def ucb(self, parent_visits):
        exploit = self.wins / (self.visits + 1e-9)
        explore = CPUCT * self.prior * math.sqrt(parent_visits) / (1.0 + self.visits)
        return exploit + explore


def _replay(root_path_moves, size, start_board, start_color):
    """Rebuild a board by replaying tree moves; returns (board, to_play, path_positions)."""
    board = copy_board(start_board)
    current = start_color
    for x, y, player in root_path_moves:
        _apply(board, x, y, player)
        current = -player
    return board, current, len(root_path_moves)


class MCTS:
    def __init__(self, color, seconds=3.0):
        self.color = color
        self.seconds = seconds

    def choose_move(self, game):
        deadline = time.time() + self.seconds
        root = Node(None, None, 1.0, -self.color)  # root.player = who moved last
        move_cap = 2 * game.size * game.size

        # precompute root children from policy (respecting real ko)
        priors = _policy(game.board, self.color)
        legal_children = []
        for prior, x, y in priors:
            sim = simulate_move(game.board, x, y, self.color)
            if sim is None or game._key(sim[0]) in game.positions:
                continue
            child = Node((x, y), root, prior, self.color)
            legal_children.append(child)
        root.children = legal_children
        root.untried = []
        if not legal_children:
            return None

        sims = 0
        while time.time() < deadline and sims < MAX_SIMS:
            sims += 1
            # --- selection ---
            node = root
            path = []  # (x, y, player) moves from root
            while True:
                if node.untried is None and node is not root:
                    node.untried = _policy_children(node, game, path)
                if node.untried:
                    prior, x, y = node.untried.pop(0)
                    child = Node((x, y), node, prior, -node.player)
                    node.children.append(child)
                    node = child
                    path.append((x, y, node.player))
                    break
                if not node.children:
                    break
                node = max(node.children, key=lambda c: c.ucb(node.visits))
                if node.move:
                    path.append((node.move[0], node.move[1], node.player))

            # --- simulation from the selected node ---
            board, to_play, moves_done = self._board_at(game, path)
            result = _playout(board, to_play, moves_done, move_cap, deadline)
            reward = 1.0 if (
                (result["black_total"] > result["white_total"]) == (self.color == BLACK)
            ) else 0.0

            # --- backup ---
            node.visits += 1
            node.wins += reward if node.player == self.color else 1.0 - reward
            node = node.parent
            while node is not None:
                node.visits += 1
                if node.move is not None:
                    node.wins += reward if node.player == self.color else 1.0 - reward
                node = node.parent

        best = max(root.children, key=lambda c: c.visits)
        return best.move

    def _board_at(self, game, path):
        board = copy_board(game.board)
        current = self.color
        for x, y, player in path:
            _apply(board, x, y, player)
            current = -player
        return board, current, len(path) + game.move_number


def _policy_children(node, game, path):
    board, _, _ = _replay(path[:-1], game.size, game.board, -node.player)
    _apply(board, node.move[0], node.move[1], node.player)
    return [(prior, x, y) for prior, x, y in _policy(board, -node.player)]
