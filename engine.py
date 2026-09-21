"""Go (Baduk / Weiqi) rules engine.

Mathematical model
------------------
* A **group** G is a maximal set of same-colour stones connected by the board
  grid. Connectivity is an equivalence relation; groups are its equivalence
  classes (found with BFS/DFS).
* The **liberty set** of a group is  L(G) = { empty points orthogonally
  adjacent to at least one stone in G }.
* A group is **captured** when |L(G)| = 0 and is removed from the board.
* **Suicide rule:** a move is legal only if, after resolving captures, the
  mover's own group has |L(G)| >= 1.
* **Super-ko:** a move may not recreate any position that already occurred
  in the game (board states are stored as immutable tuple keys).
* **Area scoring (Chinese rules):**
      Score(Black) = stones_on_board(B) + territory(B)
      Score(White) = stones_on_board(W) + territory(W) + komi
  Territory is an empty region bordered by exactly one colour; regions
  bordered by both colours (or nothing) are *dame* (neutral points).
"""

from __future__ import annotations

BLACK, WHITE, EMPTY = 1, -1, 0
COLOR_NAMES = {BLACK: "Black", WHITE: "White"}

LETTERS = "ABCDEFGHJKLMNOPQRST"  # Go convention skips the letter I


def move_name(size: int, x: int, y: int) -> str:
    return f"{LETTERS[x]}{size - y}"


def _neighbours(size: int, x: int, y: int):
    if x + 1 < size:
        yield x + 1, y
    if x - 1 >= 0:
        yield x - 1, y
    if y + 1 < size:
        yield x, y + 1
    if y - 1 >= 0:
        yield x, y - 1


def copy_board(board):
    return [row[:] for row in board]


def find_group(board, x, y):
    """Return (stones, liberties) of the group occupying (x, y)."""
    size = len(board)
    color = board[x][y]
    if color == EMPTY:
        return set(), set()
    stones = {(x, y)}
    liberties = set()
    stack = [(x, y)]
    while stack:
        cx, cy = stack.pop()
        for nx, ny in _neighbours(size, cx, cy):
            v = board[nx][ny]
            if v == EMPTY:
                liberties.add((nx, ny))
            elif v == color and (nx, ny) not in stones:
                stones.add((nx, ny))
                stack.append((nx, ny))
    return stones, liberties


def simulate_move(board, x, y, color):
    """Apply a stone on a copy and resolve captures.

    Returns (new_board, captured_set) or None if the move is impossible
    (point occupied, or the move is suicide after captures are taken).
    """
    if board[x][y] != EMPTY:
        return None
    nb = copy_board(board)
    nb[x][y] = color
    enemy = -color
    captured = set()
    for nx, ny in _neighbours(len(nb), x, y):
        if nb[nx][ny] == enemy:
            stones, libs = find_group(nb, nx, ny)
            if not libs:
                captured |= stones
    for cx, cy in captured:
        nb[cx][cy] = EMPTY
    _, my_libs = find_group(nb, x, y)
    if not my_libs:
        return None
    return nb, captured


class Game:
    def __init__(self, size: int = 19, komi: float = 7.5):
        self.size = size
        self.komi = komi
        self.board = [[EMPTY] * size for _ in range(size)]
        self.current = BLACK
        self.passes = 0
        self.captured_by = {BLACK: 0, WHITE: 0}
        self.move_number = 0
        self.last_move = None
        self.over = False
        self.result = None
        self.history = []
        self.positions = set()
        self.positions.add(self._key(self.board))

    # ---------------------------------------------------------- helpers
    @staticmethod
    def _key(board):
        return tuple(tuple(row) for row in board)

    def is_legal(self, x, y):
        """(ok, reason, captured_set). reason is '' on success."""
        if self.over:
            return False, "game is over", set()
        sim = simulate_move(self.board, x, y, self.current)
        if sim is None:
            reason = "point is occupied" if self.board[x][y] != EMPTY else "suicide is not allowed"
            return False, reason, set()
        nb, captured = sim
        if self._key(nb) in self.positions:
            return False, "ko: that move repeats the previous position", set()
        return True, "", captured

    # ---------------------------------------------------------- moves
    def play(self, x, y):
        ok, reason, captured = self.is_legal(x, y)
        if not ok:
            return False, reason
        nb, captured = simulate_move(self.board, x, y, self.current)
        self._push_history()
        self.board = nb
        self.captured_by[self.current] += len(captured)
        self.passes = 0
        self.move_number += 1
        self.last_move = (x, y)
        self.positions.add(self._key(nb))
        self.current = -self.current
        return True, captured

    def pass_move(self):
        if self.over:
            return False
        self._push_history()
        self.passes += 1
        self.move_number += 1
        self.last_move = None
        if self.passes >= 2:
            self.over = True
            self.result = self.score()
        self.current = -self.current
        return True

    def _push_history(self):
        self.history.append(
            {
                "board": copy_board(self.board),
                "current": self.current,
                "passes": self.passes,
                "captured_by": dict(self.captured_by),
                "move_number": self.move_number,
                "last_move": self.last_move,
            }
        )

    def undo(self):
        if not self.history:
            return False
        self.positions.discard(self._key(self.board))
        state = self.history.pop()
        self.board = state["board"]
        self.current = state["current"]
        self.passes = state["passes"]
        self.captured_by = state["captured_by"]
        self.move_number = state["move_number"]
        self.last_move = state["last_move"]
        self.over = False
        self.result = None
        return True

    # ---------------------------------------------------------- scoring
    def territory_map(self):
        """Classify every empty point: {(x, y): BLACK | WHITE | 'dame'}."""
        size = self.size
        board = self.board
        visited = [[False] * size for _ in range(size)]
        owners = {}
        for sy in range(size):
            for sx in range(size):
                if board[sx][sy] != EMPTY or visited[sx][sy]:
                    continue
                region = [(sx, sy)]
                visited[sx][sy] = True
                borders = set()
                i = 0
                while i < len(region):
                    cx, cy = region[i]
                    i += 1
                    for nx, ny in _neighbours(size, cx, cy):
                        v = board[nx][ny]
                        if v == EMPTY and not visited[nx][ny]:
                            visited[nx][ny] = True
                            region.append((nx, ny))
                        elif v != EMPTY:
                            borders.add(v)
                if borders == {BLACK}:
                    owner = BLACK
                elif borders == {WHITE}:
                    owner = WHITE
                else:
                    owner = "dame"
                for px, py in region:
                    owners[(px, py)] = owner
        return owners

    def score(self):
        """Area scoring breakdown (Chinese rules, komi for White)."""
        board = self.board
        black_stones = sum(row.count(BLACK) for row in board)
        white_stones = sum(row.count(WHITE) for row in board)

        owners = self.territory_map()
        black_territory = sum(1 for o in owners.values() if o == BLACK)
        white_territory = sum(1 for o in owners.values() if o == WHITE)
        dame = sum(1 for o in owners.values() if o == "dame")

        black_total = black_stones + black_territory
        white_total = white_stones + white_territory + self.komi
        margin = black_total - white_total
        if margin > 0:
            winner = "Black"
        elif margin < 0:
            winner = "White"
        else:
            winner = "Draw"
        return {
            "black_stones": black_stones,
            "white_stones": white_stones,
            "black_territory": black_territory,
            "white_territory": white_territory,
            "dame": dame,
            "komi": self.komi,
            "black_total": black_total,
            "white_total": white_total,
            "margin": abs(margin),
            "winner": winner,
        }

    def final_score(self):
        if not self.over:
            self.over = True
            self.result = self.score()
        return self.result
