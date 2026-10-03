#!/usr/bin/env python3
"""Nexus Chess — a single-file desktop chess studio (Python 3.10+).

Setup and launch:
    python -m pip install "python-chess>=1.999,<2"
    python chess_game.py

Tkinter is included in most Windows/macOS Python installers. On Debian/Ubuntu:
    sudo apt install python3-tk
A graphical desktop is required (or Xvfb for GUI tests). No network is used by
this app. No engine executable, images, or other source files are needed.

Modes: Human vs AI, AI vs AI, Human vs Human. Includes legal-move highlighting,
promotions, undo, pause, hints, board rotation, PGN import/export, history/replay,
and bounded, cancellable match analysis. The built-in AI and review scores are
practice-level heuristics, NOT Stockfish, an Elo rating, or calibrated accuracy.

SQLite stores unfinished games, settings, completed games, and a result-weighted
opening memory in ~/.nexus_chess/chess.sqlite3. Override with --data-dir PATH.
Only this .py file is needed to distribute the app; data is created at runtime.
The memory learns opening preferences, not neural-network weights. Games are
untimed. Threefold/50-move draws can be claimed; fivefold/75-move draws are
automatic, following python-chess rules.

Architecture in this file: persistence -> search/analysis -> game model -> GUI.
Workers only send queue messages; every Tk operation runs on the UI thread.
Run --self-test for headless rules, engine, persistence, PGN, and analysis checks.
Run --gui-test under a display or Xvfb for a real Tk integration smoke test.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import math
import queue
import random
import re
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import chess
    import chess.pgn
except ImportError:
    raise SystemExit(
        'Missing dependency. Run:\n  python -m pip install "python-chess>=1.999,<2"'
    )

APP_NAME = "Nexus Chess"
MODES = ("Human vs AI", "AI vs AI", "Human vs Human")
LEVELS = {"Easy": (0.15, 2), "Balanced": (0.65, 4), "Strong": (2.0, 7)}
DEFAULT_SETTINGS = {"mode": MODES[0], "human": "White", "level": "Balanced",
                    "flipped": False, "memory": True}
PIECE_VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 335,
                chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


def timestamp() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


class _StrictPGNBuilder(chess.pgn.GameBuilder):
    def handle_error(self, error: Exception) -> None:
        raise ValueError(f"Invalid PGN: {error}")


def parse_pgn(text: str) -> chess.pgn.Game:
    """Validate tokens as well as legality: python-chess ignores unknown text."""
    if not text.strip():
        raise ValueError("The PGN is empty.")
    stream = io.StringIO(text)
    game = chess.pgn.read_game(stream, Visitor=_StrictPGNBuilder)
    first_game = text[:stream.tell()]
    tokens = re.compile(r'''\s+|;[^\n]*|%[^\n]*|\{[^}]*\}|
        \[[A-Za-z0-9_]+\s+"(?:[^"\\]|\\.)*"\s*\]|
        1/2-1/2|1-0|0-1|\*|\$\d+|\d+\.(?:\.\.)?|\.\.\.|[()]|
        (?:[O0]-[O0](?:-[O0])?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=?[QRBN])?)[+#]{0,2}[!?]*|
        [!?]{1,2}|e\.p\.
        ''', re.VERBOSE)
    offset = 0
    while offset < len(first_game):
        match = tokens.match(first_game, offset)
        if match is None:
            excerpt = first_game[offset:offset+35].splitlines()[0]
            raise ValueError(f"Unrecognized PGN text near: {excerpt!r}")
        offset = match.end()
    if game is not None and not game.variations and not text.lstrip().startswith("[") and text.strip() not in ("*", "1-0", "0-1", "1/2-1/2"):
        raise ValueError("No chess moves or PGN headers found.")
    if game is None or game.errors:
        raise ValueError("Invalid PGN: " + (str(game.errors[0]) if game and game.errors else "no game found"))
    board = game.board()
    if type(board) is not chess.Board or board.chess960:
        raise ValueError("Only standard chess PGNs are supported (not variants or Chess960).")
    if not board.is_valid():
        raise ValueError("The PGN has an invalid starting position.")
    for move in game.mainline_moves():
        if move not in board.legal_moves:
            raise ValueError(f"Illegal move in PGN: {move.uci()}")
        board.push(move)
    return game


class Store:
    """UI-thread-owned SQLite connection; writes are atomic transactions."""

    def __init__(self, directory: Path):
        directory = directory.expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "chess.sqlite3"
        self.db = sqlite3.connect(str(self.path), timeout=3)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY, created TEXT NOT NULL, updated TEXT NOT NULL,
                mode TEXT NOT NULL, result TEXT NOT NULL, reason TEXT NOT NULL,
                pgn TEXT NOT NULL, controls TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS openings (
                game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                ply INTEGER NOT NULL, position TEXT NOT NULL, move TEXT NOT NULL,
                reward REAL NOT NULL, PRIMARY KEY(game_id, ply)
            );
            CREATE INDEX IF NOT EXISTS opening_position ON openings(position);
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(games)")}
        if "controls" not in columns:
            self.db.execute("ALTER TABLE games ADD COLUMN controls TEXT NOT NULL DEFAULT '{}'")
        self.db.execute("PRAGMA user_version=2")
        self.db.commit()

    def get(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        try:
            return json.loads(row[0]) if row else default
        except (TypeError, ValueError):
            return default

    def put(self, key: str, value) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value)))

    def save_session(self, session: "Session", settings: dict) -> None:
        pgn = session.pgn()
        state = {"id": session.id, "created": session.created, "mode": session.mode,
                 "result": session.forced_result, "reason": session.reason,
                 "pgn": pgn, "settings": settings, "controls": session.controls}
        result = session.result()
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES ('session', ?)", (json.dumps(state),))
            self.db.execute("INSERT OR REPLACE INTO kv VALUES ('settings', ?)", (json.dumps(settings),))
            if session.board.move_stack or result != "*":
                # An UPSERT preserves existing foreign-key children; REPLACE
                # would delete them. Rebuild this game's memory deterministically.
                self.db.execute("""INSERT INTO games
                    (id, created, updated, mode, result, reason, pgn, controls)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,
                    mode=excluded.mode, result=excluded.result,
                    reason=excluded.reason, pgn=excluded.pgn, controls=excluded.controls""",
                    (session.id, session.created, timestamp(), session.mode,
                     result, session.reason, pgn, json.dumps(session.controls)))
                self.db.execute("DELETE FROM openings WHERE game_id=?", (session.id,))
                if result != "*":
                    board = session.board.root()
                    # Never confuse a custom starting position with an opening.
                    if board.fen() == chess.Board().fen():
                        for ply, move in enumerate(session.board.move_stack[:16]):
                            reward = 0.5 if result == "1/2-1/2" else float(
                                (result == "1-0") == (board.turn == chess.WHITE))
                            self.db.execute("INSERT INTO openings VALUES (?, ?, ?, ?, ?)",
                                            (session.id, ply, self.position_key(board), move.uci(), reward))
                            board.push(move)
            else:
                self.db.execute("DELETE FROM games WHERE id=?", (session.id,))

    @staticmethod
    def position_key(board: chess.Board) -> str:
        return " ".join(board.fen().split()[:4])

    def book_move(self, board: chess.Board) -> Optional[chess.Move]:
        # At least two observations: a single previous blunder should not
        # override fresh search. Only moves with non-losing evidence qualify.
        if len(board.move_stack) >= 16:
            return None
        rows = self.db.execute("""SELECT move, COUNT(*) AS n, AVG(reward) AS reward
            FROM openings WHERE position=? GROUP BY move
            HAVING COUNT(*) >= 2 AND AVG(reward) >= 0.5""", (self.position_key(board),)).fetchall()
        moves, weights = [], []
        for row in rows:
            try:
                move = chess.Move.from_uci(row["move"])
            except ValueError:
                continue
            if move in board.legal_moves:
                moves.append(move)
                weights.append((row["reward"] + 0.2) * math.log2(row["n"] + 1))
        return random.choices(moves, weights=weights, k=1)[0] if moves else None

    def history(self) -> list:
        return self.db.execute("SELECT * FROM games ORDER BY updated DESC LIMIT 250").fetchall()

    def saved_game(self, game_id: str):
        # Fetch on demand, not from a History window's possibly stale snapshot.
        return self.db.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()

    def stats(self) -> str:
        counts = {row[0]: row[1] for row in self.db.execute(
            "SELECT result, COUNT(*) FROM games GROUP BY result")}
        finished = sum(n for r, n in counts.items() if r != "*")
        positions = self.db.execute("SELECT COUNT(DISTINCT position) FROM openings").fetchone()[0]
        return (f"{finished} completed · {counts.get('*', 0)} unfinished\n"
                f"White {counts.get('1-0', 0)} / Black {counts.get('0-1', 0)} / "
                f"Draw {counts.get('1/2-1/2', 0)}\n{positions} remembered opening positions")

    def close(self) -> None:
        self.db.close()


"""Bounded, pure-Python chess search for hobby/practice, not grandmaster play.

This fragment has no GUI calls, opening book, learned data, or shared engine state.
Use one ChessEngine per worker. Progress callbacks run in the calling thread;
a GUI must marshal them to its UI thread. Cancellation raises SearchCancelled.

