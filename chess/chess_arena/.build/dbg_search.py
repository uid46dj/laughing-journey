import os
import sys
import time

sys.path.insert(0, "/workspaces/laughing-journey/chess_arena")
from chess_arena import (Board, Evaluator, Searcher, TranspositionTable,
                         TimeManager, START_FEN, MATE_BOUND)

TESTS = [
    # (fen, depth, expected best-move SAN subset)
    ("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "Ra1+"),
    ("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4", "Kxf7"),
    ("2rr3k/pp3pp1/1nnqbN1p/3pN3/2pP4/2P3Q1/PPB4P/R4RK1 w - - 1 1", None),
    ("8/8/8/8/8/1k6/8/K1B5 w - - 0 1", "Bb2+"),
]

ev = Evaluator("balanced")
tt = TranspositionTable(32)
for fen, expect in TESTS:
    b = Board(fen)
    s = Searcher(ev, tt)
    tm = TimeManager(60, 0, 40, 2.0, 5.0)
    t0 = time.time()
    info = s.search(b, 12, tm)
    san = b.san(info.best_move)
    pv = " ".join(b.san(m) for m in info.pv)
    print("%-42s -> %-8s score %+6d d%d n=%d %.2fs" %
          (fen[:42], san, info.score, info.depth, info.nodes, info.time))
    print("    pv:", pv)
    if expect and san != expect:
        print("    (expected %s)" % expect)

# mate-in-1 detection
b = Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
b.make_move(b.find_move("Ra8+"))
print("\nmate position fen:", b.fen())
s = Searcher(ev, tt)
info = s.search(b, 8, TimeManager(60, 0, 40, 2.0, 5.0))
print("finds mate in 1:", b.san(info.best_move), "score", info.score, "mate_in", info.mate_in)

# null-move sanity: tactical position must still be solved
b = Board("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
s = Searcher(ev, tt)
info = s.search(b, 10, TimeManager(60, 0, 40, 3.0, 6.0))
print("Scholar-ish position best:", b.san(info.best_move), info.score, "depth", info.depth)
print("nps ~", int(info.nodes / max(info.time, 1e-6)))
