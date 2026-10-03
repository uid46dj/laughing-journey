#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chess Arena - a complete chess application in a single Python file.

Features
--------
* Game modes : Human vs AI, AI vs AI, Human vs Human.
* Engine     : iterative-deepening alpha-beta (PVS) with transposition table,
               quiescence search, null-move pruning, late-move reductions,
               check extensions, killer/history ordering and MVV-LVA.
               Seven playing *styles* (balanced, positional, tactical,
               aggressive, defensive, endgame, wild) on top of a tapered
               evaluation with pawn-structure, king-safety and mobility terms.
* Memory     : everything the app learns is persisted to disk (profile,
               game archive, per-opening statistics, learned book lines,
               positional analysis cache, player skill model).
* Analysis   : centipawn-loss / accuracy grading, blunder and missed-mate
               detection, phase breakdown, coaching hints, annotated PGN and
               JSON report export.
* Interface  : a dependency-free Tk GUI with drag & drop, clocks, a live
               evaluation bar, engine read-outs, promotion picker and an
               analysis notebook.

Usage
-----
    python3 chess_arena.py                 # launch the GUI
    python3 chess_arena.py --selftest      # engine + rules self-test
    python3 chess_arena.py --sim 4         # 4 headless AI vs AI games
    python3 chess_arena.py --analyze g.pgn # analyse a PGN file from the CLI

Only the Python standard library is required (tkinter ships with CPython).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import random
import re
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

APP_NAME = "Chess Arena"
VERSION = "1.0.0"

# --------------------------------------------------------------------------
#  Basic chess vocabulary
# --------------------------------------------------------------------------
WHITE, BLACK = 0, 1
EMPTY = 0
PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING = 1, 2, 3, 4, 5, 6
BLACK_FLAG = 8

PIECE_CHARS = {PAWN: "P", KNIGHT: "N", BISHOP: "B", ROOK: "R", QUEEN: "Q", KING: "K"}
PIECE_NAMES = {PAWN: "pawn", KNIGHT: "knight", BISHOP: "bishop",
               ROOK: "rook", QUEEN: "queen", KING: "king"}

FILES = "abcdefgh"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def make_piece(kind: int, color: int) -> int:
    return kind | (BLACK_FLAG if color == BLACK else 0)


def kind_of(piece: int) -> int:
    return piece & 7


def color_of(piece: int) -> int:
    return BLACK if piece & BLACK_FLAG else WHITE


def opposite(color: int) -> int:
    return color ^ 1


def file_of(square: int) -> int:
    return square & 7


def rank_of(square: int) -> int:
    return square >> 4


def square_of(file_index: int, rank_index: int) -> int:
    return rank_index * 16 + file_index


def square_name(square: int) -> str:
    return FILES[square & 7] + str((square >> 4) + 1)


def parse_square(name: str) -> int:
    return (ord(name[0]) - 97) + (ord(name[1]) - 49) * 16


def mirror_square(square: int) -> int:
    """Flip a square vertically (used by the 'flip board' button)."""
    return (7 - rank_of(square)) * 16 + file_of(square)


# Offsets for the 0x88 board representation.
KNIGHT_OFFSETS = (33, 31, 18, 14, -33, -31, -18, -14)
KING_OFFSETS = (16, -16, 1, -1, 17, 15, -15, -17)
BISHOP_OFFSETS = (17, 15, -15, -17)
ROOK_OFFSETS = (16, -16, 1, -1)

# Move flags
M_NORMAL, M_DPUSH, M_EP, M_CASTLE, M_PROMO = 0, 1, 2, 3, 4

# Castling right bits
CR_WK, CR_WQ, CR_BK, CR_BQ = 1, 2, 4, 8

# Castling rights that survive a move touching a given square.
CASTLE_MASK = {
    0: ~CR_WQ & 0xF, 4: ~(CR_WK | CR_WQ) & 0xF, 7: ~CR_WK & 0xF,          # a1 e1 h1
    112: ~CR_BQ & 0xF, 116: ~(CR_BK | CR_BQ) & 0xF, 119: ~CR_BK & 0xF,    # a8 e8 h8
}

# Zobrist keys -------------------------------------------------------------
_RNG = random.Random(0xC0FFEE1234)
ZOBRIST_PIECE = [[_RNG.getrandbits(64) for _ in range(8)] for _ in range(16)]
ZOBRIST_SIDE = _RNG.getrandbits(64)
ZOBRIST_CASTLE = [_RNG.getrandbits(64) for _ in range(16)]
ZOBRIST_EP = [_RNG.getrandbits(64) for _ in range(8)]

MATE = 30000
MATE_BOUND = MATE - 1000
INFINITY = 32000


def mate_in(ply: int) -> int:
    return MATE - ply


def is_mate_score(score: int) -> bool:
    return abs(score) > MATE_BOUND


def mate_distance(score: int) -> int:
    if score > MATE_BOUND:
        return MATE - score
    if score < -MATE_BOUND:
        return -(MATE - score)
    return 0


def clamp(value, low, high):
    return low if value < low else (high if value > high else value)


def light_square(square: int) -> bool:
    return (file_of(square) + rank_of(square)) % 2 == 0


class SearchTimeout(Exception):
    """Raised internally when the search exceeds its time budget."""


