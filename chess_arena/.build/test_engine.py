"""Stdlib regression suite: python3 .build/test_engine.py."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chess_arena import (Board, Evaluator, Searcher, TranspositionTable, TimeManager,
                         SearchTimeout, START_FEN, WHITE, BLACK, MATE, MATE_BOUND,
                         mate_distance, parse_square, STYLES)


def snapshot(board):
    return (board.fen(), list(board.sq), board.hash, dict(board.rep),
            list(board.stack), list(board.kings), board.ep)


class RulesTests(unittest.TestCase):
    def test_start_perft(self):
        board = Board()
        before = snapshot(board)
        self.assertEqual(board.perft(3), 8902)
        self.assertEqual(snapshot(board), before)

    def test_hash_distinguishes_ranks(self):
        a = Board('7k/8/8/8/8/8/P7/7K w - - 0 1')
        b = Board('7k/8/8/8/8/P7/8/7K w - - 0 1')
        self.assertNotEqual(a.hash, b.hash)

    def test_incremental_hash_and_clone(self):
        rng = random.Random(7)
        board = Board()
        before = snapshot(board)
        made = 0
        for _ in range(70):
            legal = board.legal_moves()
            if not legal:
                break
            board.make_move(rng.choice(legal))
            made += 1
            self.assertEqual(board.hash, board.compute_hash())
            clone = board.clone()
            clone.legal_moves()  # missing defaultdict must not raise KeyError
            self.assertEqual(clone.hash, board.hash)
        for _ in range(made):
            board.unmake_move()
            self.assertEqual(board.hash, board.compute_hash())
        self.assertEqual(snapshot(board), before)

    def test_repetition_ignores_unusable_ep(self):
        board = Board()
        board.make_move(board.find_move('e4'))
        same = Board(board.fen())
        self.assertEqual(board.key(), same.key())
        for _ in range(2):
            for uci in ('g8f6', 'g1f3', 'f6g8', 'f3g1'):
                board.make_move(board.find_move(uci))
        self.assertEqual(board.outcome()['termination'], 'threefold repetition')

    def test_pinned_en_passant(self):
        board = Board('k3r3/8/8/3pP3/8/8/8/4K3 w - d6 0 1')
        self.assertIsNone(board.find_move('e5d6'))
        self.assertEqual(board.usable_ep(), -1)
        self.assertEqual(board.hash, Board(board.fen()).hash)

    def test_material_draws(self):
        for fen in ('7k/8/8/8/8/8/8/K7 w - - 0 1',
                    '7k/8/8/8/8/8/8/KB6 w - - 0 1',
                    '7k/8/8/8/8/8/8/KN6 w - - 0 1'):
            board = Board(fen)
            self.assertTrue(board.insufficient_material())
            self.assertEqual(board.outcome()['result'], '1/2-1/2')
        for fen in ('7k/8/8/8/8/8/8/KBB5 w - - 0 1',
                    '7k/8/8/8/8/8/8/KBN5 w - - 0 1',
                    '7k/8/8/8/8/8/8/KNN5 w - - 0 1'):
            self.assertFalse(Board(fen).insufficient_material())

    def test_bad_fen(self):
        for fen in ('', '8/8', START_FEN.replace(' w ', ' x '),
                    START_FEN.replace('pppppppp', 'ppppppp'),
                    START_FEN.replace('pppppppp', '9'),
                    START_FEN.replace(' 0 1', ' -1 0'),
                    START_FEN.replace(' - ', ' z9 ')):
            with self.subTest(fen=fen), self.assertRaises(ValueError):
                Board(fen)
        for square in ('a9', 'i1', '', 'a10'):
            with self.assertRaises(ValueError):
                parse_square(square)

    def test_special_move_roundtrips(self):
        for fen, move in [('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1', 'O-O'),
                          ('7k/P7/8/8/8/8/8/7K w - - 0 1', 'a7a8n'),
                          ('7k/8/8/3pP3/8/8/8/7K w - d6 0 1', 'e5d6')]:
            board = Board(fen)
            before = snapshot(board)
            found = board.find_move(move)
            self.assertIsNotNone(found)
            board.make_move(found)
            self.assertEqual(board.hash, board.compute_hash())
            board.unmake_move()
            self.assertEqual(snapshot(board), before)


class SearchTests(unittest.TestCase):
    def search(self, board, depth=3, seconds=3):
        searcher = Searcher(Evaluator(), TranspositionTable())
        before = snapshot(board)
        info = searcher.search(board, depth, TimeManager(60, 0, 30, seconds, seconds))
        self.assertEqual(snapshot(board), before)
        return info

    def test_styles(self):
        for style in STYLES:
            self.assertIsInstance(Evaluator(style).evaluate(Board()), int)

    def test_mate_for_both_colors(self):
        for fen in ('7k/8/5KQ1/8/8/8/8/8 w - - 0 1',
                    '8/8/8/8/8/5kq1/8/7K b - - 0 1'):
            board = Board(fen)
            info = self.search(board)
            self.assertGreater(info.score, MATE_BOUND)
            board.make_move(info.best_move)
            self.assertEqual(board.outcome()['termination'], 'checkmate')
            self.assertEqual(info.mate_in, 1)
        self.assertEqual(mate_distance(-MATE + 2), -1)

    def test_terminal_scores(self):
        board = Board('7k/6Q1/5K2/8/8/8/8/8 b - - 100 1')
        info = self.search(board)
        self.assertIsNone(info.best_move)
        self.assertEqual(info.score, -MATE)
        board = Board('7k/5K2/6Q1/8/8/8/8/8 b - - 0 1')
        info = self.search(board)
        self.assertIsNone(info.best_move)
        self.assertEqual(info.score, 0)

    def test_capture_free_queen(self):
        board = Board('7k/8/8/8/8/4q3/4R3/7K w - - 0 1')
        info = self.search(board, 2)
        self.assertEqual(board.uci(info.best_move), 'e2e3')

    def test_timeout_restores_every_ply(self):
        board = Board()
        before = snapshot(board)
        searcher = Searcher(Evaluator(), TranspositionTable())
        def abort():
            if searcher.nodes > 80:
                raise SearchTimeout()
        searcher._check_time = abort
        info = searcher.search(board, 10, TimeManager(60, 0, 30, 3, 3))
        self.assertIn(info.best_move, board.legal_moves())
        self.assertEqual(snapshot(board), before)

    def test_pv_and_callback_are_snapshots(self):
        board = Board()
        updates = []
        searcher = Searcher(Evaluator(), TranspositionTable())
        info = searcher.search(board, 2, TimeManager(60, 0, 30, 3, 3), updates.append)
        self.assertGreaterEqual(info.depth, 1)
        if len(updates) > 1:
            self.assertIsNot(updates[0], updates[1])
            self.assertEqual(updates[0].depth, 1)
        for move in info.pv:
            self.assertIn(move, board.legal_moves())
            board.make_move(move)

    def test_quiescence_uses_legal_evasions(self):
        board = Board('4k3/8/8/8/8/8/4r3/4K3 w - - 0 1')
        before = snapshot(board)
        searcher = Searcher(Evaluator(), TranspositionTable())
        searcher.board = board
        score = searcher.quiesce(-32000, 32000, 0)
        self.assertEqual(score, 0)  # Kxe2 leaves bare kings
        self.assertEqual(snapshot(board), before)


if __name__ == '__main__':
    unittest.main()