Draw policy: automatically accept every available threefold/fifty-move claim,
including a claim by announcing a legal move. Automatic draws and checkmate are
also respected. This policy agrees with Board.outcome(claim_draw=True), rather
than treating an optional draw claim as an extra move in a winning position.
"""

import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Optional

import chess


class SearchCancelled(Exception):
    """The caller cancelled a search or analysis; no partial analysis is returned."""


@dataclass
class SearchResult:
    move: Optional[chess.Move]
    score: int  # Centipawns, always from White's perspective (including mate scores).
    depth: int
    nodes: int
    pv: list[chess.Move]
    elapsed: float


class _ChessSearchLimit(Exception):
    """Internal time/node/ply limit: retain the last fully completed iteration."""


@dataclass
class _ChessTTEntry:
    depth: int
    score: int  # Side-to-move score; mate distance normalized for this position.
    bound: str  # EXACT, LOWER, UPPER
    pv: tuple


class ChessEngine:
    """Iterative alpha-beta/negamax with check-aware quiescence and a bounded TT.

    A time limit can return depth=0: its legal fallback move and static root score
    are NOT a completed search. Only completed iterations reach ``progress``.
    Terminal positions also have depth=0, but return move=None and an exact score.
    Empty root_moves explicitly permits no move and returns an unsearched result.
    Illegal root moves raise ValueError. Restricting root moves never pollutes the
    TT with a restricted root value, and does not override the draw policy.

    Mate scores are +/- (MATE_SCORE - plies to mate), in White's perspective.
    Static evaluation is kept well outside the mate band. Hard resource caps
    bound pathological requests, in addition to the caller's wall-clock budget.
    This class is intentionally not reentrant; give independent callers their
    own instance. A table may be reused for successive searches on one worker.
    """

    MATE_SCORE = 30000
    MATE_THRESHOLD = 29000
    INFINITY = 32000
    MAX_DEPTH = 16
    MAX_PLY = 96
    QUIESCENCE_PLIES = 8
    MAX_NODES = 400000
    MAX_SECONDS = 30.0
    PIECE_VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 335,
                    chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}

    def __init__(self, tt_capacity: int = 12000):
        # Both entry count and searched depth/length are bounded. Zero disables TT.
        self.tt_capacity = max(0, min(int(tt_capacity), 50000))
        self._tt = OrderedDict()
        self._cancel = None
        self._deadline = 0.0
        self._nodes = 0
        self._repetitions = {}
        self._duplicate_positions = 0
        self._killers = {}
        self._history = {}

    @staticmethod
    def evaluate(board: chess.Board) -> int:
        """Static White-centric centipawns, not a searched or terminal score.

        Material, modest piece-square/mobility terms, pawn structure, bishop pair,
        rook files, and phase-dependent king placement. Search handles draws and
        mates separately. This function does not push/pop or modify the board.
        """
        values = ChessEngine.PIECE_VALUES
        phase = min(24, sum(len(board.pieces(piece, color)) * weight
                            for color in chess.COLORS
                            for piece, weight in ((chess.KNIGHT, 1), (chess.BISHOP, 1),
                                                  (chess.ROOK, 2), (chess.QUEEN, 4))))
        score = 0
        for color in chess.COLORS:
            own = board.occupied_co[color]
            own_pawns = board.pieces_mask(chess.PAWN, color)
            enemy_pawns = board.pieces_mask(chess.PAWN, not color)
            subtotal = 0
            for piece in chess.PIECE_TYPES:
                squares = board.pieces(piece, color)
                subtotal += len(squares) * values[piece]
                if piece == chess.BISHOP and len(squares) >= 2:
                    subtotal += 28
                for square in squares:
                    file = chess.square_file(square)
                    rank = chess.square_rank(square)
                    relative_rank = rank if color == chess.WHITE else 7 - rank
                    center = 7 - abs(2 * file - 7) - abs(2 * rank - 7)
                    if piece == chess.PAWN:
                        subtotal += 7 * (relative_rank - 1) + 2 * center
                        adjacent = ((chess.BB_FILES[file - 1] if file > 0 else 0) |
                                    (chess.BB_FILES[file + 1] if file < 7 else 0))
                        if not own_pawns & adjacent:
                            subtotal -= 12
                        lane = adjacent | chess.BB_FILES[file]
                        forward = ((chess.BB_ALL << (8 * (rank + 1))) & chess.BB_ALL
                                   if color == chess.WHITE else (1 << (8 * rank)) - 1)
                        if not enemy_pawns & lane & forward:
                            subtotal += 3 * relative_rank * relative_rank
                    elif piece == chess.KNIGHT:
                        subtotal += 7 * center
                        subtotal += 2 * (board.attacks_mask(square) & ~own).bit_count()
                    elif piece == chess.BISHOP:
                        subtotal += 3 * center
                        subtotal += 2 * (board.attacks_mask(square) & ~own).bit_count()
                    elif piece == chess.ROOK:
                        if not own_pawns & chess.BB_FILES[file]:
                            subtotal += 10 if enemy_pawns & chess.BB_FILES[file] else 18
                        subtotal += 12 if relative_rank == 6 else 0
                    elif piece == chess.QUEEN:
                        subtotal += center
                    else:
                        # A sheltered/castled king in middlegames, an active one in endings.
                        middle = -12 * relative_rank
                        middle += 24 if file in (1, 2, 6) and relative_rank == 0 else 0
                        ending = 7 * center
                        subtotal += (middle * phase + ending * (24 - phase)) // 24
            for file_mask in chess.BB_FILES:
                count = (own_pawns & file_mask).bit_count()
                subtotal -= max(0, count - 1) * 12
            score += subtotal if color == chess.WHITE else -subtotal
        return max(-20000, min(20000, int(score)))

    @staticmethod
    def _position_key(board):
        # Public Board fields only; uncapturable EP squares do not affect repetition.
        return (board.pawns, board.knights, board.bishops, board.rooks, board.queens,
                board.kings, board.occupied_co[chess.WHITE], board.occupied_co[chess.BLACK],
                board.turn, board.clean_castling_rights(),
                board.ep_square if board.has_legal_en_passant() else None,
                board.chess960)

    def _check_cancel(self):
        if self._cancel is not None and self._cancel.is_set():
            raise SearchCancelled("Chess operation cancelled")

    def _check_limits(self):
        self._check_cancel()
        if time.monotonic() >= self._deadline or self._nodes >= self.MAX_NODES:
            raise _ChessSearchLimit()

    def _visit(self, ply):
        self._check_limits()
        if ply >= self.MAX_PLY:
            # Never silently stand pat while in check at a hard recursion limit.
            raise _ChessSearchLimit()
        self._nodes += 1

    def _initialize_repetitions(self, board):
        # Keep board's stack; discard only history made irrelevant by an irreversible move.
        history = board.copy(stack=True)
        counts = {self._position_key(history): 1}
        while history.move_stack:
            # Root adjudication must remain correct even with a zero search budget.
            # The reversible suffix is short (the draw clock is checked first).
            self._check_cancel()
            move = history.pop()
            if history.is_irreversible(move):
                break
            key = self._position_key(history)
            counts[key] = counts.get(key, 0) + 1
        self._repetitions = counts
        self._duplicate_positions = sum(count >= 2 for count in counts.values())

    def _push(self, board, move):
        irreversible = board.is_irreversible(move)
        old_counts = self._repetitions if irreversible else None
        old_duplicates = self._duplicate_positions
        board.push(move)
        key = self._position_key(board)
        if irreversible:
            self._repetitions = {key: 1}
            self._duplicate_positions = 0
        else:
            count = self._repetitions.get(key, 0) + 1
            self._repetitions[key] = count
            if count == 2:
                self._duplicate_positions += 1
        return old_counts, old_duplicates, key

    def _pop(self, board, state):
        old_counts, old_duplicates, key = state
        board.pop()
        if old_counts is not None:
            self._repetitions = old_counts
        else:
            count = self._repetitions[key] - 1
            if count:
                self._repetitions[key] = count
            else:
                del self._repetitions[key]
        self._duplicate_positions = old_duplicates

    def _terminal_score(self, board, legal, ply, root_check=False):
        # Checkmate has precedence over the move-count draw rules.
        if not legal:
            return -self.MATE_SCORE + ply if board.is_check() else 0
        if board.is_insufficient_material() or board.halfmove_clock >= 150:
            return 0
        count = self._repetitions.get(self._position_key(board), 0)
        if count >= 3 or board.halfmove_clock >= 100:
            return 0  # Includes automatic fivefold and the always-claim policy.
        if not self._duplicate_positions and board.halfmove_clock < 99:
            return None
        # Claim by announcing a move. Fifty-move claims must not supersede mate.
        # Root adjudication is bounded setup, even if the search budget is zero.
        for move in legal:
            if root_check:
                self._check_cancel()
            else:
                self._check_limits()
            state = self._push(board, move)
            try:
                if self._repetitions.get(state[2], 0) >= 3:
                    return 0
                if board.halfmove_clock >= 100 and any(board.generate_legal_moves()):
                    return 0
            finally:
                self._pop(board, state)
        return None

    def _tt_key(self, board):
        # A position hash alone is UNSOUND for draw-dependent scores. Include the
        # exact reversible history multiset and clock, not a collision-prone hash
        # of history. Different move orders with the same draw context may share.
        return (self._position_key(board), board.halfmove_clock,
                frozenset(self._repetitions.items()))

    def _pack_mate(self, score, ply):
        if score >= self.MATE_THRESHOLD:
            return score + ply
        if score <= -self.MATE_THRESHOLD:
            return score - ply
        return score

    def _unpack_mate(self, score, ply):
        if score >= self.MATE_THRESHOLD:
            return score - ply
        if score <= -self.MATE_THRESHOLD:
            return score + ply
        return score

    def _store(self, key, depth, score, bound, pv, ply):
        if not self.tt_capacity:
            return
        entry = self._tt.get(key)
        if entry is not None and entry.depth > depth:
            return
        self._tt[key] = _ChessTTEntry(depth, self._pack_mate(score, ply), bound, tuple(pv))
        self._tt.move_to_end(key)
        while len(self._tt) > self.tt_capacity:
            self._tt.popitem(last=False)

    def _ordered(self, board, moves, preferred=None, ply=0):
        killers = self._killers.get(ply, ())

        def priority(move):
            if move == preferred:
                return 10000000
            value = 0
            attacker = board.piece_type_at(move.from_square)
            victim = board.piece_type_at(move.to_square)
            if board.is_en_passant(move):
                victim = chess.PAWN
            if victim is not None:
                value += 100000 + 16 * self.PIECE_VALUES[victim] - self.PIECE_VALUES[attacker]
            if move.promotion:
                value += 80000 + self.PIECE_VALUES[move.promotion]
            if not victim and not move.promotion:
                if move in killers:
                    value += 50000 - killers.index(move)
                value += self._history.get((board.turn, move.from_square, move.to_square), 0)
            return value

        return sorted(moves, key=priority, reverse=True)

    def _remember_cutoff(self, board, move, depth, ply):
        if board.is_capture(move) or move.promotion:
            return
        previous = self._killers.get(ply, ())
        self._killers[ply] = (move,) + tuple(m for m in previous if m != move)[:1]
        key = (board.turn, move.from_square, move.to_square)
        self._history[key] = min(20000, self._history.get(key, 0) + depth * depth)

    def _quiescence(self, board, alpha, beta, ply, qply):
        self._visit(ply)
        legal = list(board.generate_legal_moves())
        terminal = self._terminal_score(board, legal, ply)
        if terminal is not None:
            return terminal, []
        in_check = board.is_check()
        if in_check:
            best = -self.INFINITY
            moves = legal  # No stand-pat in check; ALL evasions, including quiet ones.
        else:
            best = self.evaluate(board) * (1 if board.turn == chess.WHITE else -1)
            if best >= beta:
                return best, []
            alpha = max(alpha, best)
            if qply >= self.QUIESCENCE_PLIES:
                return best, []
            moves = [m for m in legal if board.is_capture(m) or m.promotion]
        best_pv = []
        for move in self._ordered(board, moves, ply=ply):
            self._check_limits()
            state = self._push(board, move)
            try:
                child_score, child_pv = self._quiescence(board, -beta, -alpha, ply + 1, qply + 1)
                score = -child_score
            finally:
                self._pop(board, state)
            if score > best:
                best, best_pv = score, [move] + child_pv
            alpha = max(alpha, score)
            if alpha >= beta:
                break
        return best, best_pv

    def _negamax(self, board, depth, alpha, beta, ply):
        if depth <= 0:
            return self._quiescence(board, alpha, beta, ply, 0)
        self._visit(ply)
        legal = list(board.generate_legal_moves())
        terminal = self._terminal_score(board, legal, ply)
        if terminal is not None:
            return terminal, []
        key = self._tt_key(board)
        entry = self._tt.get(key)
        preferred = entry.pv[0] if entry is not None and entry.pv else None
        if entry is not None:
            self._tt.move_to_end(key)
            # Exact depth is deliberate: a deeper heuristic horizon is not an
            # exact bound on a shallower search, and analysis matches horizons.
            if entry.depth == depth:
                score = self._unpack_mate(entry.score, ply)
                if (entry.bound == "EXACT" or
                        (entry.bound == "LOWER" and score >= beta) or
                        (entry.bound == "UPPER" and score <= alpha)):
                    return score, list(entry.pv)
        # Do not narrow this window from TT bounds: fail-high at a narrowed beta
        # must not accidentally be recorded as EXACT in the original window.
        original_alpha, original_beta = alpha, beta
        best, best_pv = -self.INFINITY, []
        for move in self._ordered(board, legal, preferred, ply):
            self._check_limits()
            state = self._push(board, move)
            try:
                child_score, child_pv = self._negamax(board, depth - 1, -beta, -alpha, ply + 1)
                score = -child_score
            finally:
                self._pop(board, state)
            if score > best:
                best, best_pv = score, [move] + child_pv
            alpha = max(alpha, score)
            if alpha >= beta:
                self._remember_cutoff(board, move, depth, ply)
                break
        bound = "UPPER" if best <= original_alpha else "LOWER" if best >= original_beta else "EXACT"
        self._store(key, depth, best, bound, best_pv, ply)
        return best, best_pv

    def _root_search(self, board, moves, depth, preferred):
        self._visit(0)
        alpha = -self.INFINITY
        best, best_pv = -self.INFINITY, []
        for move in self._ordered(board, moves, preferred):
            self._check_limits()
            state = self._push(board, move)
            try:
                child_score, child_pv = self._negamax(board, depth - 1, -self.INFINITY, -alpha, 1)
                score = -child_score
            finally:
                self._pop(board, state)
            if score > best:
                best, best_pv = score, [move] + child_pv
            alpha = max(alpha, score)
        # Root scores are never inserted: a restricted root is not a normal node.
        return best, best_pv

    def search(self, board: chess.Board, seconds: float = 1.0, max_depth: int = 6,
               cancel: Optional[threading.Event] = None,
               progress: Optional[Callable[[SearchResult], None]] = None,
               root_moves: Optional[list[chess.Move]] = None) -> SearchResult:
        started = time.monotonic()
        seconds = float(seconds)
        if not math.isfinite(seconds):
            raise ValueError("seconds must be finite")
        max_depth = max(0, min(int(max_depth), self.MAX_DEPTH))
        self._cancel = cancel
        self._deadline = started + max(0.0, min(seconds, self.MAX_SECONDS))
        self._nodes = 0
        self._killers.clear()
        self._history.clear()
        self._check_cancel()
        work = board.copy(stack=True)
        legal = list(work.generate_legal_moves())
        sign = 1 if work.turn == chess.WHITE else -1
        if root_moves is None:
            allowed = legal
        else:
            allowed = list(dict.fromkeys(root_moves))
            if any(move not in legal for move in allowed):
                raise ValueError("root_moves contains an illegal move")
        if not legal:
            score = -self.MATE_SCORE * sign if work.is_check() else 0
            return SearchResult(None, score, 0, 0, [], time.monotonic() - started)
        if work.is_insufficient_material() or work.halfmove_clock >= 100:
            # This also covers automatic 75-move draws, under our claim policy.
            return SearchResult(None, 0, 0, 0, [], time.monotonic() - started)
        ordered = self._ordered(work, allowed)
        fallback = ordered[0] if ordered else None
        result = SearchResult(fallback, self.evaluate(work), 0, 0,
                              [fallback] if fallback is not None else [], 0.0)
        try:
            self._initialize_repetitions(work)
            terminal = self._terminal_score(work, legal, 0, root_check=True)
            if terminal is not None:
                result = SearchResult(None, terminal * sign, 0, self._nodes, [], 0.0)
            elif allowed:
                for depth in range(1, max_depth + 1):
                    self._check_limits()
                    score, pv = self._root_search(work, allowed, depth, result.move)
                    # No partial-iteration score/PV can escape on a deadline/cancel.
                    self._check_limits()
                    result = SearchResult(pv[0], score * sign, depth, self._nodes,
                                          list(pv), time.monotonic() - started)
                    if progress is not None:
                        progress(SearchResult(result.move, result.score, result.depth,
                                              result.nodes, list(result.pv), result.elapsed))
        except _ChessSearchLimit:
            pass
        self._check_cancel()
        return SearchResult(result.move, result.score, result.depth, self._nodes,
                            list(result.pv), time.monotonic() - started)


def analyze_game(board: chess.Board, seconds_per_position: float,
                 cancel: threading.Event,
                 progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """Analyze the snapshot's move stack, including a nonstandard starting FEN.

    ``seconds_per_position=0.3`` is a practical nominal budget: 40% for the best
    move, 60% for a single-root re-search (hard cap 10 seconds per position).
    The played move is searched FROM THE SAME ROOT to the SAME completed depth,
    not by comparing evaluations with different roots/horizons. If the second
    search cannot finish that depth, retained best-search iterations let us use
    a lower *matching* completed depth. Such rows are marked provisional.

    If neither search completes any common depth, score is a static evaluation
    of the actual resulting position, label says 'Provisional (unsearched)',
    and loss is math.nan (unknown, NOT zero). Such rows are excluded from
    accuracy. Exact policy draws are scored zero. Mate values use the engine's
    +/-30000 centipawn band; they are not literal material advantages.

    Accuracy is a simple 0..100 mean of exp(-loss / 2.5), scaled by 100; it is a
    hobby/practice heuristic, NOT Elo, calibrated accuracy, or playing strength.
    Returns None for a side with no comparable moves. All progress/cancellation
    checks are synchronous in the calling worker, with no Tkinter interaction.
    """
    budget = float(seconds_per_position)
    if not math.isfinite(budget):
        raise ValueError("seconds_per_position must be finite")
    budget = max(0.0, min(10.0, budget))

    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise SearchCancelled("Game analysis cancelled")

    check_cancel()
    snapshot = board.copy(stack=True)
    moves = list(snapshot.move_stack)
    position = snapshot.root()
    engine = ChessEngine()
    rows = []
    accuracies = {"White": [], "Black": []}
    total = len(moves)
    if progress is not None:
        progress(0, total)

    def label_for(loss):
        if loss <= 0.10:
            return "Best"
        if loss <= 0.30:
            return "Excellent"
        if loss <= 0.70:
            return "Good"
        if loss <= 1.50:
            return "Inaccuracy"
        if loss <= 3.00:
            return "Mistake"
        return "Blunder"

    for index, played in enumerate(moves, 1):
        check_cancel()
        if played not in position.legal_moves:
            raise ValueError("Illegal move in game history at ply %d" % index)
        before_fen = position.fen()
        san = position.san(played)
        side = "White" if position.turn == chess.WHITE else "Black"
        sign = 1 if position.turn == chess.WHITE else -1
        completed = {}

        def remember(result):
            completed[result.depth] = result

        best = engine.search(position, seconds=budget * 0.4, max_depth=6,
                             cancel=cancel, progress=remember)
        provisional = False
        comparable = best.depth > 0
        policy_draw = best.move is None and best.score == 0
        if policy_draw:
            actual = best
            loss = 0.0
            label = "Draw (claim policy)"
            comparable = True
        elif comparable and played == best.move:
            actual = best
            loss = 0.0
            label = "Best"
        elif comparable:
            actual = engine.search(position, seconds=budget * 0.6,
                                   max_depth=best.depth, cancel=cancel,
                                   root_moves=[played])
            if actual.depth > 0 and actual.depth in completed:
                provisional = actual.depth < best.depth
                best = completed[actual.depth]
                # Reusing a matching iteration also updates displayed best SAN.
                loss = 0.0 if played == best.move else max(0.0, sign * (best.score - actual.score) / 100.0)
                label = label_for(loss)
            else:
                comparable = False
                loss = math.nan
                label = "Provisional (unsearched)"
        else:
            actual = best
            loss = math.nan
            label = "Provisional (unsearched)"
        check_cancel()
        best_san = position.san(best.move) if best.move is not None else "—"
        best_uci = best.move.uci() if best.move is not None else ""
        # This board belongs solely to analysis, not the supplied board/snapshot.
        position.push(played)
        if comparable:
            score = actual.score / 100.0
            accuracies[side].append(100.0 * math.exp(-loss / 2.5))
            if provisional:
                label += " (provisional, depth %d)" % actual.depth
        else:
            score = ChessEngine.evaluate(position) / 100.0
        rows.append({"ply": index, "san": san, "side": side,
                     "before_fen": before_fen, "after_fen": position.fen(),
                     "best_san": best_san, "best_uci": best_uci,
                     "score": float(score), "loss": float(loss), "label": label})
        if progress is not None:
            progress(index, total)
    check_cancel()

    def accuracy(side):
        values = accuracies[side]
        return round(sum(values) / len(values), 1) if values else None

    return {"rows": rows, "white_accuracy": accuracy("White"),
            "black_accuracy": accuracy("Black")}



class Session:
    """Authoritative game state, independent of Tk and worker threads."""

    def __init__(self, mode: str = MODES[0]):
        self.id = uuid.uuid4().hex
        self.created = timestamp()
        self.mode = mode
        self.controls = {"mode": mode, "human": "White", "level": "Balanced"}
        self.board = chess.Board()
        self.headers = {"Event": "Nexus Chess local match", "Site": "Local",
                        "Date": dt.datetime.now().strftime("%Y.%m.%d"),
                        "White": "Nexus AI (Balanced)" if mode == "AI vs AI" else "Human",
                        "Black": "Human" if mode == "Human vs Human" else "Nexus AI (Balanced)"}
        self.forced_result = "*"
        self.reason = ""

    @classmethod
    def from_pgn(cls, text: str, mode: str = "Human vs Human") -> "Session":
        game = parse_pgn(text)
        session = cls(mode)
        session.headers = dict(game.headers)
        # Migration for older history without explicit controller settings.
        for side in ("White", "Black"):
            player = session.headers.get(side, "")
            if player.startswith("Nexus AI"):
                if mode == "Human vs AI":
                    session.controls["human"] = "Black" if side == "White" else "White"
                strength = player.partition("(")[2].rstrip(")")
                if strength in LEVELS:
                    session.controls["level"] = strength
        session.board = game.end().board()
        result = game.headers.get("Result", "*")
        if result not in ("*", "1-0", "0-1", "1/2-1/2"):
            raise ValueError("Invalid PGN result.")
        session.forced_result = result
        session.reason = "Imported result" if result != "*" else ""
        session.update_outcome()
        return session

    @classmethod
    def restore(cls, data: dict) -> "Session":
        if not isinstance(data, dict):
            raise ValueError("Invalid session data")
        session = cls.from_pgn(data["pgn"], data.get("mode", MODES[0]))
        session.id = str(data["id"])
        session.created = str(data["created"])
        session.reason = str(data.get("reason", ""))
        session.restore_controls(data.get("controls"))
        return session

    def restore_controls(self, controls) -> None:
        if isinstance(controls, dict):
            for key, options in (("mode", MODES), ("human", ("White", "Black")), ("level", LEVELS)):
                if controls.get(key) in options:
                    self.controls[key] = controls[key]
        self.mode = self.controls["mode"]

    def update_outcome(self) -> None:
        outcome = self.board.outcome()
        if outcome:
            self.forced_result = outcome.result()
            self.reason = outcome.termination.name.replace("_", " ").title()

    def result(self) -> str:
        outcome = self.board.outcome()
        return outcome.result() if outcome else self.forced_result

    def play(self, move: chess.Move) -> str:
        if self.result() != "*" or move not in self.board.legal_moves:
            raise ValueError("That move is not legal in the current game.")
        san = self.board.san(move)
        self.board.push(move)
        self.update_outcome()
        return san

    def pgn(self) -> str:
        game = chess.pgn.Game.from_board(self.board)
        game.headers.update({k: v for k, v in self.headers.items() if k not in ("FEN", "SetUp", "Result", "Termination")})
        game.headers["Result"] = self.result()
        if self.reason:
            game.headers["Termination"] = self.reason
        return game.accept(chess.pgn.StringExporter(headers=True, variations=False, comments=False)) + "\n"

    def timeline(self) -> list[tuple[chess.Board, str]]:
        board = self.board.root()
        positions = [(board.copy(), "Starting position")]
        for move in self.board.move_stack:
            label = f"{board.fullmove_number}{'.' if board.turn else '...'} {board.san(move)}"
            board.push(move)
            # Replay needs only the current state plus its last move for a
            # highlight. Full stacks at every ply would consume O(n²) memory.
            positions.append((board.copy(stack=1), label))
        return positions


def load_tk() -> None:
    global tk, ttk, filedialog, messagebox
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except ImportError:
        raise SystemExit("Tkinter is missing. Install python3-tk on Linux, or use a Python installer with Tcl/Tk.")


class ChessApp:
    BG, PANEL, CARD = "#111820", "#1a2631", "#243442"
    TEXT, MUTED, GOLD, GREEN, RED = "#edf1f5", "#a9b7c4", "#e6b66e", "#83cfac", "#f19388"

    def __init__(self, root, store: Store):
        self.root, self.store = root, store
        root.title("Nexus Chess — play · learn · review")
        root.geometry("1240x880")
        root.minsize(1020, 760)
        root.configure(bg=self.BG)
        self.closed = False
        self.storage_error_shown = False
        self.unsaved = False
        self.messages = queue.Queue()
        self.jobs: dict[str, tuple[int, threading.Event, threading.Thread]] = {}
        self.job_serial = 0
        self.ai_pending = None
        self.after_poll = None
        self.analysis_window = None
        self.selected = None
        self.hint_move = None
        self.review_ply: Optional[int] = None
        self.analysis_rows = []
        settings = store.get("settings", {})
        settings = settings if isinstance(settings, dict) else {}
        self.mode = tk.StringVar(value=settings.get("mode") if settings.get("mode") in MODES else MODES[0])
        self.human = tk.StringVar(value=settings.get("human") if settings.get("human") in ("White", "Black") else "White")
        self.level = tk.StringVar(value=settings.get("level") if settings.get("level") in LEVELS else "Balanced")
        self.use_memory = tk.BooleanVar(value=bool(settings.get("memory", True)))
        self.flipped = bool(settings.get("flipped", False))
        self.session = Session(self.mode.get())
        restored, restore_error = False, None
        state = store.get("session")
        if state:
            try:
                self.session = Session.restore(state)
                if self.session.result() == "*":
                    self.mode.set(self.session.controls["mode"])
                    self.human.set(self.session.controls["human"])
                    self.level.set(self.session.controls["level"])
                restored = True
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                restore_error = str(exc)
        self.paused = restored or self.mode.get() == "AI vs AI"
        self.status = tk.StringVar()
        self.detail = tk.StringVar(value="Session restored — press Resume." if restored else "Click a piece, then a highlighted square.")
        self.eval_text = tk.StringVar(value="Static evaluation · +0.00")
        self.stats_text = tk.StringVar(value=store.stats())
        self.review_text = tk.StringVar(value="Live position")
        self.build_ui()
        self.bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.after_poll = self.root.after(60, self.poll_messages)
        if restore_error:
            self.root.after(200, lambda: messagebox.showwarning("Saved session", "Could not restore the saved session. History is unchanged.\n" + restore_error, parent=self.root))
        if not restored:
            self.update_players()
            self.refresh(rebuild=False)
        self.schedule_ai()

    def settings(self) -> dict:
        return {"mode": self.mode.get(), "human": self.human.get(), "level": self.level.get(),
                "flipped": self.flipped, "memory": self.use_memory.get()}

    def persist(self) -> bool:
        try:
            self.store.save_session(self.session, self.settings())
            self.stats_text.set(self.store.stats())
            self.unsaved = self.storage_error_shown = False
            return True
        except (OSError, sqlite3.Error) as exc:
            self.unsaved = True
            self.detail.set("Warning: unable to save. Export PGN to protect this game.")
            if not self.storage_error_shown:
                self.storage_error_shown = True
                messagebox.showwarning("Persistence unavailable", str(exc), parent=self.root)
            return False

    def build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("TButton", background=self.CARD, foreground=self.TEXT, padding=(9, 6), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#355169")], foreground=[("disabled", "#788a9a")])
        style.configure("Gold.TButton", background=self.GOLD, foreground=self.BG)
        style.map("Gold.TButton", background=[("active", "#f4ce93")])
        style.configure("TCombobox", fieldbackground=self.CARD, background=self.CARD, foreground=self.TEXT, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", self.CARD)], foreground=[("readonly", self.TEXT)])
        style.configure("TNotebook", background=self.PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.CARD, foreground=self.TEXT, padding=(12, 7))
        style.map("TNotebook.Tab", background=[("selected", "#3c5263")])
        style.configure("Treeview", background=self.PANEL, fieldbackground=self.PANEL, foreground=self.TEXT,
                        rowheight=27, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=self.CARD, foreground=self.TEXT, font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#46647a")], foreground=[("selected", "white")])
        self.root.option_add("*TCombobox*Listbox.background", self.CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", self.TEXT)
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(header, text="♞  NEXUS CHESS", bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI", 24, "bold")).pack(side="left")
        tk.Label(header, text="LOCAL PLAY  /  PERSISTENT MEMORY  /  MATCH REVIEW",
                 bg=self.BG, fg=self.MUTED, font=("Segoe UI", 9)).pack(side="right")
        main = ttk.Frame(outer)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=0, minsize=364)
        main.rowconfigure(0, weight=1)
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        self.top_player = tk.Label(left, bg=self.BG, fg=self.TEXT, anchor="w", font=("Segoe UI", 12, "bold"))
        self.top_player.pack(fill="x", pady=(2, 7))
        board_row = ttk.Frame(left)
        board_row.pack(fill="both", expand=True)
        self.eval_canvas = tk.Canvas(board_row, bg=self.BG, width=20, highlightthickness=0)
        self.eval_canvas.pack(side="left", fill="y", padx=(0, 8))
        self.canvas = tk.Canvas(board_row, bg=self.BG, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda event: self.draw_board())
        self.canvas.bind("<Button-1>", self.on_click)
        self.bottom_player = tk.Label(left, bg=self.BG, fg=self.TEXT, anchor="w", font=("Segoe UI", 12, "bold"))
        self.bottom_player.pack(fill="x", pady=(7, 5))
        self.captures = tk.Label(left, bg=self.BG, fg=self.MUTED, anchor="w", font=("Segoe UI", 10))
        self.captures.pack(fill="x")
        replay = ttk.Frame(left)
        replay.pack(fill="x", pady=(12, 7))
        for label, action in (("|◀", lambda: self.review(0)), ("◀", lambda: self.step_review(-1)),
                              ("▶", lambda: self.step_review(1)), ("Live ▶|", self.go_live)):
            ttk.Button(replay, text=label, width=7, command=action).pack(side="left", padx=(0, 4))
        ttk.Label(replay, textvariable=self.review_text).pack(side="right")
        ttk.Label(left, textvariable=self.eval_text, foreground=self.GOLD).pack(anchor="w")
        tk.Label(left, text="Untimed local chess · + favors White · AI/review estimates are heuristic",
                 bg=self.BG, fg=self.MUTED, font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(5, 0))
        right = ttk.Frame(main, width=364)
        right.grid(row=0, column=1, sticky="nsew")
        self.make_controls(right)
        footer = tk.Frame(outer, bg=self.PANEL, padx=12, pady=9)
        footer.pack(fill="x", pady=(14, 0))
        tk.Label(footer, textvariable=self.status, bg=self.PANEL, fg=self.TEXT,
                 font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(footer, textvariable=self.detail, bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9), anchor="w", wraplength=1100).pack(fill="x", pady=(3, 0))
        menu = tk.Menu(self.root)
        game_menu = tk.Menu(menu, tearoff=False)
        for label, cmd in (("New game  Ctrl+N", self.new_game), ("Import PGN  Ctrl+O", self.import_pgn),
                           ("Export PGN  Ctrl+S", self.export_pgn), ("Copy FEN", self.copy_fen),
                           ("History / persistent memory", self.show_history), ("Quit", self.close)):
            game_menu.add_command(label=label, command=cmd)
        menu.add_cascade(label="Game", menu=game_menu)
        menu.add_command(label="Help", command=self.help)
        self.root.configure(menu=menu)

    def make_controls(self, parent) -> None:
        ttk.Label(parent, text="MATCH SETUP", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 9))
        self.mode_box = self.choice(parent, "Mode", self.mode, MODES, self.mode_changed)
        self.human_box = self.choice(parent, "Human side", self.human, ("White", "Black"), self.side_changed)
        self.choice(parent, "AI strength", self.level, tuple(LEVELS), self.level_changed)
        tk.Checkbutton(parent, text="Use learned opening memory", variable=self.use_memory,
                       command=self.persist, bg=self.BG, fg=self.MUTED, activebackground=self.BG,
                       activeforeground=self.TEXT, selectcolor=self.CARD, anchor="w").pack(fill="x", pady=(0, 8))
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 7))
        self.new_button = ttk.Button(row, text="New game", command=self.new_game, style="Gold.TButton")
        self.new_button.pack(side="left", fill="x", expand=True)
        self.pause_button = ttk.Button(row, text="Pause", command=self.toggle_pause)
        self.pause_button.pack(side="left", fill="x", expand=True, padx=(7, 0))
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 7))
        self.undo_button = ttk.Button(row, text="Undo", command=self.undo)
        self.undo_button.pack(side="left", fill="x", expand=True)
        self.hint_button = ttk.Button(row, text="Hint", command=self.hint)
        self.hint_button.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Flip", command=self.flip).pack(side="left", fill="x", expand=True)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 11))
        self.resign_button = ttk.Button(row, text="Resign", command=self.resign)
        self.resign_button.pack(side="left", fill="x", expand=True)
        self.draw_button = ttk.Button(row, text="Draw…", command=self.draw_dialog)
        self.draw_button.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.tabs = ttk.Notebook(parent)
        self.tabs.pack(fill="both", expand=True)
        moves_tab, memory_tab = ttk.Frame(self.tabs), ttk.Frame(self.tabs)
        self.tabs.add(moves_tab, text="Moves / replay")
        self.tabs.add(memory_tab, text="Memory")
        self.moves = self.tree(moves_tab, ("move", "san"), ("Turn", "Move"), (64, 210))
        self.moves.bind("<<TreeviewSelect>>", self.select_move)
        ttk.Label(memory_tab, textvariable=self.stats_text, justify="left", padding=12).pack(anchor="w")
        tk.Label(memory_tab, text="Every move is autosaved.\nCompleted results teach the opening book.\nResume starts paused for your control.\n\nAll information stays on this computer.",
                 bg=self.BG, fg=self.MUTED, justify="left", font=("Segoe UI", 10)).pack(anchor="w", padx=12)
        ttk.Button(memory_tab, text="Browse saved matches", command=self.show_history).pack(fill="x", padx=12, pady=14)
        self.analyze_button = ttk.Button(parent, text="Analyze match", command=self.analyze, style="Gold.TButton")
        self.analyze_button.pack(fill="x", pady=(10, 6))
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Button(row, text="Import PGN", command=self.import_pgn).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Export PGN", command=self.export_pgn).pack(side="left", fill="x", expand=True, padx=(6, 0))

    def choice(self, parent, label, variable, values, action):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 9))
        ttk.Label(row, text=label).pack(side="left")
        box = ttk.Combobox(row, textvariable=variable, values=values, state="readonly", width=19)
        box.pack(side="right")
        box.bind("<<ComboboxSelected>>", lambda event: action())
        return box

    def tree(self, parent, columns, headings, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse", height=6)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=40, anchor="w")
        return tree

    def bind_keys(self) -> None:
        for key, action in (("<Control-n>", self.new_game), ("<Control-s>", self.export_pgn),
                            ("<Control-o>", self.import_pgn), ("<Control-z>", self.undo),
                            ("<Escape>", self.escape), ("<F1>", self.help)):
            self.root.bind(key, lambda event, fn=action: (fn(), "break")[-1])

    def update_players(self) -> None:
        mode = self.mode.get()
        self.session.mode = mode
        self.session.controls = {"mode": mode, "human": self.human.get(), "level": self.level.get()}
        for color, name in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
            ai = mode == "AI vs AI" or (mode == "Human vs AI" and name != self.human.get())
            self.session.headers[name] = f"Nexus AI ({self.level.get()})" if ai else "Human"

    def is_human(self, color=None) -> bool:
        color = self.session.board.turn if color is None else color
        return self.mode.get() == "Human vs Human" or (
            self.mode.get() == "Human vs AI" and color == (self.human.get() == "White"))

    def display_board(self) -> chess.Board:
        if self.review_ply is None:
            return self.session.board
        return self.positions[self.review_ply][0]

    def board_geometry(self):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        side = max(8, min(width, height) - 40)
        return (width - side) / 2, (height - side) / 2, side / 8

    def square_at(self, x, y):
        x0, y0, cell = self.board_geometry()
        col, row = int((x - x0) // cell), int((y - y0) // cell)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        return chess.square(7 - col if self.flipped else col, row if self.flipped else 7 - row)

    def square_center(self, square):
        x0, y0, cell = self.board_geometry()
        file, rank = chess.square_file(square), chess.square_rank(square)
        col, row = (7 - file, rank) if self.flipped else (file, 7 - rank)
        return x0 + (col + .5) * cell, y0 + (row + .5) * cell

    def draw_board(self) -> None:
        if not hasattr(self, "canvas") or self.closed:
            return
        canvas, board = self.canvas, self.display_board()
        canvas.delete("all")
        x0, y0, cell = self.board_geometry()
        targets = {m.to_square for m in board.legal_moves if m.from_square == self.selected} if self.selected is not None else set()
        last = board.peek() if board.move_stack else None
        checked = board.king(board.turn) if board.is_check() else None
        for square in chess.SQUARES:
            x, y = self.square_center(square)
            color = "#e5d4b5" if (chess.square_rank(square) + chess.square_file(square)) % 2 else "#799184"
            if last and square in (last.from_square, last.to_square):
                color = "#c5bd72"
            if square == self.selected:
                color = "#e9bd68"
            if square == checked:
                color = "#da8276"
            canvas.create_rectangle(x-cell/2, y-cell/2, x+cell/2, y+cell/2, fill=color, outline=color)
            piece = board.piece_at(square)
            if piece:
                # Draw filled glyphs with contrasting outlines so both armies
                # remain visible on either square color (no image assets).
                glyph = chess.Piece(piece.piece_type, chess.BLACK).unicode_symbol()
                ink, edge = ("#fff9ec", "#40464a") if piece.color else ("#17232e", "#dbe0dd")
                font = ("DejaVu Sans", max(10, int(cell * .65)))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    canvas.create_text(x+dx, y+dy, text=glyph, fill=edge, font=font)
                canvas.create_text(x, y, text=glyph, fill=ink, font=font)
            if square in targets:
                if piece:
                    r = cell * .44
                    canvas.create_oval(x-r, y-r, x+r, y+r, outline="#2c645c", width=3)
                else:
                    r = cell * .12
                    canvas.create_oval(x-r, y-r, x+r, y+r, fill="#47796b", outline="")
        if self.hint_move and self.review_ply is None:
            x1, y1 = self.square_center(self.hint_move.from_square)
            x2, y2 = self.square_center(self.hint_move.to_square)
            canvas.create_line(x1, y1, x2, y2, fill="#eaa035", width=max(3, int(cell*.08)),
                               arrow=tk.LAST, arrowshape=(18, 22, 9))
        for index in range(8):
            canvas.create_text(x0+(index+.5)*cell, y0+8*cell+10,
                               text=chess.FILE_NAMES[7-index if self.flipped else index], fill=self.MUTED, font=("Segoe UI", 9))
            canvas.create_text(x0-10, y0+(index+.5)*cell,
                               text=str(index+1 if self.flipped else 8-index), fill=self.MUTED, font=("Segoe UI", 9))
        score = ChessEngine.evaluate(board)
        outcome = board.outcome()
        if outcome:
            score = 0 if outcome.winner is None else (10000 if outcome.winner else -10000)
        self.eval_text.set(f"Static evaluation · {score/100:+.2f} pawns" if abs(score) < 10000 else "Checkmate")
        fraction = 1 / (1 + math.exp(-max(-1500, min(1500, score))/300))
        self.eval_canvas.delete("all")
        if self.flipped:
            self.eval_canvas.create_rectangle(2, y0, 17, y0+8*cell, fill="#19232c", outline="")
            self.eval_canvas.create_rectangle(2, y0, 17, y0+8*cell*fraction, fill="#f0e7d6", outline="")
        else:
            self.eval_canvas.create_rectangle(2, y0, 17, y0+8*cell, fill="#19232c", outline="")
            self.eval_canvas.create_rectangle(2, y0+8*cell*(1-fraction), 17, y0+8*cell, fill="#f0e7d6", outline="")

    def refresh(self, rebuild=True) -> None:
        if rebuild:
            self.positions = self.session.timeline()
            if self.review_ply is not None:
                self.review_ply = min(self.review_ply, len(self.positions)-1)
            children = self.moves.get_children()
            if children:
                self.moves.delete(*children)
            board = self.session.board.root()
            for ply, move in enumerate(self.session.board.move_stack, 1):
                san = board.san(move)
                self.moves.insert("", "end", iid=str(ply), values=(f"{board.fullmove_number}{'.' if board.turn else '...'}", san))
                board.push(move)
            if self.session.board.move_stack:
                self.moves.see(str(len(self.session.board.move_stack)))
        board = self.display_board()
        top, bottom = ("White", "Black") if self.flipped else ("Black", "White")
        self.top_player.configure(text=f"{top}  ·  {self.session.headers.get(top, top)}")
        self.bottom_player.configure(text=f"{bottom}  ·  {self.session.headers.get(bottom, bottom)}")
        material = sum(len(board.pieces(piece, chess.WHITE))*value - len(board.pieces(piece, chess.BLACK))*value
                       for piece, value in PIECE_VALUES.items())
        self.captures.configure(text=f"Material balance: {material/100:+.2f} pawns  ·  Move {board.fullmove_number}")
        result = self.session.result()
        side = "White" if self.session.board.turn else "Black"
        status = f"{side} to move" + (" · Check!" if self.session.board.is_check() else "")
        if result != "*":
            winner = "Draw" if result == "1/2-1/2" else ("White wins" if result == "1-0" else "Black wins")
            status = f"{winner} · {result} · {self.session.reason or 'Game over'}"
        elif self.paused:
            status += " · Paused"
        elif "ai" in self.jobs:
            status += " · AI thinking…"
        if self.review_ply is not None:
            status = "REPLAY · " + status
        if self.unsaved:
            status += " · UNSAVED — export PGN"
        self.status.set(status)
        self.review_text.set(self.positions[self.review_ply][1] if self.review_ply is not None else "Live position")
        self.pause_button.configure(text="Resume" if self.paused else "Pause", state="normal" if result == "*" else "disabled")
        self.undo_button.configure(state="normal" if self.session.board.move_stack else "disabled")
        self.hint_button.configure(state="normal" if result == "*" and self.is_human() and self.review_ply is None else "disabled")
        self.resign_button.configure(state="normal" if result == "*" and self.is_human() and self.review_ply is None else "disabled")
        self.draw_button.configure(state="normal" if result == "*" and self.review_ply is None else "disabled")
        self.human_box.configure(state="readonly" if self.mode.get() == "Human vs AI" else "disabled")
        self.draw_board()

    def on_click(self, event) -> None:
        if self.paused or self.review_ply is not None or "ai" in self.jobs or not self.is_human() or self.session.result() != "*":
            return
        square = self.square_at(event.x, event.y)
        if square is None:
            return
        board = self.session.board
        candidates = [m for m in board.legal_moves if m.from_square == self.selected and m.to_square == square]
        if candidates:
            if len(candidates) > 1:
                self.promote(candidates)
            else:
                self.commit_move(candidates[0])
            return
        piece = board.piece_at(square)
        self.selected = square if piece and piece.color == board.turn and square != self.selected else None
        self.hint_move = None
        self.draw_board()

    def promote(self, moves) -> None:
        window = tk.Toplevel(self.root)
        window.title("Choose promotion")
        window.configure(bg=self.BG)
        window.transient(self.root)
        window.resizable(False, False)
        ttk.Label(window, text="Promote pawn to:", padding=14).pack()
        row = ttk.Frame(window, padding=12)
        row.pack()
        for piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
            move = next(m for m in moves if m.promotion == piece_type)
            ttk.Button(row, text=chess.piece_name(piece_type).title(), command=lambda m=move: (window.destroy(), self.commit_move(m))).pack(side="left", padx=4)
        window.grab_set()
        window.bind("<Escape>", lambda event: window.destroy())

    def commit_move(self, move) -> None:
        self.cancel_job("hint")
        try:
            san = self.session.play(move)
        except ValueError as exc:
            self.detail.set(str(exc))
            return
        if self.analysis_window:
            self.close_analysis()  # A review belongs to exactly one move snapshot.
        self.selected = self.hint_move = None
        self.review_ply = None
        self.detail.set(f"Played {san}. Every move is autosaved.")
        self.persist()
        self.refresh()
        self.schedule_ai()

    # Workers never call Tk, including root.after(). A queue polled on the UI
    # thread carries results; serial IDs discard stale replies after undo/reset.
    def start_job(self, kind, function) -> None:
        self.cancel_job(kind)
        self.job_serial += 1
        serial, cancel = self.job_serial, threading.Event()
        def emit(value):
            self.messages.put((kind, serial, "progress", value))
        def worker():
            try:
                result = function(cancel, emit)
                if not cancel.is_set():
                    self.messages.put((kind, serial, "done", result))
            except SearchCancelled:
                self.messages.put((kind, serial, "cancelled", None))
            except Exception as exc:
                traceback.print_exc()
                self.messages.put((kind, serial, "error", str(exc)))
        thread = threading.Thread(target=worker, daemon=True, name=f"nexus-{kind}-{serial}")
        self.jobs[kind] = (serial, cancel, thread)
        thread.start()

    def cancel_job(self, kind) -> None:
        job = self.jobs.pop(kind, None)
        if job:
            job[1].set()

    def cancel_play(self) -> None:
        for kind in ("ai", "hint"):
            self.cancel_job(kind)
        if self.ai_pending is not None:
            self.root.after_cancel(self.ai_pending)
            self.ai_pending = None

    def poll_messages(self) -> None:
        if self.closed:
            return
        # Bound queue work so a busy analysis cannot monopolize the event loop.
        for _ in range(100):
            try:
                kind, serial, state, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind not in self.jobs or self.jobs[kind][0] != serial:
                continue
            if state == "progress":
                if kind == "analysis":
                    done, total = payload
                    self.analysis_progress.set(f"Reviewing ply {done} / {total}…")
                else:
                    self.detail.set(f"{kind.title()} · depth {payload.depth} · {payload.nodes:,} nodes · {payload.score/100:+.2f}")
                continue
            self.jobs.pop(kind, None)
            if state == "error":
                self.detail.set(f"{kind.title()} failed: {payload}")
                if kind == "ai":
                    self.paused = True
                if kind == "analysis" and self.analysis_window:
                    self.analysis_progress.set("Analysis failed: " + payload)
                    self.analysis_cancel.configure(text="Close")
            elif state == "done":
                if kind == "ai" and payload.move:
                    self.commit_move(payload.move)
                    self.detail.set(f"AI · depth {payload.depth} · {payload.nodes:,} nodes · {payload.elapsed:.2f}s · {payload.score/100:+.2f}")
                elif kind == "hint" and payload.move:
                    if payload.move in self.session.board.legal_moves:
                        self.hint_move = payload.move
                        self.detail.set(f"Hint: {self.session.board.san(payload.move)} · depth {payload.depth} · evaluation {payload.score/100:+.2f}")
                elif kind == "analysis":
                    self.finish_analysis(payload)
            self.refresh(rebuild=False)
        self.after_poll = self.root.after(60, self.poll_messages)

    def schedule_ai(self) -> None:
        if self.closed or self.paused or self.review_ply is not None or self.is_human() or self.session.result() != "*":
            return
        if "ai" not in self.jobs and self.ai_pending is None:
            self.ai_pending = self.root.after(300, self.run_ai)

    def run_ai(self) -> None:
        self.ai_pending = None
        if self.closed or self.paused or self.review_ply is not None or self.is_human() or self.session.result() != "*":
            return
        board = self.session.board.copy(stack=True)
        # AI always accepts a legally claimable draw; humans use Draw….
        if board.can_claim_draw():
            self.finish_game("1/2-1/2", "Draw claimed by AI")
            return
        if self.use_memory.get():
            try:
                book = self.store.book_move(board)
            except sqlite3.Error:
                book = None
            if book:
                self.commit_move(book)
                self.detail.set("AI played a result-weighted move from persistent opening memory.")
                return
        seconds, depth = LEVELS[self.level.get()]
        self.start_job("ai", lambda cancel, emit: ChessEngine().search(board, seconds, depth, cancel, emit))
        self.refresh(rebuild=False)

    def hint(self) -> None:
        if self.review_ply is not None or not self.is_human() or self.session.result() != "*":
            return
        board = self.session.board.copy(stack=True)
        self.start_job("hint", lambda cancel, emit: ChessEngine().search(board, 1.5, 5, cancel, emit))
        self.detail.set("Looking for a hint…")

    def toggle_pause(self) -> None:
        if self.session.result() != "*":
            return
        self.paused = not self.paused
        if self.paused:
            self.cancel_play()
        else:
            self.review_ply = None
            self.schedule_ai()
        self.selected = None
        self.detail.set("Paused — review or change settings safely." if self.paused else "Play resumed.")
        self.refresh(rebuild=False)
        self.persist()

    def escape(self) -> None:
        self.selected = self.hint_move = None
        if not self.paused and self.session.result() == "*":
            self.toggle_pause()
        self.draw_board()

    def reset_view(self) -> None:
        self.cancel_play()
        self.cancel_job("analysis")
        if self.analysis_window:
            self.analysis_window.destroy()
            self.analysis_window = None
        self.selected = self.hint_move = self.review_ply = None
        self.analysis_rows = []

    def new_game(self) -> None:
        if self.session.board.move_stack and self.session.result() == "*":
            if not messagebox.askyesno("New game", "Start a new game? This unfinished match will remain in History.", parent=self.root):
                return
        if not self.persist():
            return  # Keep the only in-memory copy available for PGN export.
        self.reset_view()
        self.session = Session(self.mode.get())
        self.update_players()
        self.flipped = self.human.get() == "Black" if self.mode.get() == "Human vs AI" else False
        self.paused = self.mode.get() == "AI vs AI"
        self.detail.set("Press Resume to watch AI vs AI." if self.paused else "New match. Click a piece to see legal moves.")
        self.persist()
        self.refresh()
        self.schedule_ai()

    def mode_changed(self) -> None:
        # Mode changes take effect on the current board, without silently
        # throwing a match away. All pending work is invalidated first.
        self.cancel_play()
        finished = self.session.result() != "*"
        if not finished:
            self.update_players()
        self.paused = True
        self.selected = None
        self.detail.set("Setup selected for the next game; the archived result is unchanged." if finished else "Mode changed on this board. Resume, or choose New game.")
        self.persist()
        self.refresh(rebuild=False)

    def side_changed(self) -> None:
        self.flipped = self.human.get() == "Black"
        self.mode_changed()

    def level_changed(self) -> None:
        self.cancel_play()
        if self.session.result() == "*":
            self.update_players()
        self.persist()
        self.refresh(rebuild=False)
        self.schedule_ai()

    def undo(self) -> None:
        if not self.session.board.move_stack:
            return
        self.reset_view()
        was_finished = self.session.result() != "*"
        # Branching from a finished match preserves its result and learned
        # memory; the edited line receives its own ID and unfinished history.
        if was_finished:
            self.session.id = uuid.uuid4().hex
            self.session.created = timestamp()
        self.session.forced_result, self.session.reason = "*", ""
        self.update_players()
        self.session.board.pop()
        if self.mode.get() == "Human vs AI":
            while self.session.board.move_stack and not self.is_human():
                self.session.board.pop()
        self.paused = self.mode.get() == "AI vs AI"
        self.detail.set("Move undone. Finished games remain archived; edits start a new variation." if was_finished else "Move undone.")
        self.persist()
        self.refresh()
        self.schedule_ai()

    def flip(self) -> None:
        self.flipped = not self.flipped
        self.refresh(rebuild=False)
        self.persist()

    def review(self, ply) -> None:
        self.cancel_play()
        self.paused = True
        self.selected = self.hint_move = None
        self.review_ply = max(0, min(ply, len(self.positions)-1))
        self.refresh(rebuild=False)

    def step_review(self, direction) -> None:
        ply = len(self.positions)-1 if self.review_ply is None else self.review_ply
        self.review(ply + direction)

    def select_move(self, event=None) -> None:
        selected = self.moves.selection()
        if selected:
            self.review(int(selected[0]))

    def go_live(self) -> None:
        self.review_ply = self.selected = self.hint_move = None
        self.detail.set("Live board. Press Resume if play is paused.")
        self.refresh(rebuild=False)

    def finish_game(self, result, reason) -> None:
        self.cancel_play()
        self.session.forced_result, self.session.reason = result, reason
        self.paused = True
        self.selected = self.hint_move = None
        self.persist()
        self.refresh()

    def resign(self) -> None:
        if self.session.result() != "*" or not self.is_human() or self.review_ply is not None:
            return
        side = "White" if self.session.board.turn else "Black"
        if messagebox.askyesno("Resign", f"{side}: resign this game?", parent=self.root):
            self.finish_game("0-1" if self.session.board.turn else "1-0", f"{side} resigned")

    def draw_dialog(self) -> None:
        if self.session.result() != "*":
            return
        if self.session.board.can_claim_draw():
            self.finish_game("1/2-1/2", "Threefold / 50-move draw claimed")
        elif self.mode.get() == "Human vs Human":
            if messagebox.askyesno("Agree to a draw", "Do BOTH players agree to end this game as a draw?", parent=self.root):
                self.finish_game("1/2-1/2", "Draw by agreement")
        else:
            messagebox.showinfo("Draw rules", "No draw is claimable yet. Threefold repetition and the 50-move rule allow a claim. Stalemate, insufficient material, fivefold repetition and 75 moves are automatic.", parent=self.root)

    def export_pgn(self) -> None:
        path = filedialog.asksaveasfilename(parent=self.root, title="Export match", defaultextension=".pgn",
                                           initialfile="nexus_match.pgn", filetypes=[("Chess PGN", "*.pgn"), ("All files", "*.*")])
        if path:
            try:
                Path(path).write_text(self.session.pgn(), encoding="utf-8")
                self.detail.set(f"Exported {path}")
            except OSError as exc:
                messagebox.showerror("Export failed", str(exc), parent=self.root)

    def import_pgn(self) -> None:
        path = filedialog.askopenfilename(parent=self.root, title="Import first game from PGN",
                                         filetypes=[("Chess PGN", "*.pgn"), ("All files", "*.*")])
        if not path:
            return
        try:
            if Path(path).stat().st_size > 5_000_000:
                raise ValueError("Please import a PGN smaller than 5 MB.")
            session = Session.from_pgn(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, UnicodeError) as exc:
            messagebox.showerror("Import failed", str(exc), parent=self.root)
            return
        if self.load_session(session):
            self.detail.set("Imported the first PGN game, paused. Select a move to replay.")

    def load_session(self, session: Session) -> bool:
        if not self.persist():
            return False
        self.reset_view()
        self.session = session
        self.mode.set(session.controls["mode"])
        self.human.set(session.controls["human"])
        self.level.set(session.controls["level"])
        self.flipped = self.human.get() == "Black" if self.mode.get() == "Human vs AI" else self.flipped
        self.paused = True
        self.persist()
        self.refresh()
        return True

    def copy_fen(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.display_board().fen())
        self.detail.set("Displayed position FEN copied to clipboard.")

    def show_history(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Nexus Chess — persistent memory")
        window.geometry("820x510")
        window.configure(bg=self.BG)
        window.transient(self.root)
        ttk.Label(window, text=self.store.stats(), padding=14, font=("Segoe UI", 12)).pack(anchor="w")
        tree = self.tree(window, ("date", "mode", "result"), ("Date / time", "Mode", "Result"), (220, 200, 100))
        for row in self.store.history():
            tree.insert("", "end", iid=row["id"], values=(row["created"][:19].replace("T", " "), row["mode"], row["result"]))
        def load():
            if not tree.selection():
                return
            try:
                if not self.persist():
                    return
                row = self.store.saved_game(tree.selection()[0])
                if row is None:
                    messagebox.showinfo("History", "That unfinished entry was removed after an undo. Reopen History to refresh.", parent=window)
                    return
                session = Session.from_pgn(row["pgn"], row["mode"])
                session.id, session.created, session.reason = row["id"], row["created"], row["reason"]
                session.restore_controls(json.loads(row["controls"]))
                if self.load_session(session):
                    window.destroy()
                    self.detail.set("Saved match loaded, paused. Select moves to replay or Resume to continue.")
            except (ValueError, KeyError, sqlite3.Error) as exc:
                messagebox.showerror("History", str(exc), parent=window)
        tree.bind("<Double-1>", lambda event: load())
        ttk.Button(window, text="Open selected match", command=load, style="Gold.TButton").pack(pady=10)
        ttk.Label(window, text=f"Local database: {self.store.path}\nOpening memory rewards wins/draws; it is not neural-network training.",
                  padding=12, wraplength=760, foreground=self.MUTED).pack(anchor="w")

    def analyze(self) -> None:
        if self.analysis_window and self.analysis_window.winfo_exists():
            self.analysis_window.lift()
            return
        if not self.session.board.move_stack:
            messagebox.showinfo("Match analysis", "Play or import a game first.", parent=self.root)
            return
        self.cancel_play()
        self.paused = True
        self.refresh(rebuild=False)
        board = self.session.board.copy(stack=True)
        window = self.analysis_window = tk.Toplevel(self.root)
        window.title("Nexus Chess — match analysis")
        window.geometry("1030x720")
        window.minsize(820, 580)
        window.configure(bg=self.BG)
        window.transient(self.root)
        ttk.Label(window, text="MATCH REVIEW", font=("Segoe UI", 20, "bold"), padding=16).pack(anchor="w")
        self.analysis_progress = tk.StringVar(value="Reviewing moves… you can cancel at any time.")
        ttk.Label(window, textvariable=self.analysis_progress, padding=(16, 0, 16, 8)).pack(anchor="w")
        self.analysis_graph = tk.Canvas(window, bg=self.PANEL, height=120, highlightthickness=0)
        self.analysis_graph.pack(fill="x", padx=16, pady=10)
        self.analysis_graph.bind("<Configure>", lambda event: self.draw_analysis_graph())
        self.analysis_table = self.tree(window, ("ply", "san", "quality", "loss", "best", "eval"),
                                        ("Ply / side", "Played", "Quality", "Loss (pawns)", "Engine idea", "White eval"),
                                        (110, 110, 150, 110, 130, 100))
        for name, color in (("Best", self.GREEN), ("Excellent", self.GREEN), ("Good", "#c5dbac"), ("Inaccuracy", "#e6c677"),
                            ("Mistake", "#e9a475"), ("Blunder", self.RED)):
            self.analysis_table.tag_configure(name, foreground=color)
        self.analysis_table.bind("<<TreeviewSelect>>", self.select_analysis)
        ttk.Label(window, text="Practice-engine estimates, not a professional verdict. Loss compares searched alternatives; shallow or time-limited reviews can be wrong. Select a row to replay the position.",
                  foreground=self.MUTED, wraplength=940, padding=16).pack(fill="x")
        self.analysis_cancel = ttk.Button(window, text="Cancel review", command=self.close_analysis)
        self.analysis_cancel.pack(pady=(0, 14))
        window.protocol("WM_DELETE_WINDOW", self.close_analysis)
        self.analysis_rows = []
        self.start_job("analysis", lambda cancel, emit: analyze_game(board, .35, cancel, lambda done, total: emit((done, total))))

    def close_analysis(self) -> None:
        self.cancel_job("analysis")
        if self.analysis_window:
            self.analysis_window.destroy()
            self.analysis_window = None
        self.analysis_rows = []
        self.detail.set("Review closed. Press Resume to continue if paused.")

    def finish_analysis(self, result) -> None:
        if not self.analysis_window:
            return
        self.analysis_rows = result["rows"]
        fmt = lambda value: "—" if value is None else f"{value:.1f}%"
        self.analysis_progress.set(f"Heuristic accuracy · White {fmt(result['white_accuracy'])}  /  Black {fmt(result['black_accuracy'])} · {len(self.analysis_rows)} plies reviewed")
        for index, row in enumerate(self.analysis_rows):
            loss = f"{row['loss']:.2f}" if math.isfinite(row["loss"]) else "—"
            self.analysis_table.insert("", "end", iid=str(index), tags=(row["label"].split(" (")[0],), values=(
                f"{row['ply']} {row['side']}", row["san"], row["label"], loss, row["best_san"], self.format_score(row["score"])))
        self.analysis_cancel.configure(text="Close review")
        self.draw_analysis_graph()
        self.detail.set("Match analysis complete. Select a row to replay that move.")

    @staticmethod
    def format_score(pawns: float) -> str:
        if abs(pawns) >= ChessEngine.MATE_THRESHOLD / 100:
            return "White mates" if pawns > 0 else "Black mates"
        return f"{pawns:+.2f}"

    def draw_analysis_graph(self) -> None:
        if not self.analysis_window:
            return
        canvas = self.analysis_graph
        canvas.delete("all")
        width, height = max(100, canvas.winfo_width()), max(80, canvas.winfo_height())
        middle = height/2
        canvas.create_line(12, middle, width-12, middle, fill="#4a5d6c", dash=(3, 4))
        canvas.create_text(16, 12, anchor="w", text="WHITE +", fill=self.MUTED, font=("Segoe UI", 8))
        canvas.create_text(16, height-12, anchor="w", text="BLACK +", fill=self.MUTED, font=("Segoe UI", 8))
        points = [12, middle]
        for index, row in enumerate(self.analysis_rows, 1):
            points.extend([12 + (width-24)*index/max(1, len(self.analysis_rows)),
                           middle - math.tanh(row["score"]/4)*(height/2-12)])
        if len(points) >= 4:
            canvas.create_line(*points, fill=self.GOLD, width=2)

    def select_analysis(self, event=None) -> None:
        selected = self.analysis_table.selection()
        if selected:
            self.review(self.analysis_rows[int(selected[0])]["ply"])

    def help(self) -> None:
        messagebox.showinfo("Nexus Chess help", "PLAY\nClick a piece, then a highlighted destination. Promotion offers all four pieces. Castling and en passant follow normal chess rules. Games are untimed.\n\nMODES\nChange mode/side on the current board, then Resume; New game resets the board. AI vs AI starts paused. Strong thinks up to 2 seconds per move; this is a practice engine, not Stockfish.\n\nREVIEW\nSelect a move or use replay arrows. Live returns to the latest position; Resume restarts play. Analyze match pauses play and searches alternatives. Accuracy is a heuristic only.\n\nMEMORY\nEvery move is autosaved locally. History includes unfinished games. Completed games teach a result-weighted opening book. Undo on a finished game creates a variation without erasing its result.\n\nKEYS\nCtrl+N: new · Ctrl+O: import PGN · Ctrl+S: export\nCtrl+Z: undo · Esc: pause · F1: help", parent=self.root)

    def close(self) -> None:
        if self.closed:
            return
        self.cancel_play()
        self.cancel_job("analysis")
        if not self.persist():
            self.paused = True
            self.refresh(rebuild=False)
            if not messagebox.askyesno("Unsaved changes", "Saving failed. Quit WITHOUT saving your latest changes?\n\nChoose No to keep the game open and export its PGN.", parent=self.root):
                return
        self.closed = True
        if self.after_poll is not None:
            self.root.after_cancel(self.after_poll)
        self.store.close()
        self.root.destroy()


def self_test() -> bool:
    """Run isolated tests; never read or change the user's chess database."""
    import unittest

    class NexusTests(unittest.TestCase):
        def test_initial_legal_moves_and_perft(self):
            board = chess.Board()
            self.assertEqual(board.legal_moves.count(), 20)
            total = 0
            for move in list(board.legal_moves):
                board.push(move)
                total += board.legal_moves.count()
                board.pop()
            self.assertEqual(total, 400)

        def test_mate_and_standard_pgn(self):
            session = Session()
            for san in ("f3", "e5", "g4", "Qh4#"):
                session.play(session.board.parse_san(san))
            self.assertEqual(session.result(), "0-1")
            self.assertIn("Qh4#", session.pgn())
            self.assertIn('[Result "0-1"]', session.pgn())
            restored = Session.from_pgn(session.pgn())
            self.assertEqual(restored.board.fen(), session.board.fen())
            self.assertEqual(len(restored.board.move_stack), 4)

        def test_illegal_move_rejected(self):
            session = Session()
            with self.assertRaises(ValueError):
                session.play(chess.Move.from_uci("e2e5"))
            self.assertEqual(session.board.fen(), chess.Board().fen())

        def test_castling_and_en_passant(self):
            board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
            self.assertIn(chess.Move.from_uci("e1g1"), board.legal_moves)
            board.push_uci("e1g1")
            self.assertEqual(board.piece_at(chess.F1), chess.Piece(chess.ROOK, chess.WHITE))
            board = chess.Board()
            for uci in ("e2e4", "a7a6", "e4e5", "d7d5"):
                board.push_uci(uci)
            move = chess.Move.from_uci("e5d6")
            self.assertTrue(board.is_en_passant(move))
            board.push(move)
            self.assertIsNone(board.piece_at(chess.D5))
            # A pinned en-passant pawn may not expose its own king.
            board = chess.Board("k7/8/8/r4pPK/8/8/8/8 w - f6 0 1")
            self.assertNotIn(chess.Move.from_uci("g5f6"), board.legal_moves)

        def test_promotions(self):
            board = chess.Board("8/P6k/8/8/8/8/8/7K w - - 0 1")
            promotions = [m for m in board.legal_moves if m.from_square == chess.A7]
            self.assertEqual({m.promotion for m in promotions}, {chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT})

        def test_draw_rules(self):
            self.assertTrue(chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1").is_stalemate())
            self.assertTrue(chess.Board("7k/8/8/8/8/8/8/K7 w - - 0 1").is_insufficient_material())
            board = chess.Board()
            for uci in ("g1f3", "g8f6", "f3g1", "f6g8") * 2:
                board.push_uci(uci)
            self.assertTrue(board.can_claim_threefold_repetition())
            self.assertIsNone(board.outcome())  # claimable, not automatically over
            for uci in ("g1f3", "g8f6", "f3g1", "f6g8") * 2:
                board.push_uci(uci)
            self.assertEqual(board.outcome().result(), "1/2-1/2")

        def test_pgn_custom_start_and_invalid(self):
            session = Session()
            session.board = chess.Board("8/P6k/8/8/8/8/8/7K w - - 0 1")
            session.play(chess.Move.from_uci("a7a8q"))
            restored = Session.from_pgn(session.pgn())
            self.assertEqual(restored.board.fen(), session.board.fen())
            self.assertEqual(restored.board.root().fen(), session.board.root().fen())
            for text in ("", "not a chess game", '[FEN "invalid"]\n[SetUp "1"]\n\n*'):
                with self.assertRaises(ValueError):
                    Session.from_pgn(text)

        def test_strict_pgn_tokens_and_annotations(self):
            with self.assertRaises(ValueError):
                parse_pgn("1. e4 e5 2. Nf3 Nc6 3. B55 *")
            with self.assertRaises(ValueError):
                parse_pgn('[Variant "Atomic"]\n\n1. e4 *')
            game = parse_pgn('1. e4 {best central try} e5 $1 2. Nf3!? (2. Bc4) Nc6 *')
            self.assertEqual(len(list(game.mainline_moves())), 4)
            first = parse_pgn('1. e4 *\n\n[Event "Second game"]\n\n1. d4 *')
            self.assertEqual(len(list(first.mainline_moves())), 1)

        def test_controller_settings_and_legacy_migration(self):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                # Simulate the first schema version before controller storage.
                db = sqlite3.connect(str(path / "chess.sqlite3"))
                db.execute("CREATE TABLE games (id TEXT PRIMARY KEY, created TEXT, updated TEXT, mode TEXT, result TEXT, reason TEXT, pgn TEXT)")
                db.commit()
                db.close()
                store = Store(path)
                session = Session("Human vs AI")
                session.controls.update(human="Black", level="Strong")
                session.headers.update(White="Nexus AI (Strong)", Black="Human")
                session.play(chess.Move.from_uci("e2e4"))
                store.save_session(session, DEFAULT_SETTINGS)
                saved = store.saved_game(session.id)
                self.assertEqual(json.loads(saved["controls"])["human"], "Black")
                self.assertEqual(Session.restore(store.get("session")).controls, session.controls)
                migrated = Session.from_pgn(saved["pgn"], saved["mode"])
                self.assertEqual(migrated.controls, session.controls)
                store.close()

        def test_database_autosave_resume_and_deduplication(self):
            with tempfile.TemporaryDirectory() as directory:
                store = Store(Path(directory))
                session = Session()
                session.play(chess.Move.from_uci("e2e4"))
                store.save_session(session, DEFAULT_SETTINGS)
                store.close()
                store = Store(Path(directory))
                restored = Session.restore(store.get("session"))
                self.assertEqual(restored.id, session.id)
                self.assertEqual(restored.board.fen(), session.board.fen())
                self.assertEqual(store.history()[0]["result"], "*")
                session.forced_result, session.reason = "1-0", "Black resigned"
                store.save_session(session, DEFAULT_SETTINGS)
                store.save_session(session, DEFAULT_SETTINGS)
                self.assertEqual(len(store.history()), 1)
                self.assertEqual(store.db.execute("SELECT COUNT(*) FROM openings").fetchone()[0], 1)
                self.assertIn("1 completed", store.stats())
                store.close()

        def test_opening_memory_and_undo_cleanup(self):
            with tempfile.TemporaryDirectory() as directory:
                store = Store(Path(directory))
                for _ in range(2):
                    session = Session()
                    session.play(chess.Move.from_uci("e2e4"))
                    session.forced_result = "1-0"
                    store.save_session(session, DEFAULT_SETTINGS)
                self.assertEqual(store.book_move(chess.Board()), chess.Move.from_uci("e2e4"))
                session.forced_result = "*"
                session.board.pop()
                store.save_session(session, DEFAULT_SETTINGS)
                self.assertEqual(len(store.history()), 1)
                self.assertIsNone(store.book_move(chess.Board()))
                store.close()

        def test_engine_legal_time_bounded_and_no_mutation(self):
            board = chess.Board()
            before = board.fen()
            start = time.monotonic()
            result = ChessEngine().search(board, seconds=.15, max_depth=4)
            self.assertIn(result.move, board.legal_moves)
            self.assertEqual(board.fen(), before)
            self.assertEqual(board.move_stack, [])
            self.assertLess(time.monotonic()-start, 3)
            self.assertGreaterEqual(result.depth, 0)

        def test_engine_mate_and_material(self):
            board = chess.Board("7k/8/5KQ1/8/8/8/8/8 w - - 0 1")
            result = ChessEngine().search(board, seconds=.3, max_depth=2)
            self.assertIn(result.move, board.legal_moves)
            board.push(result.move)
            self.assertTrue(board.is_checkmate())
            self.assertGreater(ChessEngine.evaluate(chess.Board("7k/8/8/8/8/8/Q7/K7 w - - 0 1")), 500)

        def test_engine_cancellation_and_restricted_root(self):
            board = chess.Board()
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(SearchCancelled):
                ChessEngine().search(board, .2, 4, cancel)
            move = chess.Move.from_uci("e2e4")
            result = ChessEngine().search(board, .2, 2, root_moves=[move])
            self.assertEqual(result.move, move)
            self.assertEqual(board.fen(), chess.STARTING_FEN)

        def test_match_analysis(self):
            board = chess.Board()
            for uci in ("e2e4", "e7e5"):
                board.push_uci(uci)
            before = board.fen()
            result = analyze_game(board, .25, threading.Event())
            self.assertEqual(len(result["rows"]), 2)
            self.assertEqual(result["rows"][0]["san"], "e4")
            self.assertEqual(result["rows"][1]["side"], "Black")
            for row in result["rows"]:
                self.assertTrue(math.isnan(row["loss"]) or row["loss"] >= 0)
                position = chess.Board(row["before_fen"])
                self.assertIn(chess.Move.from_uci(row["best_uci"]), position.legal_moves)
            self.assertEqual(board.fen(), before)
            self.assertTrue(result["white_accuracy"] is None or 0 <= result["white_accuracy"] <= 100)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NexusTests)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def gui_test() -> bool:
    """Real Tk tests using a temporary database; requires a graphical display."""
    load_tk()
    errors = []
    with tempfile.TemporaryDirectory() as directory:
        root = tk.Tk()
        root.report_callback_exception = lambda kind, value, tb: errors.append(value)
        app = ChessApp(root, Store(Path(directory)))
        def pump_until(predicate, timeout=12):
            deadline = time.monotonic() + timeout
            while not predicate() and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            root.update()
            assert not errors, errors
            assert predicate(), "GUI operation timed out"
        try:
            root.update()
            # Coordinate mapping and orientation: White begins at the bottom.
            x, y = app.square_center(chess.E2)
            assert app.square_at(x, y) == chess.E2
            assert app.square_center(chess.E2)[1] > app.square_center(chess.E7)[1]
            app.mode.set("Human vs Human")
            app.mode_changed()
            app.toggle_pause()
            for square in (chess.E2, chess.E4):
                x, y = app.square_center(square)
                app.canvas.event_generate("<Button-1>", x=int(x), y=int(y))
                root.update()
            assert app.session.board.peek().uci() == "e2e4"
            app.flip()
            assert app.square_center(chess.E2)[1] < app.square_center(chess.E7)[1]
            app.undo()
            assert not app.session.board.move_stack
            # Human-vs-AI returns control to the human after a legal reply.
            app.mode.set("Human vs AI")
            app.level.set("Easy")
            app.mode_changed()
            app.toggle_pause()
            app.commit_move(chess.Move.from_uci("e2e4"))
            pump_until(lambda: len(app.session.board.move_stack) >= 2)
            assert app.is_human()
            app.analyze()
            pump_until(lambda: "analysis" not in app.jobs)
            assert len(app.analysis_rows) == 2
            app.close_analysis()
            app.review(1)
            assert len(app.display_board().move_stack) == 1
            app.go_live()
            assert len(app.display_board().move_stack) == 2
            # Spectator mode, pause, and stale-job cancellation.
            app.mode.set("AI vs AI")
            app.mode_changed()
            app.toggle_pause()
            pump_until(lambda: len(app.session.board.move_stack) >= 4)
            app.toggle_pause()
            stack = list(app.session.board.move_stack)
            pump_until(lambda: not app.jobs)
            assert app.session.board.move_stack == stack
            board = app.session.board.copy(stack=True)
            app.start_job("ai", lambda cancel, emit: ChessEngine().search(board, 2, 7, cancel, emit))
            stale_id = app.jobs["ai"][0]
            app.cancel_play()
            app.messages.put(("ai", stale_id, "done", None))
            root.after_cancel(app.after_poll)
            app.poll_messages()
            assert app.session.board.move_stack == stack
            # Resume reconstructs moves, result, settings, and game identity.
            app.persist()
            restored = Session.restore(app.store.get("session"))
            assert restored.board.fen() == app.session.board.fen()
            assert restored.id == app.session.id
            # Reviews must never survive advancement of the reviewed snapshot.
            app.analyze()
            app.commit_move(next(iter(app.session.board.legal_moves)))
            assert app.analysis_window is None and "analysis" not in app.jobs
            # Historical controls are independent of the current setup widgets.
            historical = Session("Human vs AI")
            historical.controls.update(human="Black", level="Strong")
            historical.headers.update(White="Nexus AI (Strong)", Black="Human")
            historical.play(chess.Move.from_uci("e2e4"))
            assert app.load_session(historical)
            assert app.human.get() == "Black" and app.is_human(chess.BLACK)
            assert app.level.get() == "Strong"
            # Hold a History window open while its selected game finishes.
            ongoing = Session.from_pgn("1. f3 e5 *")
            assert app.load_session(ongoing)
            app.show_history()
            history_window = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            history_tree = next(w for w in descendants(history_window) if isinstance(w, ttk.Treeview))
            open_button = next(w for w in descendants(history_window) if isinstance(w, ttk.Button))
            history_tree.selection_set(app.session.id)
            for san in ("g4", "Qh4#"):
                app.commit_move(app.session.board.parse_san(san))
            open_button.invoke()
            assert app.session.result() == "0-1" and len(app.session.board.move_stack) == 4
            # Preparing a different mode must not rewrite this completed match.
            archived = app.store.saved_game(app.session.id)["pgn"]
            app.mode.set("AI vs AI")
            app.mode_changed()
            app.level.set("Easy")
            app.level_changed()
            assert app.store.saved_game(app.session.id)["pgn"] == archived
            # A failed autosave must not discard the last in-memory copy.
            from unittest.mock import patch
            original_id = app.session.id
            with patch.object(app.store, "save_session", side_effect=sqlite3.OperationalError("test disk failure")), \
                 patch.object(messagebox, "showwarning"), patch.object(messagebox, "askyesno", return_value=False):
                assert not app.load_session(Session())
                app.new_game()
                app.close()
                assert app.session.id == original_id and not app.closed
            app.storage_error_shown = False
            assert not errors, errors
            print("GUI smoke tests passed: rendering, clicks, all modes, replay, analysis, cancellation, autosave, history freshness, controller restore, and save-failure safety.")
        finally:
            app.close()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=Path.home()/".nexus_chess",
                        help="directory for SQLite autosave/history (default: ~/.nexus_chess)")
    parser.add_argument("--self-test", action="store_true", help="run headless checks in temporary storage")
    parser.add_argument("--gui-test", action="store_true", help="run real Tk smoke tests in temporary storage")
    args = parser.parse_args()
    if args.self_test:
        return 0 if self_test() else 1
    if args.gui_test:
        return 0 if gui_test() else 1
    load_tk()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Cannot open the desktop window: {exc}\nRun on a graphical desktop. For headless checks use --self-test.", file=sys.stderr)
        return 1
    root.withdraw()
    try:
        store = Store(args.data_dir)
    except (OSError, sqlite3.Error) as exc:
        messagebox.showerror("Cannot open persistent memory", f"{exc}\n\nTry a writable folder:\npython chess_game.py --data-dir PATH", parent=root)
        root.destroy()
        return 1
    app = ChessApp(root, store)
    def callback_error(kind, value, tb):
        traceback.print_exception(kind, value, tb)
        app.cancel_play()
        app.paused = True
        messagebox.showerror("Nexus Chess error", f"{value}\n\nPlay is paused. Your last successful move was autosaved.", parent=root)
    root.report_callback_exception = callback_error
    root.deiconify()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