def utc_stamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ==========================================================================
#  BOARD  -  0x88 mailbox representation, Zobrist hashing, make/unmake
# ==========================================================================
class Board:
    """A full chess position with legal move generation and hashing."""

    __slots__ = ("sq", "side", "castling", "ep", "half", "full", "kings",
                 "hash", "stack", "rep", "_legal")

    def __init__(self, fen: str = START_FEN):
        self.stack = []
        self.rep = defaultdict(int)
        self._legal = None
        self.set_fen(fen)

    # -- construction ------------------------------------------------------
    def set_fen(self, fen: str) -> "Board":
        parts = fen.split()
        rows = parts[0].split("/")
        if len(rows) != 8:
            raise ValueError("bad FEN: %r" % fen)
        sq = [EMPTY] * 128
        for row_index, row in enumerate(rows):
            rank = 7 - row_index
            file_index = 0
            for ch in row:
                if ch.isdigit():
                    file_index += int(ch)
                else:
                    color = WHITE if ch.isupper() else BLACK
                    kind = {"P": PAWN, "N": KNIGHT, "B": BISHOP,
                            "R": ROOK, "Q": QUEEN, "K": KING}[ch.upper()]
                    sq[square_of(file_index, rank)] = make_piece(kind, color)
                    file_index += 1
        self.sq = sq
        self.side = WHITE if parts[1] == "w" else BLACK
        self.castling = 0
        if len(parts) > 2 and parts[2] != "-":
            for ch in parts[2]:
                self.castling |= {"K": CR_WK, "Q": CR_WQ, "k": CR_BK, "q": CR_BQ}[ch]
        self.ep = parse_square(parts[3]) if len(parts) > 3 and parts[3] != "-" else -1
        self.half = int(parts[4]) if len(parts) > 4 else 0
        self.full = int(parts[5]) if len(parts) > 5 else 1
        self.kings = [sq.index(make_piece(KING, WHITE)),
                      sq.index(make_piece(KING, BLACK))]
        self.hash = self.compute_hash()
        self.stack = []
        self.rep = defaultdict(int)
        self.rep[self.key()] = 1
        self._legal = None
        return self

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row, gap = "", 0
            for file_index in range(8):
                piece = self.sq[square_of(file_index, rank)]
                if piece == EMPTY:
                    gap += 1
                else:
                    if gap:
                        row += str(gap)
                        gap = 0
                    ch = PIECE_CHARS[kind_of(piece)]
                    row += ch if color_of(piece) == WHITE else ch.lower()
            if gap:
                row += str(gap)
            rows.append(row)
        castling = "".join(ch for ch, bit in
                           (("K", CR_WK), ("Q", CR_WQ), ("k", CR_BK), ("q", CR_BQ))
                           if self.castling & bit) or "-"
        ep = self.usable_ep()
        return "%s %s %s %s %d %d" % ("/".join(rows),
                                      "w" if self.side == WHITE else "b",
                                      castling,
                                      square_name(ep) if ep != -1 else "-",
                                      self.half, self.full)

    def clone(self) -> "Board":
        other = Board.__new__(Board)
        other.sq = list(self.sq)
        other.side = self.side
        other.castling = self.castling
        other.ep = self.ep
        other.half = self.half
        other.full = self.full
        other.kings = list(self.kings)
        other.hash = self.hash
        other.stack = []
        other.rep = dict(self.rep)
        other._legal = None
        return other

    def compute_hash(self) -> int:
        h = 0
        for square in range(128):
            if square & 0x88:
                continue
            piece = self.sq[square]
            if piece:
                h ^= ZOBRIST_PIECE[piece][file_of(square)]
        if self.side == BLACK:
            h ^= ZOBRIST_SIDE
        h ^= ZOBRIST_CASTLE[self.castling]
        if self.ep != -1:
            h ^= ZOBRIST_EP[file_of(self.ep)]
        return h

    def usable_ep(self) -> int:
        """The en-passant square, but only when a capture is really available.

        FEN (and the repetition rule) both require the ep field to be cleared
        unless an enemy pawn can actually make the capture.
        """
        ep = self.ep
        if ep == -1:
            return -1
        # White pawns capture upward from ep-15 / ep-17, black pawns capture
        # downward from ep+15 / ep+17 - the same convention as attacked_by().
        if self.side == WHITE:
            a, b, pawn = ep - 15, ep - 17, make_piece(PAWN, WHITE)
        else:
            a, b, pawn = ep + 15, ep + 17, make_piece(PAWN, BLACK)
        for square in (a, b):
            if 0 <= square < 128 and not (square & 0x88) and self.sq[square] == pawn:
                return ep
        return -1

    def key(self):
        """Repetition key (position hash + castling + relevant ep square)."""
        return (self.hash, self.castling, self.usable_ep())

    def ascii(self) -> str:
        lines = []
        for rank in range(7, -1, -1):
            row = ""
            for file_index in range(8):
                piece = self.sq[square_of(file_index, rank)]
                row += "." if piece == EMPTY else (
                    PIECE_CHARS[kind_of(piece)] if color_of(piece) == WHITE
                    else PIECE_CHARS[kind_of(piece)].lower())
            lines.append("%d %s" % (rank + 1, row))
        lines.append("  a b c d e f g h")
        lines.append("FEN: " + self.fen())
        return "\n".join(lines)

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        return self.ascii()

    # -- make / unmake -----------------------------------------------------
    def make_move(self, move) -> None:
        """Apply *move* (frm, to, promo, flag) in place."""
        frm, to, promo, flag = move
        sq = self.sq
        side = self.side
        piece = sq[frm]
        kind = kind_of(piece)
        old_hash = self.hash
        h = old_hash ^ ZOBRIST_PIECE[piece][file_of(frm)] ^ ZOBRIST_SIDE

        cap_sq = to
        captured = sq[to]
        if flag == M_EP:
            # A white pawn captures upward onto the ep square, so the black
            # pawn it removes sits one rank *below* (to - 16); a black pawn
            # captures downward, so the white pawn it removes sits one rank
            # *above* (to + 16).
            cap_sq = to - 16 if side == WHITE else to + 16
            captured = sq[cap_sq]
        if captured:
            h ^= ZOBRIST_PIECE[captured][file_of(cap_sq)]

        sq[frm] = EMPTY
        if flag == M_EP:
            # Unlike a normal capture, the captured pawn does not stand on
            # the destination square, so it has to be cleared explicitly.
            sq[cap_sq] = EMPTY
        placed = make_piece(promo, side) if flag == M_PROMO else piece
        sq[to] = placed
        h ^= ZOBRIST_PIECE[placed][file_of(to)]

        if flag == M_CASTLE:
            rook_from, rook_to = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
            rook = sq[rook_from]
            sq[rook_from] = EMPTY
            sq[rook_to] = rook
            h ^= ZOBRIST_PIECE[rook][file_of(rook_from)]
            h ^= ZOBRIST_PIECE[rook][file_of(rook_to)]

        old_castling, old_ep = self.castling, self.ep
        old_half, old_full, old_king = self.half, self.full, self.kings[side]

        new_castling = old_castling & CASTLE_MASK.get(frm, 0xF) & CASTLE_MASK.get(to, 0xF)
        if new_castling != old_castling:
            h ^= ZOBRIST_CASTLE[old_castling] ^ ZOBRIST_CASTLE[new_castling]
        self.castling = new_castling

        if old_ep != -1:
            h ^= ZOBRIST_EP[file_of(old_ep)]
        if flag == M_DPUSH:
            self.ep = (frm + to) >> 1
            h ^= ZOBRIST_EP[file_of(self.ep)]
        else:
            self.ep = -1

        self.half = 0 if (kind == PAWN or captured) else old_half + 1
        self.full = old_full + (1 if side == BLACK else 0)
        if kind == KING:
            self.kings[side] = to
        self.side = opposite(side)
        self.hash = h
        self.stack.append((move, piece, captured, cap_sq, old_castling, old_ep,
                           old_half, old_full, old_king, side, old_hash))
        self.rep[self.key()] += 1
        self._legal = None

    def unmake_move(self) -> None:
        """Undo the last move played."""
        (move, piece, captured, cap_sq, castling, ep, half, full,
         king_sq, side, old_hash) = self.stack.pop()
        current_key = self.key()
        self.rep[current_key] -= 1
        if self.rep[current_key] <= 0:
            del self.rep[current_key]
        frm, to, promo, flag = move
        self.side = side
        self.sq[to] = EMPTY
        self.sq[frm] = piece
        if captured:
            self.sq[cap_sq] = captured
        if flag == M_CASTLE:
            rook_from, rook_to = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
            self.sq[rook_to] = EMPTY
            self.sq[rook_from] = make_piece(ROOK, side)
        self.castling = castling
        self.ep = ep
        self.half = half
        self.full = full
        self.kings[side] = king_sq
        self.hash = old_hash
        self._legal = None

    # -- attack detection --------------------------------------------------
    def attacked_by(self, square: int, by: int) -> bool:
        """True when *square* is attacked by a piece of colour *by*."""
        sq = self.sq
        # A white pawn captures upwards, so a white pawn attacking *square*
        # stands on square-15 / square-17; a black pawn (capturing downwards)
        # stands on square+15 / square+17.  The 0x88 mask rejects the squares
        # where the file offset would wrap around the board edge.
        if by == WHITE:
            pawn = make_piece(PAWN, WHITE)
            for offset in (-15, -17):
                target = square + offset
                if 0 <= target < 128 and not (target & 0x88) and sq[target] == pawn:
                    return True
        else:
            pawn = make_piece(PAWN, BLACK)
            for offset in (15, 17):
                target = square + offset
                if 0 <= target < 128 and not (target & 0x88) and sq[target] == pawn:
                    return True
        knight = make_piece(KNIGHT, by)
        for offset in KNIGHT_OFFSETS:
            target = square + offset
            if 0 <= target < 128 and not (target & 0x88) and sq[target] == knight:
                return True
        king = make_piece(KING, by)
        for offset in KING_OFFSETS:
            target = square + offset
            if 0 <= target < 128 and not (target & 0x88) and sq[target] == king:
                return True
        for offsets, slider in ((BISHOP_OFFSETS, BISHOP), (ROOK_OFFSETS, ROOK)):
            for offset in offsets:
                target = square + offset
                while 0 <= target < 128 and not (target & 0x88):
                    piece = sq[target]
                    if piece:
                        if color_of(piece) == by and kind_of(piece) in (slider, QUEEN):
                            return True
                        break
                    target += offset
        return False

    def in_check(self, color: int = -1) -> bool:
        """True when the king of *color* (default: side to move) is attacked."""
        if color < 0:
            color = self.side
        return self.attacked_by(self.kings[color], opposite(color))

    # -- move generation ---------------------------------------------------
    def generate_moves(self, color: int = -1, captures_only: bool = False) -> list:
        """Pseudo-legal moves for *color* (defaults to the side to move)."""
        if color < 0:
            color = self.side
        sq = self.sq
        ep = self.ep
        moves = []
        forward = 16 if color == WHITE else -16
        start_rank = 1 if color == WHITE else 6
        promo_rank = 7 if color == WHITE else 0
        enemy = opposite(color)

        for square in range(128):
            if square & 0x88:
                continue
            piece = sq[square]
            if not piece or color_of(piece) != color:
                continue
            kind = kind_of(piece)
            if kind == PAWN:
                if not captures_only:
                    one = square + forward
                    if 0 <= one < 128 and not (one & 0x88) and not sq[one]:
                        if rank_of(one) == promo_rank:
                            for promoted in (QUEEN, ROOK, BISHOP, KNIGHT):
                                moves.append((square, one, promoted, M_PROMO))
                        else:
                            moves.append((square, one, 0, M_NORMAL))
                            two = square + 2 * forward
                            if rank_of(square) == start_rank and not sq[two]:
                                moves.append((square, two, 0, M_DPUSH))
                for offset in ((15, 17) if color == WHITE else (-15, -17)):
                    target = square + offset
                    if not (0 <= target < 128) or (target & 0x88):
                        continue
                    victim = sq[target]
                    if victim and color_of(victim) == enemy:
                        if rank_of(target) == promo_rank:
                            for promoted in (QUEEN, ROOK, BISHOP, KNIGHT):
                                moves.append((square, target, promoted, M_PROMO))
                        else:
                            moves.append((square, target, 0, M_NORMAL))
                    elif target == ep and victim == EMPTY:
                        moves.append((square, target, 0, M_EP))
            elif kind in (KNIGHT, KING):
                for offset in (KNIGHT_OFFSETS if kind == KNIGHT else KING_OFFSETS):
                    target = square + offset
                    if 0 <= target < 128 and not (target & 0x88):
                        victim = sq[target]
                        if not victim or color_of(victim) == enemy:
                            moves.append((square, target, 0, M_NORMAL))
            else:
                if kind in (BISHOP, QUEEN):
                    for offset in BISHOP_OFFSETS:
                        target = square + offset
                        while 0 <= target < 128 and not (target & 0x88):
                            victim = sq[target]
                            if victim:
                                if color_of(victim) == enemy:
                                    moves.append((square, target, 0, M_NORMAL))
                                break
                            if not captures_only:
                                moves.append((square, target, 0, M_NORMAL))
                            target += offset
                if kind in (ROOK, QUEEN):
                    for offset in ROOK_OFFSETS:
                        target = square + offset
                        while 0 <= target < 128 and not (target & 0x88):
                            victim = sq[target]
                            if victim:
                                if color_of(victim) == enemy:
                                    moves.append((square, target, 0, M_NORMAL))
                                break
                            if not captures_only:
                                moves.append((square, target, 0, M_NORMAL))
                            target += offset

        if not captures_only:
            self._add_castling(color, moves)
        return moves

    def _add_castling(self, color: int, moves: list) -> None:
        sq = self.sq
        enemy = opposite(color)
        home = 4 if color == WHITE else 116
        if sq[home] != make_piece(KING, color):
            return
        rook = make_piece(ROOK, color)
        if self.castling & (CR_WK if color == WHITE else CR_BK):
            if (sq[home + 1] == EMPTY and sq[home + 2] == EMPTY and sq[home + 3] == rook
                    and not self.attacked_by(home, enemy)
                    and not self.attacked_by(home + 1, enemy)
                    and not self.attacked_by(home + 2, enemy)):
                moves.append((home, home + 2, 0, M_CASTLE))
        if self.castling & (CR_WQ if color == WHITE else CR_BQ):
            if (sq[home - 1] == EMPTY and sq[home - 2] == EMPTY and sq[home - 3] == EMPTY
                    and sq[home - 4] == rook
                    and not self.attacked_by(home, enemy)
                    and not self.attacked_by(home - 1, enemy)
                    and not self.attacked_by(home - 2, enemy)):
                moves.append((home, home - 2, 0, M_CASTLE))

    def legal_moves(self) -> list:
        """Fully legal moves for the side to move (cached until next move)."""
        if self._legal is None:
            side = self.side
            enemy = opposite(side)
            moves = []
            for move in self.generate_moves(side):
                self.make_move(move)
                if not self.attacked_by(self.kings[side], enemy):
                    moves.append(move)
                self.unmake_move()
            self._legal = moves
        return self._legal

    # -- queries -----------------------------------------------------------
    def is_capture(self, move) -> bool:
        return bool(self.sq[move[1]]) or move[3] == M_EP

    def piece_moved(self, move) -> int:
        return kind_of(self.sq[move[0]])

    def insufficient_material(self) -> bool:
        minors = {WHITE: [], BLACK: []}
        for square in range(128):
            if square & 0x88:
                continue
            piece = self.sq[square]
            if not piece:
                continue
            kind = kind_of(piece)
            if kind in (PAWN, ROOK, QUEEN):
                return False
            if kind in (BISHOP, KNIGHT):
                minors[color_of(piece)].append(square)
        if not minors[WHITE] or not minors[BLACK]:
            return True
        if len(minors[WHITE]) == 1 and len(minors[BLACK]) == 1:
            if kind_of(self.sq[minors[WHITE][0]]) == BISHOP and \
                    kind_of(self.sq[minors[BLACK][0]]) == BISHOP:
                if light_square(minors[WHITE][0]) == light_square(minors[BLACK][0]):
                    return True
        return False

    def outcome(self) -> dict:
        """Classify the position: result string + termination reason."""
        if self.legal_moves():
            if self.rep.get(self.key(), 0) >= 3:
                return {"result": "1/2-1/2", "termination": "threefold repetition"}
            if self.half >= 100:
                return {"result": "1/2-1/2", "termination": "fifty-move rule"}
            return {"result": "*", "termination": "*"}
        if self.in_check():
            return {"result": "1-0" if self.side == BLACK else "0-1",
                    "termination": "checkmate"}
        return {"result": "1/2-1/2", "termination": "stalemate"}

    def is_game_over(self) -> bool:
        if not self.legal_moves():
            return True
        if self.rep.get(self.key(), 0) >= 3 or self.half >= 100:
            return True
        return self.insufficient_material()

    def uci(self, move) -> str:
        frm, to, promo, _ = move
        text = square_name(frm) + square_name(to)
        if promo:
            text += {QUEEN: "q", ROOK: "r", BISHOP: "b", KNIGHT: "n"}[promo]
        return text

    def san(self, move) -> str:
        """Standard Algebraic Notation for a legal *move*."""
        frm, to, promo, flag = move
        kind = kind_of(self.sq[frm])
        if flag == M_CASTLE:
            text = "O-O" if to > frm else "O-O-O"
        elif kind == PAWN:
            text = (FILES[file_of(frm)] + "x" if self.is_capture(move) else "") + square_name(to)
            if flag == M_PROMO:
                text += "=" + {QUEEN: "Q", ROOK: "R", BISHOP: "B", KNIGHT: "N"}[promo]
        else:
            capture = "x" if self.is_capture(move) else ""
            text = "%s%s%s%s" % (PIECE_CHARS[kind], self._disambiguate(frm, to, kind),
                                 capture, square_name(to))
        self.make_move(move)
        if self.in_check():
            text += "#" if not self.legal_moves() else "+"
        self.unmake_move()
        return text

    def _disambiguate(self, frm: int, to: int, kind: int) -> str:
        rivals = [m[0] for m in self.legal_moves()
                  if m[1] == to and m[0] != frm and kind_of(self.sq[m[0]]) == kind]
        if not rivals:
            return ""
        if all(file_of(s) != file_of(frm) for s in rivals):
            return FILES[file_of(frm)]
        if all(rank_of(s) != rank_of(frm) for s in rivals):
            return str(rank_of(frm) + 1)
        return square_name(frm)

    def find_move(self, text: str):
        """Look up a move from UCI ('e2e4') or SAN ('Nf3', 'O-O', 'exd5')."""
        text = text.strip()
        if not text:
            return None
        for move in self.legal_moves():
            if self.uci(move) == text.lower():
                return move
        for move in self.legal_moves():
            if self.san(move) == text:
                return move
        return None

    def perft(self, depth: int) -> int:
        """Node count - used by the self-test to validate move generation."""
        if depth == 0:
            return 1
        total = 0
        for move in self.legal_moves():
            self.make_move(move)
            total += self.perft(depth - 1)
            self.unmake_move()
        return total


