"""Stdlib-only records/analysis regression tests against concatenated fragments.

Run from any directory: python3 chess_arena/.build/test_records.py
This imports fragments in memory, without rebuilding/editing chess_arena.py.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock
import warnings

HERE = Path(__file__).resolve().parent
arena = types.ModuleType("_records_test_arena")
sys.modules[arena.__name__] = arena
source = "\n".join(path.read_text(encoding="utf-8") for path in sorted(HERE.glob("p*.py"))
                   if path.name < "p11")
exec(compile(source, str(HERE / "<records-fragments>"), "exec"), arena.__dict__)


class RecordTests(unittest.TestCase):
    def test_default_lists_are_not_shared(self):
        first, second = arena.GameRecord(), arena.GameRecord()
        first.moves.append("e2e4")
        first.headers["White"] = "A"
        self.assertEqual(second.moves, [])
        self.assertEqual(second.headers, {})

    def test_export_parse_replay(self):
        record = arena.GameRecord(moves=["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"],
                                  headers={"White": 'A "quoted" \\ player', "Black": "Zoë"},
                                  result="1-0", termination="resignation")
        parsed = arena.parse_pgn(arena.export_pgn(record))
        self.assertEqual(parsed.moves, record.moves)
        self.assertEqual(parsed.result, "1-0")
        self.assertEqual(parsed.termination, "resignation")
        self.assertEqual(parsed.headers["White"], record.headers["White"])
        self.assertEqual(parsed.replay().fen(), record.replay().fen())

    def test_nested_variations_comments_nags_and_annotations(self):
        text = ('% escape line\n[Event "Test"]\n\n'
                '1.e4{mainline}(1.d4 d5 (1...Nf6 {ignore ) here})) e5$1\n'
                '2.Nf3!? Nc6; a comment with ( and {\n3.Bb5 a6 * {ending}')
        result = arena.parse_pgn(text)
        self.assertEqual(result.moves, ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6"])

    def test_black_start_and_castling(self):
        fen = "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 12"
        text = '[SetUp "1"]\n[FEN "%s"]\n12...0-0 13.O-O-O *' % fen
        record = arena.parse_pgn(text)
        self.assertEqual(record.moves, ["e8g8", "e1c1"])
        exported = arena.export_pgn(record)
        self.assertIn("12... O-O", exported)
        self.assertEqual(arena.parse_pgn(exported).start_fen, fen)
        self.assertEqual(arena.parse_pgn(exported).moves, record.moves)

    def test_promotion_and_en_passant(self):
        promotion = '[FEN "4k3/P7/8/8/8/8/8/4K3 w - - 0 1"]\n1.a8=Q+ *'
        self.assertEqual(arena.parse_pgn(promotion).moves, ["a7a8q"])
        ep = '[FEN "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"]\n2.exd6 *'
        record = arena.parse_pgn(ep)
        self.assertEqual(record.moves, ["e5d6"])
        self.assertEqual(record.replay().sq[arena.parse_square("d5")], arena.EMPTY)

    def test_san_disambiguation(self):
        header = '[FEN "4k3/8/8/8/8/8/8/1N2KN2 w - - 0 1"]\n'
        self.assertEqual(arena.parse_pgn(header + "1.Nbd2 *").moves, ["b1d2"])
        with self.assertRaises(ValueError):
            arena.parse_pgn(header + "1.Nd2 *")

    def test_mate_result_validation(self):
        mate = "1.f3 e5 2.g4 Qh4# 0-1"
        self.assertTrue(arena.parse_pgn(mate).replay().in_check())
        with self.assertRaises(ValueError):
            arena.parse_pgn(mate.replace("0-1", "1-0"))

    def test_reject_malformed_and_unrecognized_input(self):
        texts = ["", "1.e4 e5", "1.e5 *", "1.e4+ *", "1.e4 * garbage", "1.e4 * 1.d4 *",
                 "1.e4 {oops *", "1.e4 (1.d4 *", "1.e4 ) *", "1.e4 } *", "1.e4 {x {y}} *",
                 "1.e4 2.e5 *", "1...e4 *", "1.e4 1... *", "1.e4 $256 *", "1.e4 $x *",
                 "1.e4 g7g6 *", "1.e4 nonsense *", "[Event nope]\n*", '[Event "x\\q"]\n*',
                 '[Event "a"] [Event "b"] *', '[Variant "Chess960"] *', '[SetUp "1"] *',
                 '[Result "win"] *', '[Result "1-0"] 1.e4 *', '(1.d4) 1.e4 *', '* (1.e4)',
                 '[FEN "8/8/8/8/8/8/8/8 w - - 0 1"] *']
        for text in texts:
            with self.subTest(text=text), self.assertRaises(ValueError):
                arena.parse_pgn(text)

    def test_replay_rejects_illegal_uci(self):
        for moves in (["e2e5"], ["e2e4", "e2e3"], ["e4"], ["e2e4q"], [None]):
            with self.subTest(moves=moves), self.assertRaises(ValueError):
                arena.GameRecord(moves=moves).replay()

    def test_bad_fen_is_rejected(self):
        fens = ["", "8/8/8/8/8/8/8/K6k w - - 0", "8/8/8/8/8/8/8/K6k x - - 0 1",
                "8/8/8/8/8/8/8/K6k w - - -1 1", "8/8/8/8/8/8/8/K6k w - - 0 0",
                "8/8/8/8/8/8/8/K6k w K - 0 1", "8/8/8/8/8/8/8/K6k w - d6 0 1",
                "8/8/8/8/8/8/8/K5kk w - - 0 1", "8/8/8/8/8/8/8/Kk6 w - - 0 1",
                "4k3/8/8/8/8/8/8/K6P w - - 0 1", "4k3/8/8/8/8/8/8/K7q w - - 0 1",
                "4k3/8/8/8/8/8/8/K34 w - - 0 1", "4k3/8/8/8/8/8/8/K3R3 w - - 0 1"]
        for fen in fens:
            with self.subTest(fen=fen), self.assertRaises(ValueError):
                arena.GameRecord(start_fen=fen).replay()

    def test_annotation_export_cannot_inject_movetext(self):
        record = arena.GameRecord(moves=["e2e4"])
        report = {"moves": [{"ply": 1, "grade": "good", "loss_cp": 12,
                              "best": "d4", "hint": "} 0-1 {\ntry this"}]}
        result = arena.parse_pgn(arena.export_pgn(record, report))
        self.assertEqual(result.moves, record.moves)
        self.assertEqual(result.result, "*")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = arena.Store(self.temp.name)

    def test_default_directory(self):
        with mock.patch.dict(os.environ, {"HOME": self.temp.name}):
            store = arena.Store()
            self.assertEqual(store.data_dir, os.path.join(self.temp.name, ".chess_arena"))

    def test_profile_roundtrip(self):
        self.assertEqual(self.store.load_profile()["games_played"], 0)
        profile = {"name": "Zoë", "games_played": 3, "settings": {"style": "balanced"}, "history": [1, None, True]}
        self.store.save_profile(profile)
        self.assertEqual(arena.Store(self.temp.name).load_profile(), profile)
        path = Path(self.temp.name) / "profile.json"
        self.assertEqual(json.loads(path.read_text()), profile)

    def test_invalid_json_data_leaves_profile_unchanged(self):
        self.store.save_profile({"name": "saved"})
        for invalid in ({"x": float("nan")}, {"x": float("inf")}, {"x": object()}, {1: "x"}, []):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.store.save_profile(invalid)
        self.assertEqual(self.store.load_profile(), {"name": "saved"})

    def test_corrupt_profile_warns_and_is_preserved(self):
        path = Path(self.temp.name) / "profile.json"
        for text in ("not JSON", "[]", '{"x": NaN}', '{"x": 1, "x": 2}'):
            path.write_text(text)
            with self.subTest(text=text), self.assertWarns(RuntimeWarning):
                self.assertEqual(self.store.load_profile()["games_played"], 0)
            self.assertEqual(path.read_text(), text)
        self.assertEqual(len(self.store.warnings), 4)

    def test_atomic_failure_preserves_old_file_and_cleans_temp(self):
        self.store.save_profile({"saved": True})
        with mock.patch.object(arena.os, "replace", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                self.store.save_profile({"saved": False})
        self.assertEqual(self.store.load_profile(), {"saved": True})
        self.assertEqual(list(Path(self.temp.name).glob(".tmp-*")), [])

    def test_archive_history_and_weighted_book_survive_restart(self):
        win = arena.GameRecord(moves=["e2e4", "e7e5"], result="1-0", termination="resignation")
        draw = arena.GameRecord(moves=["d2d4", "d7d5"], result="1/2-1/2", termination="agreement")
        identifiers = {self.store.archive(win), self.store.archive(draw)}
        restarted = arena.Store(self.temp.name)
        entries = restarted.history()
        self.assertEqual({entry["id"] for entry in entries}, identifiers)
        self.assertEqual({entry["result"] for entry in entries}, {"1-0", "1/2-1/2"})
        json.dumps(entries, allow_nan=False)
        stats = restarted.opening_stats()
        self.assertEqual(stats["games"], 2)
        root = restarted._book_key(arena.Board())
        self.assertEqual(stats["positions"][root]["e2e4"]["wins"], 1)
        black_board = arena.GameRecord(moves=["e2e4"]).replay()
        black_key = restarted._book_key(black_board)
        self.assertEqual(stats["positions"][black_key]["e7e5"]["losses"], 1)
        board = arena.Board()
        self.assertEqual(board.uci(restarted.choose_book_move(board)), "e2e4")

    def test_unfinished_games_are_not_winning_evidence(self):
        self.store.archive(arena.GameRecord(moves=["e2e4"]))
        self.assertIsNone(self.store.choose_book_move(arena.Board()))

    def test_corrupt_archive_is_explicitly_skipped(self):
        good_id = self.store.archive(arena.GameRecord(moves=["e2e4"]))
        bad = Path(self.store.archive_dir) / ("f" * 32 + ".json")
        bad.write_text('{"id":"bad"}')
        with self.assertWarns(RuntimeWarning):
            history = self.store.history()
        self.assertEqual([entry["id"] for entry in history], [good_id])
        self.assertTrue(bad.exists())

    def test_corrupt_book_rebuilds_from_valid_archives(self):
        self.store.archive(arena.GameRecord(moves=["e2e4"], result="1-0"))
        (Path(self.temp.name) / "openings.json").write_text("broken")
        with self.assertWarns(RuntimeWarning):
            stats = self.store.opening_stats()
        self.assertEqual(stats["games"], 1)
        self.assertEqual(stats["positions"][self.store._book_key(arena.Board())]["e2e4"]["wins"], 1)


class AnalysisTests(unittest.TestCase):
    def test_cancel_before_start(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(arena.SearchTimeout):
            arena.analyze_game(arena.GameRecord(), cancel=event)

    def test_cancel_from_progress_and_node_check(self):
        event = threading.Event()
        with self.assertRaises(arena.SearchTimeout):
            arena.analyze_game(arena.GameRecord(moves=["e2e4"]), cancel=event,
                               on_progress=lambda done, total: event.set())
        searcher = arena._AnalysisSearcher(event)
        with self.assertRaises(arena.SearchTimeout):
            searcher._check_time()

    def test_parameter_validation(self):
        for seconds, depth in ((0, 3), (-1, 3), (float("nan"), 3), (True, 3), (0.1, 0), (0.1, 2.5)):
            with self.subTest(seconds=seconds, depth=depth), self.assertRaises(ValueError):
                arena.analyze_game(arena.GameRecord(), seconds=seconds, depth=depth)

    def test_empty_report_is_json_and_no_calibration_claims(self):
        calls = []
        report = arena.analyze_game(arena.GameRecord(), on_progress=lambda done, total: calls.append((done, total)))
        self.assertEqual(calls, [(0, 0)])
        self.assertEqual(report["moves"], [])
        self.assertIsNone(report["summary"]["mean_loss_cp"])
        self.assertNotIn("accuracy", report["summary"])
        self.assertNotIn("elo", report["summary"])
        json.dumps(report, allow_nan=False)

    def test_centipawn_signs_for_both_colors(self):
        # At both mover roots, +100; opponent after move +150 => mover -150,
        # a loss of 250. White-centric displays must invert on Black's ply.
        call_count = 0
        def probe(searcher, board, depth, seconds, cancel):
            nonlocal call_count
            before = call_count % 2 == 0
            call_count += 1
            best = board.find_move("d2d4" if board.side == arena.WHITE else "d7d5") if before else board.legal_moves()[0]
            return {"score": 100 if before else 150, "depth": 2 if before else 1,
                    "best_move": best, "nodes": 10, "exact": False}
        calls = []
        with mock.patch.object(arena, "_analysis_search", side_effect=probe):
            report = arena.analyze_game(arena.GameRecord(moves=["e2e4", "e7e5"]),
                                        on_progress=lambda done, total: calls.append((done, total)))
        white, black = report["moves"]
        self.assertEqual([white["loss_cp"], black["loss_cp"]], [250, 250])
        self.assertEqual([white["score_before_white_cp"], black["score_before_white_cp"]], [100, -100])
        self.assertEqual([white["score_after_white_cp"], black["score_after_white_cp"]], [-150, 150])
        self.assertEqual(calls, [(0, 2), (1, 2), (2, 2)])
        self.assertEqual(report["summary"]["phases"]["opening"]["plies"], 2)
        json.dumps(report, allow_nan=False)

    def test_mate_scores_not_averaged_as_centipawns(self):
        board = arena.Board()
        before = {"score": arena.MATE - 3, "depth": 3, "best_move": board.find_move("d2d4"), "nodes": 10, "exact": False}
        after = {"score": 20, "depth": 2, "best_move": None, "nodes": 10, "exact": False}
        with mock.patch.object(arena, "_analysis_search", side_effect=[before, after]):
            report = arena.analyze_game(arena.GameRecord(moves=["e2e4"]))
        row = report["moves"][0]
        self.assertTrue(row["possible_missed_mate"])
        self.assertEqual(row["grade"], "possible missed mate")
        self.assertIsNone(row["loss_cp"])
        self.assertIsNone(report["summary"]["mean_loss_cp"])

    def test_terminal_mate_sign(self):
        board = arena.parse_pgn("1.f3 e5 2.g4 Qh4# 0-1").replay()
        found = arena._analysis_search(arena._AnalysisSearcher(None), board, 2, 0.02, None)
        self.assertEqual(found["score"], -arena.MATE)
        self.assertTrue(found["exact"])

    def test_real_engine_smoke_and_progress(self):
        record = arena.GameRecord(moves=["e2e4", "e7e5"])
        expected = record.replay().fen()
        started = time.monotonic()
        report = arena.analyze_game(record, seconds=0.03, depth=1)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(len(report["moves"]), 2)
        for row in report["moves"]:
            for key in ("ply", "san", "best", "loss_cp", "grade", "hint"):
                self.assertIn(key, row)
        self.assertEqual(record.replay().fen(), expected)
        json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
