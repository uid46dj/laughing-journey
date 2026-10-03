"""Rules-engine validation for the Chess Arena board.

Run:  python3 .build/test_rules.py          (uses python-chess as an oracle)
      python3 .build/test_rules.py --quick  (published perft values only)
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chess  # optional oracle
from chess_arena import Board, START_FEN  # noqa: E402

PERFT = [
    (START_FEN, [20, 400, 8902, 197281]),
    ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862]),
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812]),
    ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
    ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486, 62379]),
    ("r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10", [46, 2079, 89890]),
]
TRICKY = [
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 b - - 0 1",
    "n1n5/PPPk4/8/8/8/8/4Kppp/5N1N b - - 0 1",
    "n1n5/PPPk4/8/8/8/8/4Kppp/5N1N w - - 0 1",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 b kq - 0 1",
    "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R b KQ - 1 8",
    "r2q1rk1/pP1p2pp/Q4n2/bbp1p3/Np6/1B3NBn/pPPP1PPP/R3K2R w KQ - 0 1",
    "1k1r4/pp1b1R2/3q2pp/4p3/2B5/4Q3/PPP2B2/2K5 b - - 0 1",
    "4k3/1P6/8/8/8/8/K7/8 w - - 0 1",
    "8/1k6/8/2Pp4/8/8/8/4K3 w - d6 0 1",
    "8/8/8/1k6/2Pp4/8/8/4K3 b - d3 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
]


def ref_perft(board, depth):
    """Standard perft: count every leaf, ignoring draws (matches FEN perft)."""
    if depth == 0:
        return 1
    moves = list(board.legal_moves)
    if not moves:
        return 0
    total = 0
    for mv in moves:
        board.push(mv)
        total += ref_perft(board, depth - 1)
        board.pop()
    return total


def main():
    quick = "--quick" in sys.argv
    failures = 0
    t0 = time.time()
    for fen, expected in PERFT:
        for d, exp in enumerate(expected, 1):
            got = Board(fen).perft(d)
            if got != exp:
                failures += 1
                print("FAIL perft %d: got %d want %d  %s" % (d, got, exp, fen[:45]))
    print("published perft: %d failures (%.1fs)" % (failures, time.time() - t0))

    if quick:
        return failures
    # Oracle: python-chess is the source of truth for the tricky positions.
    for fen in TRICKY:
        for d in (1, 2, 3):
            mine = Board(fen).perft(d)
            theirs = ref_perft(chess.Board(fen), d)
            if mine != theirs:
                failures += 1
                print("ORACLE FAIL depth %d: mine %d ref %d  %s" % (d, mine, theirs, fen[:45]))

    # Random self-play: legal move sets, SAN, UCI and FEN must match exactly.
    rng = random.Random(20240501)
    positions = plies = 0
    for _ in range(40):
        rb, mine = chess.Board(), Board(START_FEN)
        for _ in range(80):
            ref_sans = sorted(rb.san(m) for m in rb.legal_moves)
            my_sans = sorted(mine.san(m) for m in mine.legal_moves())
            positions += 1
            if ref_sans != my_sans:
                failures += 1
                print("MOVE MISMATCH", mine.fen())
                print("  missing:", sorted(set(ref_sans) - set(my_sans))[:8])
                print("  extra  :", sorted(set(my_sans) - set(ref_sans))[:8])
                break
            if rb.is_game_over():
                break
            mv = rng.choice(list(rb.legal_moves))
            my_mv = mine.find_move(rb.san(mv))
            if my_mv is None or mine.uci(my_mv) != mv.uci():
                failures += 1
                print("LOOKUP FAIL", rb.san(mv), mine.fen())
                break
            rb.push(mv)
            mine.make_move(my_mv)
            plies += 1
            if mine.fen() != rb.fen():
                failures += 1
                print("FEN MISMATCH\n mine: %s\n ref : %s" % (mine.fen(), rb.fen()))
                break
    print("oracle positions: %d  plies: %d" % (positions, plies))

    # make/unmake must be perfectly reversible.
    for fen in TRICKY[:8]:
        board = Board(fen)
        base = board.fen()
        for move in board.legal_moves():
            board.make_move(move)
            board.unmake_move()
            assert board.fen() == base, (fen, move)
            assert board.hash == board.compute_hash(), (fen, move)
    print("make/unmake reversibility: ok")
    return failures


if __name__ == "__main__":
    print("RULES-OK" if main() == 0 else "RULES-FAILURES")