# ==========================================================================
#  EVALUATION  -  tapered material + piece-square tables and structure terms
# ==========================================================================
MG_VALUE = {PAWN: 82, KNIGHT: 337, BISHOP: 365, ROOK: 477, QUEEN: 1025, KING: 0}
EG_VALUE = {PAWN: 94, KNIGHT: 281, BISHOP: 297, ROOK: 512, QUEEN: 936, KING: 0}
# Phase weights; the sum over a full board is 24.
PHASE_WEIGHT = {PAWN: 0, KNIGHT: 1, BISHOP: 1, ROOK: 2, QUEEN: 4, KING: 0}

# Piece-square tables, written from White's point of view with a1 first.
MG_PAWN = (0, 0, 0, 0, 0, 0, 0, 0,
           98, 134, 61, 95, 68, 126, 34, -11,
           -6, 7, 26, 31, 65, 56, 25, -20,
           -14, 13, 6, 21, 23, 12, 17, -23,
           -27, -2, -5, 12, 17, 6, 10, -25,
           -26, -4, -4, -10, 3, 3, 33, -12,
           -35, -1, -20, -23, -15, 24, 38, -22,
           0, 0, 0, 0, 0, 0, 0, 0)
EG_PAWN = (0, 0, 0, 0, 0, 0, 0, 0,
           178, 173, 158, 134, 147, 132, 165, 187,
           94, 100, 85, 67, 56, 53, 82, 84,
           32, 24, 13, 5, -2, 4, 17, 17,
           13, 9, -3, -7, -7, -8, 3, -1,
           4, 7, -6, 1, 0, -5, -1, -8,
           13, 8, 8, 10, 13, 0, 2, -7,
           0, 0, 0, 0, 0, 0, 0, 0)
