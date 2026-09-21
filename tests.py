"""Rule-engine and AI self-play tests:  python tests.py"""

from ai import GoAI, influence_map
from engine import BLACK, WHITE, EMPTY, Game


def empty_board(n=8):
    return [[EMPTY] * n for _ in range(n)]


def fresh_game(size, board, current=BLACK):
    g = Game(size=size)
    g.board = board
    g.positions = {g._key(board)}
    g.current = current
    return g


def test_liberties_and_capture():
    g = Game(size=5)
    g.play(1, 1)  # black stone with 4 liberties
    g.play(2, 1)  # white
    g.play(4, 4)  # black elsewhere
    g.play(0, 1)  # white
    g.play(3, 4)  # black
    g.play(1, 0)  # white
    g.play(4, 3)  # black
    ok, info = g.play(1, 2)  # white takes the last liberty
    assert ok, info
    assert g.board[1][1] == EMPTY, "stone should be captured"
    assert g.captured_by[WHITE] == 1


def test_suicide_banned():
    g = Game(size=5)
    g.play(4, 4)  # black filler
    g.play(1, 0)  # white
    g.play(3, 4)  # black filler
    g.play(0, 1)  # white: (0,0) is now a suicide point for black
    ok, reason = g.play(0, 0)
    assert not ok and "suicide" in reason, (ok, reason)


def test_ko():
    board = empty_board(8)
    board[1][0] = BLACK
    board[0][1] = BLACK
    board[1][2] = BLACK
    board[1][1] = WHITE  # white stone with a single liberty at (2,1)
    board[2][0] = WHITE
    board[2][2] = WHITE
    board[3][1] = WHITE
    g = fresh_game(8, board, current=BLACK)

    ok, info = g.play(2, 1)  # black captures the lone white stone
    assert ok, info
    assert g.board[1][1] == EMPTY

    # white may not recapture at (1,1): it recreates the previous position
    ok, reason, _c = g.is_legal(1, 1)
    assert not ok and "ko" in reason, (ok, reason)

    # play a round elsewhere, then the recapture becomes legal
    g.play(7, 0)  # white filler (current flipped to white after black's capture)
    g.play(7, 7)  # black filler
    ok, reason, _c = g.is_legal(1, 1)
    assert ok, reason
    ok, info = g.play(1, 1)  # white recaptures black's ko stone
    assert ok, info
    assert g.board[2][1] == EMPTY


def test_scoring_math():
    # Black wall on column x=2 owns the left half; white stones block the right.
    board = empty_board(5)
    for y in range(5):
        board[2][y] = BLACK
    board[4][0] = WHITE
    board[4][4] = WHITE
    board[3][1] = WHITE
    board[3][3] = WHITE
    res = fresh_game(5, board).score()
    assert res["black_stones"] == 5
    assert res["black_territory"] == 10  # columns 0 and 1
    assert res["white_territory"] == 0
    assert res["dame"] == 6  # right-side points touch both colours
    assert res["white_total"] == res["white_stones"] + res["white_territory"] + 7.5
    assert res["winner"] == "Black"


def test_influence_field():
    board = empty_board(5)
    board[2][2] = BLACK
    f = influence_map(board, BLACK)
    assert abs(f[2][2] - 1.0) < 1e-9
    assert abs(f[2][1] - 0.62) < 1e-9
    assert f[0][0] < f[2][1]  # decays with distance


def test_ai_selfplay():
    g = Game(size=9)
    ais = {BLACK: GoAI(BLACK, "medium"), WHITE: GoAI(WHITE, "easy")}
    for _ in range(200):
        if g.over:
            break
        mv = ais[g.current].choose_move(g)
        if mv is None:
            g.pass_move()
        else:
            ok, info = g.play(*mv)
            assert ok, info
    res = g.final_score()
    accounted = (
        res["black_total"]
        + res["white_total"]
        - res["komi"]
        + res["dame"]
    )
    assert accounted <= 81
    print(f"self-play finished: Black {res['black_total']} - White {res['white_total']} "
          f"({res['winner']} wins by {res['margin']})")


def test_mcts():
    from mcts import MCTS

    g = Game(size=9)
    mv = MCTS(BLACK, seconds=0.5).choose_move(g)
    assert mv is not None, "MCTS must open somewhere"
    ok, info = g.play(*mv)
    assert ok, info

    # capture sense: white takes the black stone whose last liberty is (4,5)
    board = empty_board(9)
    board[4][4] = BLACK
    board[3][4] = WHITE
    board[5][4] = WHITE
    board[4][3] = WHITE
    g2 = fresh_game(9, board, current=WHITE)
    assert MCTS(WHITE, seconds=1.0).choose_move(g2) == (4, 5)


if __name__ == "__main__":
    test_liberties_and_capture()
    test_suicide_banned()
    test_ko()
    test_scoring_math()
    test_influence_field()
    test_ai_selfplay()
    test_mcts()
    print("All tests passed.")