MG_KNIGHT = (-167, -89, -34, -49, 61, -97, -15, -107,
             -73, -41, 72, 36, 23, 62, 7, -17,
             -47, 60, 37, 65, 84, 129, 73, 44,
             -9, 17, 19, 53, 37, 69, 18, 22,
             -13, 4, 16, 13, 28, 19, 21, -8,
             -23, -9, 12, 10, 19, 17, 25, -16,
             -29, -53, -12, -3, -1, 18, -14, -19,
             -105, -21, -58, -33, -17, -28, -19, -23)
EG_KNIGHT = (-58, -38, -13, -28, -31, -27, -63, -99,
             -25, -8, -25, -2, -9, -25, -24, -52,
             -24, -20, 10, 9, -1, -9, -19, -41,
             -17, 3, 22, 22, 22, 11, 8, -18,
             -18, -6, 16, 25, 16, 17, 4, -18,
             -23, -3, -1, 15, 10, -3, -20, -22,
             -42, -20, -10, -5, -2, -20, -23, -44,
             -29, -51, -23, -15, -22, -18, -50, -64)
MG_BISHOP = (-29, 4, -82, -37, -25, -42, 7, -8,
             -26, 16, -18, -13, 30, 59, 18, -47,
             -16, 37, 43, 40, 35, 50, 37, -2,
             -4, 5, 19, 50, 37, 37, 7, -2,
             -6, 13, 13, 26, 34, 12, 10, 4,
             0, 15, 15, 15, 14, 27, 18, 10,
             4, 15, 16, 0, 7, 21, 33, 1,
             -33, -3, -14, -21, -13, -12, -39, -21)
EG_BISHOP = (-14, -21, -11, -8, -7, -9, -17, -24,
             -8, -4, 7, -12, -3, -13, -4, -14,
             2, -8, 0, -1, -2, 6, 0, 4,
             -3, 9, 12, 9, 14, 10, 3, 2,
             -6, 3, 13, 19, 7, 10, -3, -9,
             -12, -3, 8, 10, 13, 3, -7, -15,
             -14, -18, -7, -1, 4, -9, -15, -27,
             -23, -9, -23, -5, -9, -16, -5, -17)
MG_ROOK = (32, 42, 32, 51, 63, 9, 31, 43,
           27, 32, 58, 62, 80, 67, 26, 44,
           -5, 19, 26, 36, 17, 45, 61, 16,
           -24, -11, 7, 26, 24, 35, -8, -20,
           -36, -26, -12, -1, 9, -7, 6, -23,
           -45, -25, -16, -17, 3, 0, -5, -33,
           -44, -16, -20, -9, -1, 11, -6, -71,
           -19, -13, 1, 17, 16, 7, -37, -26)
EG_ROOK = (13, 10, 18, 15, 12, 12, 8, 5,
           11, 13, 13, 11, -3, 3, 8, 3,
           7, 7, 7, 5, 4, -3, -5, -3,
           4, 3, 13, 1, 2, 1, -1, 2,
           3, 5, 8, 4, -5, -6, -8, -11,
           -4, 0, -5, -1, -7, -12, -8, -16,
           -6, -6, 0, 2, -9, -9, -11, -3,
           -9, 2, 3, -1, -5, -13, 4, -20)
MG_QUEEN = (-28, 0, 29, 12, 59, 44, 43, 45,
            -24, -39, -5, 1, -16, 57, 28, 54,
            -13, -17, 7, 8, 29, 56, 47, 57,
            -27, -27, -16, -16, -1, 17, -2, 1,
            -9, -26, -9, -10, -2, -4, 3, -3,
            -14, 2, -11, -2, -5, 2, 14, 5,
            -35, -8, 11, 2, 8, 15, -3, 1,
            -1, -18, -9, 10, -15, -25, -31, -50)
EG_QUEEN = (-9, 22, 22, 27, 27, 19, 10, 20,
            -17, 20, 32, 41, 58, 25, 30, 0,
            -20, 6, 9, 49, 47, 35, 19, 9,
            3, 22, 24, 45, 57, 40, 57, 36,
            -18, 28, 19, 47, 31, 34, 39, 23,
            -16, -27, 15, 6, 9, 17, 10, 5,
            -22, -23, -30, -16, -16, -23, -36, -32,
            -33, -28, -22, -43, -5, -32, -20, -41)
MG_KING = (-65, 23, 16, -15, -56, -34, 2, 13,
           29, -1, -20, -7, -8, -4, -38, -29,
           -9, 24, 2, -16, -20, 6, 22, -22,
           -17, -20, -12, -27, -30, -25, -14, -36,
           -49, -1, -27, -39, -46, -44, -33, -51,
           -14, -14, -22, -46, -44, -30, -15, -27,
           1, 7, -8, -64, -43, -16, 9, 8,
           -15, 36, 12, -54, 8, -28, 24, 14)
EG_KING = (-74, -35, -18, -18, -11, 15, 4, -17,
           -12, 17, 14, 17, 17, 38, 23, 11,
           10, 17, 23, 15, 20, 45, 44, 13,
           -8, 22, 24, 27, 26, 33, 26, 3,
           -18, -4, 21, 24, 27, 23, 9, -11,
           -19, -3, 11, 21, 23, 16, 7, -9,
           -27, -11, 4, 13, 14, 4, -5, -17,
           -53, -34, -21, -11, -28, -14, -24, -43)

PST_MG = {PAWN: MG_PAWN, KNIGHT: MG_KNIGHT, BISHOP: MG_BISHOP,
          ROOK: MG_ROOK, QUEEN: MG_QUEEN, KING: MG_KING}
PST_EG = {PAWN: EG_PAWN, KNIGHT: EG_KNIGHT, BISHOP: EG_BISHOP,
          ROOK: EG_ROOK, QUEEN: EG_QUEEN, KING: EG_KING}

# Precompute lookup tables indexed by [piece code][square] so the inner
# evaluation loop needs a single list access per piece.
MG_TABLE = [[0] * 128 for _ in range(16)]
EG_TABLE = [[0] * 128 for _ in range(16)]
for _kind in (PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING):
    for _color in (WHITE, BLACK):
        _code = make_piece(_kind, _color)
        for _sq in range(128):
            if _sq & 0x88:
                continue
            _rel = _sq if _color == WHITE else mirror_square(_sq)
            MG_TABLE[_code][_sq] = MG_VALUE[_kind] + PST_MG[_kind][_rel]
            EG_TABLE[_code][_sq] = EG_VALUE[_kind] + PST_EG[_kind][_rel]

PASSED_PAWN_BONUS = (0, 8, 14, 26, 48, 84, 140, 0)
ISOLATED_PAWN_PENALTY = 12
DOUBLED_PAWN_PENALTY = 11
BISHOP_PAIR_BONUS = 32
ROOK_OPEN_FILE = 22
ROOK_SEMI_OPEN_FILE = 11
KING_SHIELD_BONUS = 11
TEMPO_BONUS = 12

# MVV-LVA capture ordering table.
MVV_LVA = [[0] * 128 for _ in range(16)]
for _attacker in range(16):
    for _victim in range(16):
        MVV_LVA[_attacker][_victim] = (
            (MG_VALUE[_victim & 7] if _victim else 0) * 16 -
            MG_VALUE[_attacker & 7 if _attacker else 0])



# ==========================================================================
#  EVALUATOR  -  tapered evaluation with a small set of style personalities
# ==========================================================================
#                 struct  king   piece  tempo
STYLES = {
    "balanced":   (1.00, 1.00, 1.00, 1.00),
    "positional": (1.30, 1.15, 1.00, 0.70),
    "tactical":   (0.60, 0.90, 1.25, 1.50),
    "aggressive": (0.80, 1.60, 1.10, 1.30),
    "defensive":  (1.25, 0.55, 0.95, 0.60),
    "endgame":    (1.10, 0.40, 0.85, 0.50),
    "wild":       (0.70, 1.45, 1.20, 1.70),
}
STYLE_DESCRIPTIONS = {
    "balanced":   "Solid all-round play, no particular bias.",
    "positional": "Prefers structure, space and long-term pawn advantages.",
    "tactical":   "Sharp and forcing; hunts for material and checks.",
    "aggressive": "Attacks the king, storms the position, accepts risk.",
    "defensive":  "Solid, conservative, rarely gambles on anything.",
    "endgame":    "Simplifies early and thrives on technique and pawns.",
    "wild":       "Chaotic creativity; the most surprising opponent.",
}
STYLE_NAMES = list(STYLES)


class Evaluator:
    """Static evaluation.  Scores are always from the side-to-move's view."""

    def __init__(self, style: str = "balanced"):
        self.set_style(style)

    def set_style(self, style: str) -> None:
        self.style = style if style in STYLES else "balanced"
        self.w_struct, self.w_king, self.w_piece, self.w_tempo = STYLES[self.style]

    def evaluate(self, board: Board) -> int:
        """Return the static score in centipawns from the mover's view."""
        sq = board.sq
        mg_w = mg_b = eg_w = eg_b = 0
        phase = 0
        pawn_files_w = [0] * 8
        pawn_files_b = [0] * 8
        pawn_counts_w = [0] * 8
        pawn_counts_b = [0] * 8
        bishops_w = bishops_b = 0
        rooks_w, rooks_b = [], []
        white_pawns, black_pawns = [], []

        for square in range(128):
            if square & 0x88:
                continue
            piece = sq[square]
            if not piece:
                continue
            mg = MG_TABLE[piece][square]
            eg = EG_TABLE[piece][square]
            kind = piece & 7
            phase += PHASE_WEIGHT[kind]
            if piece & BLACK_FLAG:
                mg_b += mg
                eg_b += eg
            else:
                mg_w += mg
                eg_w += eg
            if kind == PAWN:
                f = square & 7
                if piece & BLACK_FLAG:
                    pawn_files_b[f] += 1
                    pawn_counts_b[f] += 1
                    black_pawns.append(square)
                else:
                    pawn_files_w[f] += 1
                    pawn_counts_w[f] += 1
                    white_pawns.append(square)
            elif kind == BISHOP:
                if piece & BLACK_FLAG:
                    bishops_b += 1
                else:
                    bishops_w += 1

        # --- pawn structure -------------------------------------------------
        struct = 0
        for square in white_pawns:
            f, r = square & 7, square >> 4
            left_clear = (f == 0) or not pawn_files_b[f - 1]
            right_clear = (f == 7) or not pawn_files_b[f + 1]
            if left_clear and right_clear:
                struct += PASSED_PAWN_BONUS[r]
            isolated = ((f == 0 or not pawn_files_w[f - 1]) and
                        (f == 7 or not pawn_files_w[f + 1]))
            if isolated:
                struct -= ISOLATED_PAWN_PENALTY
        for square in black_pawns:
            f, r = square & 7, square >> 4
            left_clear = (f == 0) or not pawn_files_w[f - 1]
            right_clear = (f == 7) or not pawn_files_w[f + 1]
            if left_clear and right_clear:
                struct -= PASSED_PAWN_BONUS[7 - r]
            isolated = ((f == 0 or not pawn_files_b[f - 1]) and
                        (f == 7 or not pawn_files_b[f + 1]))
            if isolated:
                struct += ISOLATED_PAWN_PENALTY
        for f in range(8):
            if pawn_counts_w[f] > 1:
                struct -= DOUBLED_PAWN_PENALTY * (pawn_counts_w[f] - 1)
            if pawn_counts_b[f] > 1:
                struct += DOUBLED_PAWN_PENALTY * (pawn_counts_b[f] - 1)

        # --- bishops and rooks ---------------------------------------------
        piece_score = 0
        if bishops_w >= 2:
            piece_score += BISHOP_PAIR_BONUS
        if bishops_b >= 2:
            piece_score -= BISHOP_PAIR_BONUS
        for square in rooks_w:
            f = square & 7
            if not pawn_files_w[f] and not pawn_files_b[f]:
                piece_score += ROOK_OPEN_FILE
            elif not pawn_files_w[f]:
                piece_score += ROOK_SEMI_OPEN_FILE
        for square in rooks_b:
            f = square & 7
            if not pawn_files_w[f] and not pawn_files_b[f]:
                piece_score -= ROOK_OPEN_FILE
            elif not pawn_files_b[f]:
                piece_score -= ROOK_SEMI_OPEN_FILE

        # --- king safety ----------------------------------------------------
        king_score = (self._king_safety(board, pawn_files_w, pawn_files_b, WHITE) -
                      self._king_safety(board, pawn_files_w, pawn_files_b, BLACK))

        # --- interpolate between middlegame and endgame ---------------------
        if phase > 24:
            phase = 24
        eg_phase = 24 - phase
        mid = ((mg_w + self.w_piece * piece_score - self.w_king * king_score
                + self.w_struct * struct) -
               (mg_b - self.w_piece * piece_score + self.w_king * king_score
                - self.w_struct * struct))
        end = ((eg_w + self.w_piece * piece_score * 0.6 - self.w_struct * struct) -
               (eg_b - self.w_piece * piece_score * 0.6 + self.w_struct * struct))
        score = (mid * phase + end * eg_phase) // 24
        if board.side == BLACK:
            score = -score
        return score + int(self.w_tempo * TEMPO_BONUS)

    def _king_safety(self, board: Board, files_w, files_b, color: int) -> int:
        """Pawn-shield and open-file pressure around *color*'s king."""
        king = board.kings[color]
        kf, kr = king & 7, king >> 4
        step = 1 if color == WHITE else -1
        own_files, enemy_files = (files_w, files_b) if color == WHITE else (files_b, files_w)
        total = 0
        for df in (-1, 0, 1):
            f = kf + df
            if 0 <= f <= 7:
                shield_rank = kr + step
                if 0 <= shield_rank <= 7 and own_files[f]:
                    total += KING_SHIELD_BONUS
                if not enemy_files[f]:
                    total -= 3
        return total

    def evaluate_white(self, board: Board) -> int:
        """Score from White's point of view (used by the analyser)."""
        saved = board.side
        board.side = WHITE
        try:
            return self.evaluate(board)
        finally:
            board.side = saved


# ==========================================================================
#  TRANSPOSITION TABLE
# ==========================================================================
TT_EXACT, TT_LOWER, TT_UPPER = 0, 1, 2
TT_BUCKET_BITS = 16                      # 65 536 buckets
TT_MASK = (1 << TT_BUCKET_BITS) - 1


class TTEntry:
    """One transposition slot (plain class with __slots__ for speed)."""

    __slots__ = ("key", "depth", "score", "flag", "move", "age")

    def __init__(self, key=0, depth=-1, score=0, flag=TT_EXACT, move=None, age=0):
        self.key = key
        self.depth = depth
        self.score = score
        self.flag = flag
        self.move = move
        self.age = age


class TranspositionTable:
    """Fixed-capacity table with bucket replacement (fast + bounded memory)."""

    def __init__(self, max_mb: int = 48):
        self.entries = {}
        self.order = 0
        self.hits = 0
        self.misses = 0
        self.enabled = True
        self.max_mb = max_mb
        self._limit = max(4096, max_mb * 1024)

    def clear(self) -> None:
        self.entries.clear()
        self.order = 0
        self.hits = 0
        self.misses = 0

    def resize(self, max_mb: int) -> None:
        self.max_mb = max_mb
        self._limit = max(4096, max_mb * 1024)
        self.clear()

    def store(self, key: int, depth: int, score: int, flag: int, move) -> None:
        if not self.enabled:
            return
        self.order += 1
        slot = key & TT_MASK
        current = self.entries.get(slot)
        if current is not None and current.key == key and \
                current.depth > depth + 2 and self.order - current.age < 16:
            return
        self.entries[slot] = TTEntry(key, depth, score, flag, move, self.order)
        if len(self.entries) > self._limit:
            self._evict()

    def _evict(self) -> None:
        victims = sorted(self.entries.items(), key=lambda kv: kv[1].age)
        for slot, _ in victims[:max(1, len(self.entries) // 4)]:
            del self.entries[slot]

    def probe(self, key: int, depth: int):
        """Return (flag, entry); flag is None when the entry is too shallow."""
        entry = self.entries.get(key & TT_MASK)
        if entry is None or entry.key != key:
            self.misses += 1
            return None, None
        self.hits += 1
        if entry.depth >= depth:
            return entry.flag, entry
        return None, entry

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"entries": len(self.entries), "limit": self._limit,
                "hits": self.hits, "misses": self.misses,
                "hit_rate": (100.0 * self.hits / total) if total else 0.0}


class TimeManager:
    """Turns a clock position into a wall-clock deadline for a single search."""

    def __init__(self, time_left: float, increment: float, moves_left: int,
                 base: float, cap: float):
        time_left = max(0.0, time_left)
        self.time_left = time_left
        self.increment = increment
        self.moves_left = max(1, moves_left)
        self.base = base
        budget = min(cap, base, time_left * 0.45 + increment * 0.8 + base * 0.1)
        budget = max(0.02, budget)
        now = time.time()
        self.deadline = now + budget
        self.soft_deadline = now + budget * 1.35

    def expired(self, hard: bool = False) -> bool:
        return time.time() >= (self.soft_deadline if hard else self.deadline)

    def remaining(self) -> float:
        return max(0.0, self.soft_deadline - time.time())


@dataclass
class SearchInfo:
    """Snapshot of engine progress (consumed by the GUI and the analyser)."""
    depth: int = 0
    seldepth: int = 0
    score: int = 0
    nodes: int = 0
    time: float = 0.0
    pv: list = field(default_factory=list)
    best_move: object = None
    mate_in: int = 0
    completed: bool = False

    def score_text(self) -> str:
        if self.mate_in:
            side = "White" if self.mate_in > 0 else "Black"
            return "#%d (%s to move mates in %d)" % (
                self.mate_in, side, abs(self.mate_in))
        return "%+.2f" % (self.score / 100.0)


# ==========================================================================
#  SEARCH  -  iterative deepening alpha-beta with the usual pruning tricks
# ==========================================================================
class Searcher:
    """Negamax + alpha-beta with a transposition table.

    Includes quiescence search with delta pruning, null-move pruning,
    late-move reductions, check extensions, killer moves and a history
    heuristic.  All scores are from the point of view of the side to move.
    """

    MAX_PLY = 96

    def __init__(self, evaluator: Evaluator, tt: TranspositionTable,
                 rng: random.Random = None):
        self.evaluator = evaluator
        self.tt = tt
        self.rng = rng or random.Random(0xA5A5)
        self.killers = [(), ()]
        self.history = defaultdict(int)
        self.nodes = 0
        self.time = None
        self.stopped = False
        self.board = None
        self.seldepth = 0

    def stop(self) -> None:
        """Ask the search to abort (used by the GUI's Stop button)."""
        self.stopped = True

    def _check_time(self) -> None:
        if self.stopped:
            raise SearchTimeout()
        if self.nodes % 2048 == 0 and self.time is not None and self.time.expired():
            raise SearchTimeout()

    # -- move ordering -------------------------------------------------------
    def score_moves(self, board: Board, moves: list, tt_move) -> list:
        """Order moves: TT move, promotions, MVV-LVA captures, killers, history."""
        killers = self.killers[board.side]
        scored = []
        for move in moves:
            if tt_move is not None and move == tt_move:
                score = 1 << 28
            elif move[3] == M_PROMO:
                score = (1 << 26) + move[2]
            elif board.is_capture(move):
                victim = board.sq[move[1]] or make_piece(PAWN, opposite(board.side))
                score = (1 << 24) + MVV_LVA[board.sq[move[0]]][victim]
            elif move in killers:
                score = 1 << 23
            else:
                score = self.history[(move, board.side)]
            scored.append((-score, move))
        scored.sort()
        return [move for _, move in scored]

    @staticmethod
    def _has_non_pawn_material(board: Board) -> bool:
        """Null-move is unsafe when we only have pawns left."""
        for piece in board.sq:
            if piece and color_of(piece) == board.side and \
                    (piece & 7) in (KNIGHT, BISHOP, ROOK, QUEEN):
                return True
        return False

    # -- quiescence ----------------------------------------------------------
    def quiesce(self, alpha: int, beta: int, ply: int) -> int:
        """Search only captures/promotions so the evaluation sees a quiet board."""
        self._check_time()
        self.nodes += 1
        if ply > self.seldepth:
            self.seldepth = ply
        board = self.board
        if ply >= self.MAX_PLY - 1:
            return self.evaluator.evaluate(board)
        stand_pat = self.evaluator.evaluate(board)
        if stand_pat >= beta:
            return stand_pat
        if stand_pat > alpha:
            alpha = stand_pat
        if stand_pat + 1000 < alpha:                      # delta pruning
            return stand_pat
        moves = [m for m in board.generate_moves(captures_only=True)
                 if m[3] != M_PROMO or m[2] == QUEEN]
        for move in self.score_moves(board, moves, None):
            victim = board.sq[move[1]] or make_piece(PAWN, opposite(board.side))
            if stand_pat + MG_VALUE[kind_of(victim)] + 200 < alpha and move[3] != M_PROMO:
                continue
            board.make_move(move)
            score = -self.quiesce(-beta, -alpha, ply + 1)
            board.unmake_move()
            if score >= beta:
                return score
            if score > alpha:
                alpha = score
        return alpha

    # -- main search ---------------------------------------------------------
    def negamax(self, depth: int, alpha: int, beta: int, ply: int,
                allow_null: bool = True) -> int:
        self._check_time()
        self.nodes += 1
        board = self.board
        if ply > self.seldepth:
            self.seldepth = ply
        if ply >= self.MAX_PLY - 2:
            return self.evaluator.evaluate(board)

        is_root = ply == 0
        in_check = board.in_check()
        if in_check:
            depth += 1                                   # check extension

        # Draw detection: fifty-move rule, dead position, repetition.
        if not is_root:
            if board.half >= 100 or board.insufficient_material():
                return 0
            if board.rep.get(board.key(), 0) >= 2:
                return 0

        # Transposition table.
        key = board.hash
        tt_move = None
        if not in_check:
            flag, entry = self.tt.probe(key, depth)
            if entry is not None:
                tt_move = entry.move
                if flag is not None:
                    score = entry.score
                    if score > MATE_BOUND:
                        score -= ply
                    elif score < -MATE_BOUND:
                        score += ply
                    if flag == TT_EXACT:
                        return score
                    if flag == TT_LOWER and score >= beta:
                        return score
                    if flag == TT_UPPER and score <= alpha:
                        return score

        if depth <= 0:
            return self.quiesce(alpha, beta, ply)

        static_eval = 0 if in_check else self.evaluator.evaluate(board)

        # Null-move pruning: hand the opponent a free move; if we are still
        # above beta the position is too good to need a full-width search.
        if (allow_null and not is_root and not in_check and depth >= 3
                and static_eval >= beta and self._has_non_pawn_material(board)):
            reduction = 2 + depth // 6
            saved_ep, saved_side = board.ep, board.side
            board.ep = -1
            board.side = opposite(saved_side)
            score = -self.negamax(depth - 1 - reduction, -beta, -beta + 1,
                                  ply + 1, False)
            board.side = saved_side
            board.ep = saved_ep
            if score >= beta and not is_mate_score(score):
                return score

        moves = board.legal_moves()
        if not moves:
            return mate_in(0) if in_check else 0
        if not in_check and len(moves) == 1 and not is_root:
            depth -= 1                                   # forced-move reduction

        ordered = self.score_moves(board, moves, tt_move)
        best_score, best_move = -INFINITY, None
        original_alpha = alpha
        killer = self.killers[board.side]

        for index, move in enumerate(ordered):
            is_capture = board.is_capture(move)
            gives_check = False

            if index == 0:
                score = -self.negamax(depth - 1, -beta, -alpha, ply + 1)
            elif depth >= 4 and not is_capture and not in_check and index >= 4:
                # late move reduction, re-searched whenever it beats alpha
                reduction = 1 if index < 9 else 2
                score = -self.negamax(depth - 1 - reduction,
                                      -alpha - 1, -alpha, ply + 1)
                if score > alpha:
                    score = -self.negamax(depth - 1, -alpha - 1, -alpha, ply + 1)
            else:
                score = -self.negamax(depth - 1, -alpha - 1, -alpha, ply + 1)
                if score > alpha and score < beta:
                    score = -self.negamax(depth - 1, -beta, -alpha, ply + 1)

            board.make_move(move)
            if board.in_check():
                gives_check = True
            board.unmake_move()

            if score > best_score:
                best_score, best_move = score, move
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        if not is_capture and not gives_check:
                            if move not in killer:
                                self.killers[board.side] = (move,) + killer[:1]
                            self.history[(move, board.side)] += depth * depth
                        break

        if not in_check:
            stored = best_score
            if stored > MATE_BOUND:
                stored += ply
            elif stored < -MATE_BOUND:
                stored -= ply
            if best_score <= original_alpha:
                flag = TT_UPPER
            elif best_score >= beta:
                flag = TT_LOWER
            else:
                flag = TT_EXACT
            self.tt.store(key, depth, stored, flag, best_move)
        return best_score

    # -- principal variation -------------------------------------------------
    def extract_pv(self, board: Board, best_move, max_len: int = 14) -> list:
        """Rebuild the PV by following transposition-table best moves."""
        pv = []
        if best_move is None:
            return pv
        pv.append(best_move)
        made = 0
        try:
            while made < max_len - 1:
                board.make_move(best_move)
                made += 1
                entry = self.tt.entries.get(board.hash & TT_MASK)
                nxt = entry.move if entry is not None and entry.key == board.hash else None
                if nxt is None or nxt not in board.legal_moves():
                    break
                pv.append(nxt)
                best_move = nxt
        except (IndexError, ValueError):
            pass
        for _ in range(made):
            board.unmake_move()
        return pv

    # -- driver ---------------------------------------------------------------
    def search(self, board: Board, depth: int, time: TimeManager,
               on_update=None) -> SearchInfo:
        """Iterative deepening; returns the best move found within the budget."""
        self.board = board
        self.time = time
        self.stopped = False
        self.nodes = 0
        self.seldepth = 0
        self.killers = [(), ()]
        self.history.clear()

        info = SearchInfo()
        best_move = None
        best_score = 0
        start = time.time()

        for depth_limit in range(1, max(1, depth) + 1):
            try:
                score, move = self._search_root(board, depth_limit, best_move)
            except SearchTimeout:
                break
            if move is not None:
                best_move, best_score = move, score
                info.depth = depth_limit
                info.seldepth = self.seldepth
                info.score = score
                info.nodes = self.nodes
                info.time = time.time() - start
                info.best_move = move
                info.pv = self.extract_pv(board, move)
                info.mate_in = mate_distance(score)
                if on_update is not None:
                    on_update(info)
            if time.expired() or self.stopped:
                break
            if is_mate_score(best_score):
                break

        if best_move is None:
            legal = board.legal_moves()
            best_move = legal[0] if legal else None
            best_score = 0
        info.best_move = best_move
        info.score = best_score
        info.nodes = self.nodes
        info.time = time.time() - start
        if info.depth == 0:
            info.depth = 1
        info.pv = self.extract_pv(board, best_move)
        info.mate_in = mate_distance(best_score)
        info.completed = True
        return info

    def _search_root(self, board: Board, depth: int, last_move) -> tuple:
        """Root ply using PVS: first move full window, the rest null window."""
        best_move, best_score, tried = None, -INFINITY, None
        ordered = self.score_moves(board, board.legal_moves(), last_move)
        for move in ordered:
            board.make_move(move)
            try:
                if tried is None:
                    score = -self.negamax(depth - 1, -INFINITY, INFINITY, 1)
                else:
                    score = -self.negamax(depth - 1, -INFINITY, -tried, 1)
                    if score > tried and score < INFINITY:
                        score = -self.negamax(depth - 1, -INFINITY, INFINITY, 1)
            except SearchTimeout:
                board.unmake_move()
                raise
            board.unmake_move()
            if score > best_score:
                best_score, best_move = score, move
                tried = score
        return best_score, best_move
