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
import random
import re
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

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
    if len(name) != 2 or name[0] not in FILES or name[1] not in '12345678':
        raise ValueError('Invalid square: %r' % name)
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
ZOBRIST_PIECE = [[_RNG.getrandbits(64) for _ in range(128)] for _ in range(16)]
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
    """Signed moves to mate from the side-to-move's perspective."""
    if is_mate_score(score):
        moves = (MATE - abs(score) + 1) // 2
        return moves if score > 0 else -moves
    return 0


def clamp(value, low, high):
    return low if value < low else (high if value > high else value)


def light_square(square: int) -> bool:
    return (file_of(square) + rank_of(square)) % 2 == 1


class SearchTimeout(Exception):
    """Raised internally when the search exceeds its time budget."""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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
        if len(parts) not in (4, 6):
            raise ValueError('FEN needs four or six fields')
        rows = parts[0].split('/')
        if len(rows) != 8 or parts[1] not in ('w', 'b'):
            raise ValueError('Invalid FEN board or side to move')
        sq = [EMPTY] * 128
        for row_index, row in enumerate(rows):
            rank, file_index = 7 - row_index, 0
            for ch in row:
                if ch in '12345678':
                    file_index += int(ch)
                elif ch in 'PNBRQKpnbrqk' and file_index < 8:
                    kind = {'P': PAWN, 'N': KNIGHT, 'B': BISHOP,
                            'R': ROOK, 'Q': QUEEN, 'K': KING}[ch.upper()]
                    if kind == PAWN and rank in (0, 7):
                        raise ValueError('Unpromoted pawn on back rank')
                    sq[square_of(file_index, rank)] = make_piece(kind, WHITE if ch.isupper() else BLACK)
                    file_index += 1
                else:
                    raise ValueError('Invalid FEN piece placement')
                if file_index > 8:
                    raise ValueError('FEN rank exceeds eight squares')
            if file_index != 8:
                raise ValueError('FEN rank must contain eight squares')
        if any(sq.count(make_piece(KING, color)) != 1 for color in (WHITE, BLACK)):
            raise ValueError('FEN requires exactly one king of each color')
        castling = 0
        if parts[2] != '-':
            if not re.fullmatch(r'K?Q?k?q?', parts[2]):
                raise ValueError('Invalid FEN castling rights')
            for ch in parts[2]:
                castling |= {'K': CR_WK, 'Q': CR_WQ, 'k': CR_BK, 'q': CR_BQ}[ch]
        side = WHITE if parts[1] == 'w' else BLACK
        ep = parse_square(parts[3]) if parts[3] != '-' else -1
        if ep != -1 and (rank_of(ep) != (5 if side == WHITE else 2) or sq[ep]):
            raise ValueError('Invalid FEN en passant target')
        half, full = (int(parts[4]), int(parts[5])) if len(parts) == 6 else (0, 1)
        if half < 0 or full < 1:
            raise ValueError('Invalid FEN move counters')
        self.sq, self.side, self.castling, self.ep = sq, side, castling, ep
        self.half, self.full = half, full
        self.kings = [sq.index(make_piece(KING, WHITE)), sq.index(make_piece(KING, BLACK))]
        if self.in_check(opposite(side)):
            raise ValueError('The side not to move cannot be in check')
        for color, home, kingside, queenside in ((WHITE, 4, CR_WK, CR_WQ), (BLACK, 116, CR_BK, CR_BQ)):
            if castling & (kingside | queenside) and sq[home] != make_piece(KING, color):
                raise ValueError('Castling king is not on its home square')
            for right, square in ((kingside, home + 3), (queenside, home - 4)):
                if castling & right and sq[square] != make_piece(ROOK, color):
                    raise ValueError('Castling rook is not on its home square')
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
        other.rep = defaultdict(int, self.rep)
        other._legal = None
        return other

    def compute_hash(self) -> int:
        h = 0
        for square in range(128):
            if square & 0x88:
                continue
            piece = self.sq[square]
            if piece:
                h ^= ZOBRIST_PIECE[piece][square]
        if self.side == BLACK:
            h ^= ZOBRIST_SIDE
        h ^= ZOBRIST_CASTLE[self.castling]
        ep = self.usable_ep()
        if ep != -1:
            h ^= ZOBRIST_EP[file_of(ep)]
        return h

    def usable_ep(self) -> int:
        """The en-passant square, but only when a capture is really available.

        Emit legal-en-passant FEN (as python-chess does by default). Repetition
        must ignore an ep target when every candidate pawn is pinned.
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
        captured_square = ep - 16 if self.side == WHITE else ep + 16
        captured = self.sq[captured_square]
        if self.sq[ep] or captured != make_piece(PAWN, opposite(self.side)):
            return -1
        for square in (a, b):
            if 0 <= square < 128 and not (square & 0x88) and self.sq[square] == pawn:
                # Test the discovered rook/bishop attack without recursive make_move.
                self.sq[square], self.sq[captured_square], self.sq[ep] = EMPTY, EMPTY, pawn
                try:
                    legal = not self.in_check()
                finally:
                    self.sq[square], self.sq[captured_square], self.sq[ep] = pawn, captured, EMPTY
                if legal:
                    return ep
        return -1

    def key(self):
        """Repetition key (position hash + castling + relevant ep square)."""
        return self.hash

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
        old_usable_ep = self.usable_ep()
        h = old_hash ^ ZOBRIST_PIECE[piece][frm] ^ ZOBRIST_SIDE

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
            h ^= ZOBRIST_PIECE[captured][cap_sq]

        sq[frm] = EMPTY
        if flag == M_EP:
            # Unlike a normal capture, the captured pawn does not stand on
            # the destination square, so it has to be cleared explicitly.
            sq[cap_sq] = EMPTY
        placed = make_piece(promo, side) if flag == M_PROMO else piece
        sq[to] = placed
        h ^= ZOBRIST_PIECE[placed][to]

        if flag == M_CASTLE:
            rook_from, rook_to = (frm + 3, frm + 1) if to > frm else (frm - 4, frm - 1)
            rook = sq[rook_from]
            sq[rook_from] = EMPTY
            sq[rook_to] = rook
            h ^= ZOBRIST_PIECE[rook][rook_from]
            h ^= ZOBRIST_PIECE[rook][rook_to]

        old_castling, old_ep = self.castling, self.ep
        old_half, old_full, old_king = self.half, self.full, self.kings[side]

        new_castling = old_castling & CASTLE_MASK.get(frm, 0xF) & CASTLE_MASK.get(to, 0xF)
        if new_castling != old_castling:
            h ^= ZOBRIST_CASTLE[old_castling] ^ ZOBRIST_CASTLE[new_castling]
        self.castling = new_castling

        if old_usable_ep != -1:
            h ^= ZOBRIST_EP[file_of(old_usable_ep)]
        if flag == M_DPUSH:
            self.ep = (frm + to) >> 1
        else:
            self.ep = -1

        self.half = 0 if (kind == PAWN or captured) else old_half + 1
        self.full = old_full + (1 if side == BLACK else 0)
        if kind == KING:
            self.kings[side] = to
        self.side = opposite(side)
        new_usable_ep = self.usable_ep()
        if new_usable_ep != -1:
            h ^= ZOBRIST_EP[file_of(new_usable_ep)]
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
                    elif (target == ep and victim == EMPTY and color == self.side
                          and sq[target - forward] == make_piece(PAWN, enemy)):
                        moves.append((square, target, 0, M_EP))
            elif kind in (KNIGHT, KING):
                for offset in (KNIGHT_OFFSETS if kind == KNIGHT else KING_OFFSETS):
                    target = square + offset
                    if 0 <= target < 128 and not (target & 0x88):
                        victim = sq[target]
                        if ((victim and color_of(victim) == enemy) or
                                (not victim and not captures_only)):
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
        pieces = minors[WHITE] + minors[BLACK]
        if len(pieces) <= 1:
            return True
        # Any number of bishops on one square color cannot deliver mate.
        # Two knights, mixed bishops or opposing minor pieces can, with help.
        return (all(kind_of(self.sq[s]) == BISHOP for s in pieces)
                and len({light_square(s) for s in pieces}) == 1)

    def outcome(self) -> dict:
        """Classify the position: result string + termination reason."""
        if self.legal_moves():
            if self.insufficient_material():
                return {'result': '1/2-1/2', 'termination': 'insufficient material'}
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
        return self.outcome()['result'] != '*'

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

# PeSTO-style piece-square tables: White's eighth rank first, a8 through h1.
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
            _rank = 7 - rank_of(_sq) if _color == WHITE else rank_of(_sq)
            _rel = _rank * 8 + file_of(_sq)
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
MVV_LVA = [[0] * 16 for _ in range(16)]
for _attacker in range(16):
    for _victim in range(16):
        MVV_LVA[_attacker][_victim] = (
            MG_VALUE.get(_victim & 7, 0) * 16 - MG_VALUE.get(_attacker & 7, 0))



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

            elif kind == ROOK:
                (rooks_b if piece & BLACK_FLAG else rooks_w).append(square)

        # --- pawn structure -------------------------------------------------
        struct = 0
        for square in white_pawns:
            f, r = square & 7, square >> 4
            if not any(abs(file_of(p) - f) <= 1 and rank_of(p) > r for p in black_pawns):
                struct += PASSED_PAWN_BONUS[r]
            isolated = ((f == 0 or not pawn_files_w[f - 1]) and
                        (f == 7 or not pawn_files_w[f + 1]))
            if isolated:
                struct -= ISOLATED_PAWN_PENALTY
        for square in black_pawns:
            f, r = square & 7, square >> 4
            if not any(abs(file_of(p) - f) <= 1 and rank_of(p) < r for p in white_pawns):
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
        mid = (mg_w - mg_b + self.w_piece * piece_score + self.w_king * king_score
               + self.w_struct * struct)
        end = eg_w - eg_b + self.w_piece * piece_score * 0.6 + self.w_struct * struct
        score = (mid * phase + end * eg_phase) // 24
        if board.side == BLACK:
            score = -score
        return int(score + self.w_tempo * TEMPO_BONUS)

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
                if (0 <= shield_rank <= 7 and
                        board.sq[square_of(f, shield_rank)] == make_piece(PAWN, color)):
                    total += KING_SHIELD_BONUS
                if not enemy_files[f]:
                    total -= 3
        return total

    def evaluate_white(self, board: Board) -> int:
        """Score from White's point of view (used by the analyser)."""
        score = self.evaluate(board)
        return score if board.side == WHITE else -score


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
        entry = self.entries.get(key & TT_MASK) if self.enabled else None
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
        budget = max(0.0, min(cap, base, time_left * 0.45 + increment * 0.8))
        now = time.monotonic()
        self.deadline = now + budget
        self.soft_deadline = self.deadline

    def expired(self, hard: bool = False) -> bool:
        return time.monotonic() >= (self.soft_deadline if hard else self.deadline)

    def remaining(self) -> float:
        return max(0.0, self.soft_deadline - time.monotonic())


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
        if is_mate_score(self.score):
            return '#%s%d' % ('-' if self.score < 0 else '', abs(self.mate_in))
        return "%+.2f" % (self.score / 100.0)


# ==========================================================================
#  SEARCH - iterative-deepening principal-variation alpha-beta
# ==========================================================================
class Searcher:
    """Practice-level engine. All scores are from the side-to-move's view.

    A searcher belongs to one worker. Every move, including null moves, is
    unwound in finally blocks so cancellation cannot corrupt the position.
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
        self._null_depth = 0

    def stop(self) -> None:
        self.stopped = True

    def _check_time(self) -> None:
        if self.stopped or (self.nodes % 32 == 0 and self.time is not None and self.time.expired()):
            raise SearchTimeout()

    def _draw(self, board: Board) -> bool:
        return (board.insufficient_material() or
                (not self._null_depth and (board.half >= 100 or board.rep.get(board.key(), 0) >= 3)))

    def _tt_key(self, board: Board) -> int:
        # Repetition and the fifty-move counter are path-dependent. Including
        # their context prevents an exact entry reusing a draw on another path.
        return hash((board.hash, board.half, frozenset(board.rep.items()), bool(self._null_depth)))

    def score_moves(self, board: Board, moves: list, tt_move) -> list:
        killers = self.killers[board.side]
        def priority(move):
            if move == tt_move:
                return 1 << 28
            if move[3] == M_PROMO:
                return (1 << 26) + MG_VALUE[move[2]]
            if board.is_capture(move):
                victim = board.sq[move[1]] or make_piece(PAWN, opposite(board.side))
                return (1 << 24) + MVV_LVA[board.sq[move[0]]][victim]
            if move in killers:
                return 1 << 23
            return self.history.get((move, board.side), 0)
        return sorted(moves, key=priority, reverse=True)

    @staticmethod
    def _has_non_pawn_material(board: Board) -> bool:
        return any(piece and color_of(piece) == board.side and
                   kind_of(piece) in (KNIGHT, BISHOP, ROOK, QUEEN) for piece in board.sq)

    def quiesce(self, alpha: int, beta: int, ply: int) -> int:
        """Legal captures/promotions, or every legal evasion when in check."""
        self._check_time()
        self.nodes += 1
        self.seldepth = max(self.seldepth, ply)
        board = self.board
        in_check = board.in_check()
        legal = board.legal_moves()
        if not legal:
            return -mate_in(ply) if in_check else 0
        if self._draw(board):
            return 0
        if ply >= self.MAX_PLY - 1:
            return self.evaluator.evaluate(board)
        stand_pat = self.evaluator.evaluate(board)
        if not in_check:
            if stand_pat >= beta:
                return stand_pat
            alpha = max(alpha, stand_pat)
        moves = legal if in_check else [m for m in legal if board.is_capture(m) or m[3] == M_PROMO]
        for move in self.score_moves(board, moves, None):
            board.make_move(move)
            try:
                score = -self.quiesce(-beta, -alpha, ply + 1)
            finally:
                board.unmake_move()
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    def negamax(self, depth: int, alpha: int, beta: int, ply: int,
                allow_null: bool = True) -> int:
        self._check_time()
        self.nodes += 1
        self.seldepth = max(self.seldepth, ply)
        board = self.board
        in_check = board.in_check()
        moves = board.legal_moves()
        if not moves:
            return -mate_in(ply) if in_check else 0
        if self._draw(board):
            return 0
        if ply >= self.MAX_PLY - 2:
            return self.evaluator.evaluate(board)
        if in_check:
            depth += 1
        if depth <= 0:
            return self.quiesce(alpha, beta, ply)

        key = self._tt_key(board)
        flag, entry = self.tt.probe(key, depth)
        tt_move = entry.move if entry is not None else None
        if flag is not None:
            score = entry.score
            if score > MATE_BOUND:
                score -= ply
            elif score < -MATE_BOUND:
                score += ply
            if (flag == TT_EXACT or (flag == TT_LOWER and score >= beta)
                    or (flag == TT_UPPER and score <= alpha)):
                return score

        # Null-move pruning, never in check, pawn-only endings or mate windows.
        if (allow_null and not self._null_depth and not in_check and depth >= 3
                and abs(beta) < MATE_BOUND and self._has_non_pawn_material(board)
                and self.evaluator.evaluate(board) >= beta):
            saved = board.ep, board.side, board.hash, board._legal
            board.ep, board.side = -1, opposite(board.side)
            board.hash, board._legal = board.compute_hash(), None
            self._null_depth += 1
            try:
                score = -self.negamax(depth - 3 - depth // 6, -beta, -beta + 1, ply + 1, False)
            finally:
                self._null_depth -= 1
                board.ep, board.side, board.hash, board._legal = saved
            if score >= beta and not is_mate_score(score):
                return score

        ordered = self.score_moves(board, moves, tt_move)
        best_score, best_move = -INFINITY, None
        original_alpha = alpha
        side = board.side

        for index, move in enumerate(ordered):
            quiet = not board.is_capture(move) and move[3] != M_PROMO
            board.make_move(move)
            try:
                gives_check = board.in_check()
                if index == 0:
                    score = -self.negamax(depth - 1, -beta, -alpha, ply + 1)
                else:
                    reduced = depth >= 4 and quiet and not in_check and not gives_check and index >= 4
                    reduction = (1 if index < 9 else 2) if reduced else 0
                    score = -self.negamax(depth - 1 - reduction, -alpha - 1, -alpha, ply + 1)
                    if reduced and score > alpha:
                        score = -self.negamax(depth - 1, -alpha - 1, -alpha, ply + 1)
                    if alpha < score < beta:
                        score = -self.negamax(depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.unmake_move()
            if score > best_score:
                best_score, best_move = score, move
            alpha = max(alpha, score)
            if alpha >= beta:
                if quiet and not gives_check:
                    killers = self.killers[side]
                    if move not in killers:
                        self.killers[side] = (move,) + killers[:1]
                    self.history[(move, side)] += depth * depth
                break

        stored = best_score
        if stored > MATE_BOUND:
            stored += ply
        elif stored < -MATE_BOUND:
            stored -= ply
        flag = TT_UPPER if best_score <= original_alpha else TT_LOWER if best_score >= beta else TT_EXACT
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

# ==========================================================================
#  GAME RECORDS, PGN AND SAFE JSON PERSISTENCE
# ==========================================================================
import tempfile
import uuid
import warnings

_PGN_RESULTS = frozenset(("1-0", "0-1", "1/2-1/2", "*"))
_PGN_TAG_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_UCI_MOVE = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?\Z")


def _record_board(fen: str) -> Board:
    """Validate a standard six-field FEN before giving it to the engine.

    This checks local legality, not whether a position is historically reachable.
    FEN may specify an en-passant target even when no capture is available.
    """
    if not isinstance(fen, str):
        raise ValueError("FEN must be text")
    parts = fen.split()
    if len(parts) != 6:
        raise ValueError("FEN must have six fields")
    rows = parts[0].split("/")
    if len(rows) != 8:
        raise ValueError("FEN must have eight ranks")
    for row in rows:
        width = 0
        previous_digit = False
        for ch in row:
            if ch in "12345678":
                if previous_digit:
                    raise ValueError("FEN contains adjacent empty-square counts")
                width += int(ch)
                previous_digit = True
            elif ch in "PNBRQKpnbrqk":
                width += 1
                previous_digit = False
            else:
                raise ValueError("Invalid FEN piece or empty-square count")
        if width != 8:
            raise ValueError("Each FEN rank must contain eight squares")
    if parts[0].count("K") != 1 or parts[0].count("k") != 1:
        raise ValueError("FEN must contain exactly one king of each color")
    if any(ch in "Pp" for ch in rows[0] + rows[-1]):
        raise ValueError("FEN has an unpromoted pawn on a back rank")
    for pieces in ("PNBRQK", "pnbrqk"):
        if sum(parts[0].count(ch) for ch in pieces) > 16 or parts[0].count(pieces[0]) > 8:
            raise ValueError("FEN has too many pieces or pawns")
    if parts[1] not in ("w", "b"):
        raise ValueError("FEN side must be w or b")
    rights = parts[2]
    if rights != "-" and (not rights or any(ch not in "KQkq" for ch in rights)
                            or len(set(rights)) != len(rights)):
        raise ValueError("Invalid FEN castling rights")
    if parts[3] != "-" and not re.fullmatch(r"[a-h][36]", parts[3]):
        raise ValueError("Invalid FEN en-passant square")
    if not re.fullmatch(r"[0-9]+", parts[4]) or not re.fullmatch(r"[0-9]+", parts[5]):
        raise ValueError("FEN counters must be nonnegative integers")
    if int(parts[5]) < 1:
        raise ValueError("FEN move number must be at least one")
    try:
        board = Board(fen)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("Invalid FEN: %s" % exc) from exc
    for right, color, king, rook in (("K", WHITE, 4, 7), ("Q", WHITE, 4, 0),
                                      ("k", BLACK, 116, 119), ("q", BLACK, 116, 112)):
        if right in rights and (board.sq[king] != make_piece(KING, color)
                               or board.sq[rook] != make_piece(ROOK, color)):
            raise ValueError("FEN castling right has no home king/rook")
    if parts[3] != "-":
        ep = parse_square(parts[3])
        forward = 16 if board.side == WHITE else -16
        if (rank_of(ep) != (5 if board.side == WHITE else 2)
                or board.sq[ep] or board.sq[ep + forward]
                or board.sq[ep - forward] != make_piece(PAWN, opposite(board.side))
                or board.half != 0):
            raise ValueError("FEN en-passant target is inconsistent with a double pawn move")
    if board.in_check(opposite(board.side)):
        raise ValueError("FEN leaves the side that just moved in check")
    return board


def _record_text(value, name):
    if not isinstance(value, str) or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("%s must be text without control characters" % name)
    return value


@dataclass
class GameRecord:
    start_fen: str = START_FEN
    moves: list[str] = field(default_factory=list)
    headers: dict = field(default_factory=dict)
    result: str = "*"
    termination: str = "*"

    def replay(self) -> Board:
        """Return a fresh board after all legal UCI moves, or raise ValueError."""
        board = _record_start(self)
        for ply, text in enumerate(self.moves, 1):
            board.make_move(_record_move(board, text, ply))
        return board


def _record_start(record: GameRecord) -> Board:
    if not isinstance(record, GameRecord):
        raise ValueError("Expected a GameRecord")
    if not isinstance(record.moves, list):
        raise ValueError("Record moves must be a list of UCI strings")
    if not isinstance(record.result, str) or record.result not in _PGN_RESULTS:
        raise ValueError("Invalid game result")
    _record_text(record.termination, "Termination")
    if not isinstance(record.headers, dict):
        raise ValueError("Record headers must be a dictionary")
    for key, value in record.headers.items():
        if not isinstance(key, str) or not _PGN_TAG_NAME.fullmatch(key):
            raise ValueError("Invalid PGN tag name")
        _record_text(value, "PGN header " + key)
    return _record_board(record.start_fen)


def _record_move(board: Board, text: str, ply: int):
    if not isinstance(text, str) or not _UCI_MOVE.fullmatch(text):
        raise ValueError("Invalid UCI move at ply %d: %r" % (ply, text))
    for move in board.legal_moves():
        if board.uci(move) == text:
            return move
    raise ValueError("Illegal move at ply %d: %s" % (ply, text))


def _pgn_tokens(text):
    """Strict lexer: balanced RAVs are skipped, never truncated at bad input."""
    index, depth = 0, 0
    length = len(text)
    tag = re.compile(r'\[\s*([A-Za-z][A-Za-z0-9_]*)\s+"((?:\\["\\]|[^"\\\r\n])*)"\s*\]')
    while index < length:
        ch = text[index]
        if ch.isspace():
            index += 1
            continue
        if ch == "%" and (index == 0 or text[index - 1] in "\r\n"):
            end = text.find("\n", index)
            index = length if end < 0 else end + 1
            continue
        if ch == ";":
            end = text.find("\n", index)
            index = length if end < 0 else end + 1
            continue
        if ch == "{":
            end = text.find("}", index + 1)
            if end < 0 or "{" in text[index + 1:end]:
                raise ValueError("Unclosed or nested PGN brace comment")
            index = end + 1
            continue
        if ch == "}":
            raise ValueError("Unexpected closing PGN comment brace")
        if ch == "(":
            if not depth:
                yield "variation", "("
            depth += 1
            index += 1
            continue
        if ch == ")":
            if not depth:
                raise ValueError("Unexpected closing PGN variation")
            depth -= 1
            index += 1
            continue
        if ch in "[]":
            if depth:
                raise ValueError("PGN headers cannot occur inside variations")
            match = tag.match(text, index)
            if not match:
                raise ValueError("Malformed PGN tag at character %d" % index)
            value = re.sub(r'\\(["\\])', r'\1', match.group(2))
            yield "tag", (match.group(1), value)
            index = match.end()
            continue
        if depth:
            index += 1
            continue
        match = re.match(r"([0-9]+)(\.\.\.|\.)", text[index:])
        if match:
            yield "number", (int(match.group(1)), len(match.group(2)))
            index += match.end()
            continue
        if ch == "$":
            match = re.match(r"\$([0-9]+)", text[index:])
            if not match or int(match.group(1)) > 255:
                raise ValueError("Invalid PGN numeric annotation glyph")
            yield "nag", int(match.group(1))
            index += match.end()
            continue
        end = index
        while end < length and not text[end].isspace() and text[end] not in "{}();[]$":
            end += 1
        if end == index:
            raise ValueError("Unrecognized PGN input at character %d" % index)
        yield "symbol", text[index:end]
        index = end
    if depth:
        raise ValueError("Unclosed PGN variation")


def _pgn_san_move(board, token):
    token = re.sub(r"(?:!!|\?\?|!\?|\?!|!|\?)$", "", token)
    if token.startswith("0-0"):
        token = token.replace("0", "O")
    if token.endswith("++"):
        token = token[:-1]
    pattern = r"(?:O-O(?:-O)?|[KQRBN](?:[a-h][1-8]|[a-h]|[1-8])?x?[a-h][1-8]|[a-h](?:x[a-h])?[1-8](?:=[QRBN])?)[+#]?"
    if not re.fullmatch(pattern, token):
        raise ValueError("Unrecognized SAN token: %r" % token)
    candidates = []
    for move in board.legal_moves():
        san = board.san(move)
        # Missing check suffixes are a common import convention. An explicit
        # but incorrect check/mate suffix is never accepted.
        if san == token or (not token.endswith(("+", "#")) and san.rstrip("+#") == token):
            candidates.append(move)
    if len(candidates) != 1:
        raise ValueError("Illegal or ambiguous SAN move: %s" % token)
    return candidates[0]


def parse_pgn(text: str) -> GameRecord:
    """Parse one standard-chess PGN game; a movetext result is mandatory.

    Comments, NAGs and balanced nested variations are ignored. Legal mainline
    SAN, move numbers, tags, FEN and result agreement are checked. Multiple
    games, unsupported variants, garbage and unfinished syntax raise ValueError.
    """
    if not isinstance(text, str):
        raise ValueError("PGN must be text")
    text = text.lstrip("\ufeff")
    headers, moves = {}, []
    board = None
    pending_number, finished = False, False
    result, start_fen = "*", START_FEN
    for kind, value in _pgn_tokens(text):
        if finished:
            raise ValueError("Unexpected input after PGN result (only one game is supported)")
        if kind == "tag":
            if board is not None:
                raise ValueError("PGN tags must precede movetext")
            key, val = value
            if key in headers:
                raise ValueError("Duplicate PGN tag: " + key)
            headers[key] = _record_text(val, "PGN header " + key)
            continue
        if board is None:
            if headers.get("Variant", "Standard").lower() not in ("standard", "chess"):
                raise ValueError("Only standard chess PGN is supported")
            setup = headers.get("SetUp")
            if setup not in (None, "0", "1"):
                raise ValueError("PGN SetUp must be 0 or 1")
            if setup == "1" and "FEN" not in headers:
                raise ValueError("PGN SetUp 1 requires a FEN tag")
            if setup == "0" and "FEN" in headers:
                raise ValueError("PGN FEN conflicts with SetUp 0")
            if "Result" in headers and headers["Result"] not in _PGN_RESULTS:
                raise ValueError("Invalid PGN Result tag")
            start_fen = headers.get("FEN", START_FEN)
            board = _record_board(start_fen)
        if kind in ("variation", "nag") or (kind == "symbol" and value in ("!", "?", "!!", "??", "!?", "?!")):
            if not moves or pending_number:
                raise ValueError("PGN annotation must follow a move")
            continue
        if kind == "number":
            number, dots = value
            if pending_number or number != board.full or dots != (1 if board.side == WHITE else 3):
                raise ValueError("Incorrect PGN move number or side")
            pending_number = True
            continue
        if value in _PGN_RESULTS:
            if pending_number:
                raise ValueError("PGN ends after an unplayed move number")
            result, finished = value, True
            continue
        try:
            move = _pgn_san_move(board, value)
        except ValueError as exc:
            raise ValueError("PGN ply %d: %s" % (len(moves) + 1, exc)) from exc
        moves.append(board.uci(move))
        board.make_move(move)
        pending_number = False
    if not finished:
        raise ValueError("PGN is missing its movetext result marker")
    if "Result" in headers and headers["Result"] != result:
        raise ValueError("PGN header and movetext results disagree")
    if result != "*" and not board.legal_moves():
        forced = "1-0" if board.side == BLACK else "0-1"
        if not board.in_check():
            forced = "1/2-1/2"
        if result != forced:
            raise ValueError("PGN result contradicts the final checkmate/stalemate position")
    return GameRecord(start_fen, moves, headers, result, headers.get("Termination", "*"))


def export_pgn(record: GameRecord, report: dict | None = None) -> str:
    """Export legal SAN with escaped tags and optional, safely quoted comments."""
    board = _record_start(record)
    headers = {"Event": "Chess Arena", "Site": "?", "Date": "????.??.??", "Round": "?",
               "White": "White", "Black": "Black", "Result": record.result}
    headers.update(record.headers)
    headers["Result"] = record.result
    if record.start_fen != START_FEN:
        headers.update({"SetUp": "1", "FEN": record.start_fen})
    else:
        headers.pop("SetUp", None)
        headers.pop("FEN", None)
    if record.termination != "*":
        headers["Termination"] = record.termination
    else:
        headers.pop("Termination", None)
    lines = []
    for key, value in headers.items():
        value = _record_text(value, "PGN header " + key).replace("\\", "\\\\").replace('"', '\\"')
        lines.append('[%s "%s"]' % (key, value))
    annotations = {}
    if isinstance(report, dict):
        for row in report.get("moves", []):
            if isinstance(row, dict) and isinstance(row.get("ply"), int):
                annotations[row["ply"]] = row
    tokens = []
    for ply, uci in enumerate(record.moves, 1):
        move = _record_move(board, uci, ply)
        if board.side == WHITE:
            tokens.append("%d." % board.full)
        elif ply == 1:
            tokens.append("%d..." % board.full)
        tokens.append(board.san(move))
        board.make_move(move)
        row = annotations.get(ply)
        if row:
            parts = [str(row[key]) for key in ("grade", "hint") if row.get(key)]
            if row.get("loss_cp") is not None:
                parts.append("estimated loss %s cp" % row["loss_cp"])
            if row.get("best"):
                parts.append("engine choice " + str(row["best"]))
            comment = "; ".join(parts).replace("{", "(").replace("}", ")")
            comment = " ".join(comment.split())
            if comment:
                tokens.append("{ " + comment + " }")
    tokens.append(record.result)
    # Wrap between tokens, not inside tags/SAN or brace comments.
    body, current = [], ""
    for token in tokens:
        if current and len(current) + len(token) + 1 > 88:
            body.append(current)
            current = ""
        current = (current + " " + token).strip()
    if current:
        body.append(current)
    return "\n".join(lines) + "\n\n" + "\n".join(body) + "\n"


def _json_check(value):
    """Reject non-JSON types, non-string keys and NaN/Infinity before saving."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _json_check(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_check(item)
        return
    raise ValueError("Persistence accepts only finite JSON values with string dictionary keys")


class Store:
    """Atomic JSON profile/archive plus a small result-weighted opening book.

    Bad files are preserved, skipped/defaulted and reported both through
    ``warnings`` and RuntimeWarning. Writes raise OSError when unsuccessful.
    One instance is thread-safe; simultaneous independent processes are not
    coordinated when updating the derived opening statistics.
    """

    BOOK_PLIES = 20
    BOOK_POSITIONS = 10000
    MAX_JSON_BYTES = 8 * 1024 * 1024

    def __init__(self, data_dir=None):
        self.data_dir = os.path.abspath(os.path.expanduser(os.fspath(data_dir) if data_dir is not None
                                                         else "~/.chess_arena"))
        self.archive_dir = os.path.join(self.data_dir, "games")
        os.makedirs(self.archive_dir, mode=0o700, exist_ok=True)
        self.warnings = []
        self._lock = threading.RLock()

    def _warn(self, message):
        self.warnings.append(message)
        warnings.warn(message, RuntimeWarning, stacklevel=3)

    def _read_json(self, path, default, validator):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read(self.MAX_JSON_BYTES + 1)
            if len(text.encode("utf-8")) > self.MAX_JSON_BYTES:
                raise ValueError("JSON file exceeds size limit")
            def pairs(items):
                result = {}
                for key, val in items:
                    if key in result:
                        raise ValueError("Duplicate JSON key: " + key)
                    result[key] = val
                return result
            value = json.loads(text, object_pairs_hook=pairs)
            _json_check(value)
            validator(value)
            return value
        except FileNotFoundError:
            return default
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
            self._warn("Cannot load %s: %s; file preserved, using default/skipping" % (path, exc))
            return default

    def _write_json(self, path, value):
        _json_check(value)
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        if len(text.encode("utf-8")) > self.MAX_JSON_BYTES:
            raise ValueError("JSON data exceeds size limit")
        descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=os.path.dirname(path))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _profile_ok(profile):
        if not isinstance(profile, dict):
            raise ValueError("Profile must be a JSON object")

    def load_profile(self) -> dict:
        with self._lock:
            return self._read_json(os.path.join(self.data_dir, "profile.json"),
                                   {"version": 1, "games_played": 0, "settings": {}}, self._profile_ok)

    def save_profile(self, profile: dict):
        self._profile_ok(profile)
        with self._lock:
            self._write_json(os.path.join(self.data_dir, "profile.json"), profile)

    @staticmethod
    def _entry_ok(entry):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not re.fullmatch(r"[0-9a-f]{32}", entry["id"]):
            raise ValueError("Invalid archive identifier")
        required = ("start_fen", "moves", "headers", "result", "termination", "created_utc")
        if any(key not in entry for key in required):
            raise ValueError("Archive entry is missing record fields")
        _record_text(entry["created_utc"], "Archive timestamp")
        GameRecord(entry["start_fen"], entry["moves"], entry["headers"],
                   entry["result"], entry["termination"]).replay()

    def archive(self, record: GameRecord) -> str:
        record.replay()
        identifier = uuid.uuid4().hex
        entry = {"id": identifier, "created_utc": utc_stamp(), "start_fen": record.start_fen,
                 "moves": list(record.moves), "headers": dict(record.headers),
                 "result": record.result, "termination": record.termination}
        with self._lock:
            # Load before adding the archive: a rebuild must not count it twice.
            book = self.opening_stats()
            self._write_json(os.path.join(self.archive_dir, identifier + ".json"), entry)
            self._learn(book, record)
            try:
                self._write_json(os.path.join(self.data_dir, "openings.json"), book)
            except (OSError, ValueError) as exc:
                self._warn("Game %s was archived, but opening statistics could not be saved: %s" % (identifier, exc))
        return identifier

    def history(self) -> list[dict]:
        with self._lock:
            entries = []
            for filename in sorted(os.listdir(self.archive_dir)):
                if not filename.endswith(".json") or filename.startswith(".tmp-"):
                    continue
                path = os.path.join(self.archive_dir, filename)
                entry = self._read_json(path, None, self._entry_ok)
                if entry is not None:
                    if filename != entry["id"] + ".json":
                        self._warn("Archive filename/identifier mismatch: " + path)
                    else:
                        entries.append(entry)
            return sorted(entries, key=lambda row: (row["created_utc"], row["id"]), reverse=True)

    @staticmethod
    def _book_ok(book):
        if not isinstance(book, dict) or book.get("version") != 1 or not isinstance(book.get("positions"), dict):
            raise ValueError("Invalid opening book schema")
        if type(book.get("games")) is not int or book["games"] < 0:
            raise ValueError("Invalid opening game count")
        if len(book["positions"]) > Store.BOOK_POSITIONS:
            raise ValueError("Opening book has too many positions")
        for position, choices in book["positions"].items():
            if not isinstance(position, str) or not isinstance(choices, dict):
                raise ValueError("Invalid opening book position")
            for uci, stats in choices.items():
                if not _UCI_MOVE.fullmatch(uci) or not isinstance(stats, dict):
                    raise ValueError("Invalid opening move")
                for field_name in ("wins", "draws", "losses", "unfinished"):
                    if type(stats.get(field_name)) is not int or stats[field_name] < 0:
                        raise ValueError("Invalid opening result counts")

    @staticmethod
    def _book_key(board):
        return " ".join(board.fen().split()[:4])

    def _learn(self, book, record):
        board = _record_board(record.start_fen)
        for ply, text in enumerate(record.moves[:self.BOOK_PLIES], 1):
            key = self._book_key(board)
            move = _record_move(board, text, ply)
            if key in book["positions"] or len(book["positions"]) < self.BOOK_POSITIONS:
                stats = book["positions"].setdefault(key, {}).setdefault(text,
                            {"wins": 0, "draws": 0, "losses": 0, "unfinished": 0})
                if record.result == "*":
                    label = "unfinished"
                elif record.result == "1/2-1/2":
                    label = "draws"
                else:
                    winner = WHITE if record.result == "1-0" else BLACK
                    label = "wins" if board.side == winner else "losses"
                stats[label] += 1
            board.make_move(move)
        book["games"] += 1

    def opening_stats(self) -> dict:
        """Return JSON data; recover a missing/corrupt derived book from archives."""
        with self._lock:
            path = os.path.join(self.data_dir, "openings.json")
            book = self._read_json(path, None, self._book_ok)
            if book is not None:
                return book
            book = {"version": 1, "games": 0, "positions": {}}
            for entry in self.history():
                self._learn(book, GameRecord(entry["start_fen"], entry["moves"], entry["headers"],
                                            entry["result"], entry["termination"]))
            return book

    def choose_book_move(self, board: Board):
        """Choose a legal learned move using smoothed, result-weighted counts.

        No built-in repertoire or claim of optimality: only completed archived
        games contribute evidence. Sparse data is deliberately smoothed.
        """
        choices = self.opening_stats()["positions"].get(self._book_key(board), {})
        candidates = []
        for move in board.legal_moves():
            uci = board.uci(move)
            stats = choices.get(uci)
            if not stats:
                continue
            finished = stats["wins"] + stats["draws"] + stats["losses"]
            if finished:
                score = (stats["wins"] + 0.5 * stats["draws"] + 1) / (finished + 2)
                candidates.append((score, finished, uci, move))
        return max(candidates)[-1] if candidates else None

# ==========================================================================
#  BOUNDED POST-GAME ANALYSIS (HEURISTIC, NOT A CALIBRATED RATING MODEL)
# ==========================================================================
def _analysis_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise SearchTimeout("Game analysis cancelled")


class _AnalysisSearcher(Searcher):
    """Check cancellation at search nodes, without a monitoring thread."""

    def __init__(self, cancel):
        super().__init__(Evaluator("balanced"), TranspositionTable())
        self._analysis_event = cancel

    def _check_time(self):
        _analysis_cancel(self._analysis_event)
        super()._check_time()


def _analysis_search(searcher, board, depth, seconds, cancel):
    _analysis_cancel(cancel)
    legal = board.legal_moves()
    if not legal:
        return {"score": -MATE if board.in_check() else 0, "depth": 0,
                "best_move": None, "nodes": 0, "exact": True}
    if board.insufficient_material() or board.half >= 100 or board.rep.get(board.key(), 0) >= 3:
        return {"score": 0, "depth": 0, "best_move": legal[0], "nodes": 0, "exact": True}
    # Never let a timed-out/cancelled search mutate the replay board. The
    # engine's scores are side-to-move scores, including at Black positions.
    snapshot = board.clone()
    manager = TimeManager(max(3600.0, seconds * 100), 0, 30, seconds, seconds)
    info = searcher.search(snapshot, depth, manager)
    # Searcher normally catches its own timeouts; cancellation must propagate.
    _analysis_cancel(cancel)
    best = info.best_move if info.best_move in legal else None
    return {"score": int(info.score), "depth": int(info.depth), "best_move": best,
            "nodes": int(info.nodes), "exact": False}


def _analysis_phase(board):
    material_phase = sum(PHASE_WEIGHT[kind_of(piece)] for square, piece in enumerate(board.sq)
                         if not square & 0x88 and piece)
    if material_phase <= 8:
        return "endgame"
    if board.full <= 10 and material_phase >= 20:
        return "opening"
    return "middlegame"


def _analysis_grade(loss, played_best, before, after, reliable):
    if not reliable:
        return "unrated"
    if played_best:
        return "best"
    # A non-mating continuation under shallow search is not proof that a
    # longer mate no longer exists, so explicitly qualify missed-mate labels.
    if before > MATE_BOUND and after <= MATE_BOUND:
        return "possible missed mate"
    if after < -MATE_BOUND and before >= -MATE_BOUND:
        return "allows mate"
    if loss is None:
        return "mate line"
    if loss <= 20:
        return "excellent"
    if loss <= 60:
        return "good"
    if loss <= 120:
        return "inaccuracy"
    if loss <= 250:
        return "mistake"
    return "blunder"


def _analysis_hint(grade, best, phase, in_check):
    if grade == "unrated":
        return "No completed search at this budget; increase analysis time before judging this move."
    if grade == "possible missed mate":
        return ("The engine found a mating line with %s, but not after the played move. "
                "This is a search-limited warning, not proof that every longer mate was lost." % best)
    if grade == "allows mate":
        return "The searched continuation permits forced mate; compare the defensive alternative %s." % best
    if grade == "mate line":
        return "A mating score is not a centipawn value; compare the forcing lines rather than material."
    if grade == "best":
        return "Matches the engine's choice at this search budget; deeper analysis may choose differently."
    if grade in ("excellent", "good"):
        return "Close to the engine's estimate; compare %s to understand the alternative plan." % best
    if in_check:
        return "Compare all legal check evasions, starting with %s, before committing to a defense." % best
    if phase == "opening":
        return "Compare %s; review development, central control and king safety before moving again." % best
    if phase == "endgame":
        return "Compare %s; count pawn races and check king activity before exchanging material." % best
    return "Compare %s and check the opponent's checks, captures and threats." % best


def _analysis_totals(rows):
    losses = [row["loss_cp"] for row in rows if row["loss_cp"] is not None]
    grades = {}
    for row in rows:
        grades[row["grade"]] = grades.get(row["grade"], 0) + 1
    return {"plies": len(rows), "cp_scored_plies": len(losses),
            "mean_loss_cp": round(sum(losses) / len(losses), 1) if losses else None,
            "max_loss_cp": max(losses) if losses else None, "grades": grades}


def analyze_game(record: GameRecord, seconds=0.1, depth=3, cancel=None,
                 on_progress=None) -> dict:
    """Return a JSON-serializable, shallow-engine coaching report.

    ``seconds`` is the per-search budget (the engine may impose a minimum).
    Each ply uses at most two searches: best play before the move, and the
    opponent's best reply afterwards, normally at one less nominal depth.
    Scores after the move are negated back to the mover's perspective before
    computing max(0, best_score - played_score). If the played move is the
    engine choice, its loss is zero by definition. Mate scores are NOT treated
    as enormous centipawn losses. Budget/depth differences can make estimates
    noisy, especially when only one iteration completes.

    A threading.Event cancellation raises SearchTimeout; progress receives
    (completed_plies, total_plies), including an initial (0, total) call.
    Neither an externally calibrated accuracy percentage nor Elo is inferred.
    """
    _analysis_cancel(cancel)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Analysis seconds must be finite and positive")
    if type(depth) is not int or not 1 <= depth <= 64:
        raise ValueError("Analysis depth must be an integer from 1 to 64")
    # Validate the complete mainline before doing expensive analysis. Check
    # cancellation during validation too, including long imported games.
    validator = _record_start(record)
    for ply, text in enumerate(record.moves, 1):
        _analysis_cancel(cancel)
        validator.make_move(_record_move(validator, text, ply))
    board = _record_start(record)
    searcher = _AnalysisSearcher(cancel)
    total, rows = len(record.moves), []
    started = time.monotonic()
    if on_progress is not None:
        on_progress(0, total)
    _analysis_cancel(cancel)
    for ply, uci in enumerate(record.moves, 1):
        _analysis_cancel(cancel)
        move = _record_move(board, uci, ply)
        san, color, fullmove = board.san(move), board.side, board.full
        phase, checked = _analysis_phase(board), board.in_check()
        # History-dependent draw evaluations must not leak across root calls.
        searcher.tt.clear()
        before = _analysis_search(searcher, board, depth, seconds, cancel)
        best_move = before["best_move"]
        best = board.san(best_move) if best_move is not None else "(none)"
        best_uci = board.uci(best_move) if best_move is not None else None
        board.make_move(move)
        # Clearing also prevents a deeper entry from giving a misleadingly
        # optimistic completed-depth label on the shallower played position.
        searcher.tt.clear()
        reply_depth = max(1, min(depth, before["depth"] or depth) - 1)
        after = _analysis_search(searcher, board, reply_depth, seconds, cancel)
        best_score = before["score"]
        played_score = -after["score"]
        played_best = move == best_move
        reliable = ((before["depth"] > 0 or before["exact"])
                    and (after["depth"] > 0 or after["exact"]))
        mate_before = is_mate_score(best_score)
        mate_after = is_mate_score(played_score)
        if not reliable:
            loss = None
        elif played_best:
            loss = 0
        elif mate_before or mate_after:
            loss = None
        else:
            loss = max(0, int(best_score - played_score))
        grade = _analysis_grade(loss, played_best, best_score, played_score, reliable)
        white_sign = 1 if color == WHITE else -1
        rows.append({
            "ply": ply, "fullmove": fullmove, "color": "white" if color == WHITE else "black",
            "uci": uci, "san": san, "best": best, "best_uci": best_uci,
            "loss_cp": loss, "grade": grade,
            "hint": _analysis_hint(grade, best, phase, checked), "phase": phase,
            "score_before_cp": None if mate_before else best_score,
            "score_after_cp": None if mate_after else played_score,
            "score_before_white_cp": None if mate_before else white_sign * best_score,
            "score_after_white_cp": None if mate_after else white_sign * played_score,
            "mate_before": mate_before, "mate_after": mate_after,
            "possible_missed_mate": grade == "possible missed mate",
            "depth_before": before["depth"], "depth_after": after["depth"],
            "nodes": before["nodes"] + after["nodes"],
            "horizon_warning": (not played_best and not before["exact"] and not after["exact"]
                                and before["depth"] != after["depth"] + 1),
        })
        if on_progress is not None:
            on_progress(ply, total)
        _analysis_cancel(cancel)
    summary = _analysis_totals(rows)
    summary["by_color"] = {color: _analysis_totals([row for row in rows if row["color"] == color])
                           for color in ("white", "black")}
    summary["phases"] = {phase: _analysis_totals([row for row in rows if row["phase"] == phase])
                         for phase in ("opening", "middlegame", "endgame")}
    summary["note"] = ("Heuristic centipawn-loss estimates from a small, time-limited engine; "
                       "not calibrated accuracy or Elo. Mate transitions without a finite "
                       "centipawn loss are excluded from averages. Claimable draws follow "
                       "the engine's automatic draw policy.")
    return {"version": 1, "start_fen": record.start_fen, "result": record.result,
            "termination": record.termination, "headers": dict(record.headers),
            "requested_depth": depth, "seconds_per_search": float(seconds),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "score_perspective": "score_before_cp and score_after_cp favor the player making that move; *_white_cp favors White",
            "moves": rows, "summary": summary}

# ==========================================================================
#  TK INTERFACE - Tk is deliberately imported only when a GUI is requested.
# ==========================================================================
class _GUIBudget(TimeManager):
    """The cancellation event also covers stop-before-search-start races."""

    def __init__(self, seconds, cancel):
        super().__init__(3600.0, 0.0, 30, seconds, seconds)
        self.cancel = cancel

    def expired(self, hard=False):
        return self.cancel.is_set() or super().expired(hard)


class ChessApp:
    """Tk application. Construct on the Tk thread as ChessApp(root, store).

    All widgets, variables and the live board belong exclusively to that
    thread. Workers receive detached records/boards and communicate through a
    queue. Undo rewinds one ply and pauses; imported games open paused without
    clocks. Strength names describe search budgets, not calibrated Elo ratings.
    """

    MODES = ("Human vs AI", "AI vs AI", "Human vs Human")
    STRENGTHS = {"Quick": (1, 0.06), "Casual": (2, 0.20),
                 "Club": (3, 0.65), "Strong": (5, 2.0)}
    CLOCKS = {"No clock": (0, 0), "1 + 0": (60, 0),
              "3 + 2": (180, 2), "5 + 0": (300, 0),
              "10 + 5": (600, 5), "15 + 10": (900, 10)}
    GLYPHS = {PAWN: "\u265f", KNIGHT: "\u265e", BISHOP: "\u265d",
              ROOK: "\u265c", QUEEN: "\u265b", KING: "\u265a"}

    def __init__(self, root, store):
        import queue
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox

        self.root, self.store = root, store
        self.tk, self.ttk = tk, ttk
        self.filedialog, self.messagebox = filedialog, messagebox
        self._events = queue.Queue()
        self._queue_empty = queue.Empty
        self._generation = 0
        self._worker = None
        self._searcher = None
        self._cancel = threading.Event()
        self._job = None
        self._pending_analysis = None
        self._after_id = None
        self._closed = False
        self._promotion_window = None
        self._selected = None
        self._drag_from = None
        self._press_consumed = False
        self._archived_signature = None
        self._archives = {}
        self.report = None
        self.paused = False
        self.flipped = False
        self.board = Board()
        self.record = GameRecord()
        self._sans = []
        self._clock_history = []
        self._clocks = [0.0, 0.0]
        self._clock_enabled = False
        self._increment = 0
        self._last_tick = time.monotonic()
        try:
            profile = store.load_profile()
            self._profile = profile if isinstance(profile, dict) else {}
        except Exception as exc:
            self._profile = {}
            print("Chess Arena: profile could not be loaded: %s" % exc, file=sys.stderr)
        settings = self._profile.get("gui", {})
        if not isinstance(settings, dict):
            settings = {}
        self.styles = tuple(globals().get("STYLE_WEIGHTS", globals().get(
            "STYLES", {"balanced": ()})))

        def choice(key, options, default):
            value = settings.get(key, default)
            return tk.StringVar(root, value=value if value in options else default)

        self.mode_var = choice("mode", self.MODES, self.MODES[0])
        self.human_color_var = choice("human_color", ("White", "Black"), "White")
        self.style_var = choice("white_style", self.styles, "balanced")
        self.black_style_var = choice("black_style", self.styles, "balanced")
        self.strength_var = choice("strength", self.STRENGTHS, "Casual")
        self.time_control_var = choice("clock", self.CLOCKS, "No clock")
        self.status_var = tk.StringVar(root, value="Ready")
        self.engine_var = tk.StringVar(root, value="Engine idle")
        self.eval_var = tk.StringVar(root, value="White +0.00 (static)")
        self.clock_vars = [tk.StringVar(root), tk.StringVar(root)]
        self.pause_var = tk.StringVar(root, value="Pause")
        self.flipped = bool(settings.get("flipped", False))
        self._build_ui()
        self.new_game()
        self.refresh_history()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._after_id = self.root.after(40, self._pump)

    def _build_ui(self):
        tk, ttk, root = self.tk, self.ttk, self.root
        root.title("Chess Arena")
        root.geometry("1120x780")
        root.minsize(840, 610)
        outer = ttk.Frame(root, padding=8)
        outer.pack(fill="both", expand=True)
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(0, 6))
        for text, command in (("New / Reset", lambda: self.new_game(confirm=True)),
                              ("Undo ply", self.undo),
                              ("Flip board", self.flip_board),
                              ("Open PGN", self.open_pgn),
                              ("Save PGN", self.save_pgn),
                              ("Archive", self.archive_game)):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=2)
        ttk.Button(bar, textvariable=self.pause_var,
                   command=self.toggle_pause).pack(side="left", padx=2)

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 5))
        self._combo(controls, "Mode", self.mode_var, self.MODES, 17, self._mode_changed)
        self._combo(controls, "Human", self.human_color_var,
                    ("White", "Black"), 7, self._mode_changed)
        self._combo(controls, "Strength", self.strength_var,
                    tuple(self.STRENGTHS), 9, self._engine_settings_changed)
        self._combo(controls, "Clock (new game)", self.time_control_var,
                    tuple(self.CLOCKS), 10)
        styles = ttk.Frame(outer)
        styles.pack(fill="x", pady=(0, 7))
        self._combo(styles, "White AI style", self.style_var,
                    self.styles, 12, self._engine_settings_changed)
        self._combo(styles, "Black AI style", self.black_style_var,
                    self.styles, 12, self._engine_settings_changed)
        ttk.Label(styles, text="Strength is a search budget, not an Elo rating.").pack(
            side="left", padx=12)

        body = ttk.Panedwindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True)
        left, right = ttk.Frame(body), ttk.Frame(body, width=390)
        body.add(left, weight=3)
        body.add(right, weight=2)
        clocks = ttk.Frame(left)
        clocks.pack(fill="x")
        for color in (WHITE, BLACK):
            ttk.Label(clocks, textvariable=self.clock_vars[color],
                      font=("TkDefaultFont", 14, "bold")).pack(
                          side="left" if color == WHITE else "right", padx=10, pady=5)
        self.canvas = tk.Canvas(left, width=540, height=540, background="#23313c",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw_board())
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        ttk.Label(left, text="Click two squares or drag a piece. Dots mark legal moves.").pack(
            pady=(6, 2))
        ttk.Label(left, textvariable=self.eval_var).pack()
        self.eval_bar = ttk.Progressbar(left, maximum=100, value=50)
        self.eval_bar.pack(fill="x", padx=15, pady=3)
        ttk.Label(left, textvariable=self.engine_var, wraplength=530,
                  justify="left").pack(fill="x", padx=8, pady=5)

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True, padx=(8, 0))
        moves_tab = ttk.Frame(self.notebook, padding=5)
        self.analysis_tab = ttk.Frame(self.notebook, padding=5)
        history_tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(moves_tab, text="Moves")
        self.notebook.add(self.analysis_tab, text="Analysis")
        self.notebook.add(history_tab, text="Archive")
        self.moves_tree = self._tree(moves_tab, ("ply", "side", "san"),
                                    ("Ply", "Side", "Move"), (45, 65, 120))
        ttk.Label(moves_tab, text="Undo takes back one ply and pauses the game.",
                  wraplength=340).pack(fill="x", pady=5)
        analysis_bar = ttk.Frame(self.analysis_tab)
        analysis_bar.pack(fill="x", pady=(0, 6))
        ttk.Button(analysis_bar, text="Analyze game", command=self.start_analysis).pack(
            side="left")
        ttk.Button(analysis_bar, text="Cancel", command=self.cancel_analysis).pack(
            side="left", padx=3)
        ttk.Button(analysis_bar, text="Export JSON", command=self.export_report).pack(
            side="left")
        self.analysis_tree = self._tree(
            self.analysis_tab, ("ply", "san", "best", "loss", "grade"),
            ("Ply", "Move", "Best", "Loss cp", "Grade"), (35, 65, 70, 60, 80))
        self.analysis_tree.bind("<<TreeviewSelect>>", self._analysis_selected)
        self.report_text = tk.Text(self.analysis_tab, height=10, width=36,
                                   wrap="word", state="disabled")
        self.report_text.pack(fill="x", pady=(6, 0))
        history_bar = ttk.Frame(history_tab)
        history_bar.pack(fill="x", pady=(0, 6))
        ttk.Button(history_bar, text="Refresh", command=self.refresh_history).pack(side="left")
        ttk.Button(history_bar, text="Load selected", command=self.load_archive).pack(
            side="left", padx=5)
        self.history_tree = self._tree(history_tab, ("game", "result", "plies"),
                                      ("Game", "Result", "Plies"), (200, 70, 45))
        self.history_tree.bind("<Double-1>", lambda _event: self.load_archive())
        ttk.Label(outer, textvariable=self.status_var, anchor="w", wraplength=1050).pack(
            fill="x", pady=(7, 0))

    def _combo(self, parent, text, variable, values, width, callback=None):
        self.ttk.Label(parent, text=text).pack(side="left", padx=(4, 3))
        widget = self.ttk.Combobox(parent, textvariable=variable, values=values,
                                   state="readonly", width=width)
        widget.pack(side="left", padx=(0, 7))
        if callback:
            widget.bind("<<ComboboxSelected>>", callback)
        return widget

    def _tree(self, parent, columns, headings, widths):
        frame = self.ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = self.ttk.Treeview(frame, columns=columns, show="headings",
                                 selectmode="browse", height=12)
        scroll = self.ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        for column, heading, width in zip(columns, headings, widths):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=30, stretch=True)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return tree

    @staticmethod
    def _copy_record(record):
        return GameRecord(start_fen=record.start_fen, moves=list(record.moves),
                          headers=dict(record.headers), result=record.result,
                          termination=record.termination)

    def _cancel_work(self):
        self._generation += 1
        self._cancel.set()
        if self._searcher is not None:
            self._searcher.stop()
        self._searcher = None
        self._job = None
        self._pending_analysis = None
        # A retiring worker is not joined on the Tk thread. No replacement is
        # launched until it exits, so repeated resets cannot accumulate workers.
        if self._promotion_window is not None:
            self._promotion_window.destroy()
            self._promotion_window = None

    def _confirm_replace(self):
        return not self.record.moves or self.messagebox.askyesno(
            "Replace game?", "Replace the current game? Save PGN or Archive first to keep it.",
            parent=self.root)

    def new_game(self, confirm=False):
        if confirm and not self._confirm_replace():
            return False
        self._cancel_work()
        self.board = Board()
        mode = self.mode_var.get()
        human = WHITE if self.human_color_var.get() == "White" else BLACK
        names = []
        for color in (WHITE, BLACK):
            is_human = mode == "Human vs Human" or (mode == "Human vs AI" and color == human)
            names.append("Human" if is_human else "Chess Arena")
        self.record = GameRecord(headers={"Event": "Chess Arena", "White": names[WHITE],
                                          "Black": names[BLACK],
                                          "Date": datetime.now().strftime("%Y.%m.%d")})
        self._sans, self._clock_history = [], []
        seconds, self._increment = self.CLOCKS.get(self.time_control_var.get(), (0, 0))
        self._clocks = [float(seconds), float(seconds)]
        self._clock_enabled = seconds > 0
        self._last_tick = time.monotonic()
        self.paused = False
        self._archived_signature = None
        self._selected = self._drag_from = None
        self._clear_report()
        self.engine_var.set("Engine idle")
        self._refresh()
        return True

    def load_record(self, record):
        """Replace the game with a validated detached record, initially paused."""
        candidate = self._copy_record(record)
        board = candidate.replay()
        replay, sans = Board(candidate.start_fen), []
        for text in candidate.moves:
            move = replay.find_move(text)
            if move is None:
                raise ValueError("Illegal move in game: " + text)
            sans.append(replay.san(move))
            replay.make_move(move)
        self._cancel_work()
        self.record, self.board, self._sans = candidate, board, sans
        outcome = board.outcome()
        if candidate.result == "*" and outcome["result"] != "*":
            candidate.result, candidate.termination = outcome["result"], outcome["termination"]
        self.paused = True
        self._clock_enabled = False
        self._clocks = [0.0, 0.0]
        self._clock_history = [None] * len(candidate.moves)
        self._last_tick = time.monotonic()
        self._selected = self._drag_from = None
        self._archived_signature = None
        self._clear_report()
        self.engine_var.set("Imported game; clocks disabled")
        self._refresh()

    def _is_human(self, color):
        mode = self.mode_var.get()
        return mode == "Human vs Human" or (mode == "Human vs AI" and
            color == (WHITE if self.human_color_var.get() == "White" else BLACK))

    def _can_human_move(self):
        return (not self._closed and not self.paused and self.record.result == "*"
                and self._is_human(self.board.side) and self._job != "analysis")

    def play_move(self, move):
        """Play a legal human move (UCI/SAN or move tuple); return success."""
        if not self._can_human_move():
            return False
        if isinstance(move, str):
            move = self.board.find_move(move)
        if move not in self.board.legal_moves():
            return False
        return self._commit_move(move)

    def _commit_move(self, move):
        self._tick_clock()
        if self._closed or self.paused or self.record.result != "*":
            return False
        if move not in self.board.legal_moves():
            return False
        san, uci, side = self.board.san(move), self.board.uci(move), self.board.side
        self._clock_history.append(list(self._clocks) if self._clock_enabled else None)
        self._cancel_work()
        self.board.make_move(move)
        self.record.moves.append(uci)
        self._sans.append(san)
        if self._clock_enabled:
            self._clocks[side] += self._increment
        self._last_tick = time.monotonic()
        self._selected = self._drag_from = None
        self._clear_report()
        outcome = self.board.outcome()
        self.record.result, self.record.termination = outcome["result"], outcome["termination"]
        self._refresh()
        if self.record.result != "*":
            self.archive_game(automatic=True)
        return True

    def undo(self):
        self._tick_clock()
        self._cancel_work()
        self.paused = True
        if self.record.moves:
            self.record.moves.pop()
            self._sans.pop()
            previous_clock = self._clock_history.pop()
            if previous_clock is not None:
                self._clocks = previous_clock
            # Replaying also works with Board.clone(), whose undo stack is empty.
            self.record.result = self.record.termination = "*"
            self.record.headers.pop("Result", None)
            self.record.headers.pop("Termination", None)
            self.board = self.record.replay()
        self._last_tick = time.monotonic()
        self._selected = self._drag_from = None
        self._clear_report()
        self.engine_var.set("Undo: paused; Resume to continue")
        self._refresh()

    def toggle_pause(self):
        self._tick_clock()
        self._cancel_work()
        self.paused = not self.paused
        self._last_tick = time.monotonic()
        self._selected = self._drag_from = None
        self.engine_var.set("Paused" if self.paused else "Engine idle")
        self._refresh()

    def _mode_changed(self, _event=None):
        self._tick_clock()
        self._cancel_work()
        self.paused = True
        self._selected = self._drag_from = None
        self.engine_var.set("Mode changed; Resume or New / Reset to play")
        self._refresh()

    def _engine_settings_changed(self, _event=None):
        self._tick_clock()
        self._cancel_work()
        self.engine_var.set("Engine settings updated")
        self._refresh()

    def flip_board(self):
        self.flipped = not self.flipped
        self._drag_from = None
        self._draw_board()

    def _board_geometry(self):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        size = max(8.0, (min(width, height) - 36) / 8)
        return size, (width - size * 8) / 2, (height - size * 8) / 2

    def _square_center(self, square):
        size, left, top = self._board_geometry()
        file_index, rank = file_of(square), rank_of(square)
        column, row = (7 - file_index, rank) if self.flipped else (file_index, 7 - rank)
        return left + (column + 0.5) * size, top + (row + 0.5) * size

    def _event_square(self, event):
        size, left, top = self._board_geometry()
        column, row = int((event.x - left) // size), int((event.y - top) // size)
        if not (0 <= column < 8 and 0 <= row < 8):
            return None
        return square_of(7 - column, row) if self.flipped else square_of(column, 7 - row)

    def _draw_board(self):
        if self._closed:
            return
        canvas = self.canvas
        canvas.delete("all")
        size, left, top = self._board_geometry()
        last = set()
        if self.record.moves:
            uci = self.record.moves[-1]
            last = {parse_square(uci[:2]), parse_square(uci[2:4])}
        targets = {m[1] for m in self.board.legal_moves() if m[0] == self._selected}
        checked_king = self.board.kings[self.board.side] if self.board.in_check() else None
        for rank in range(8):
            for file_index in range(8):
                square = square_of(file_index, rank)
                x, y = self._square_center(square)
                light = (rank + file_index) % 2 != 0
                color = "#e9e3d2" if light else "#789486"
                if square in last:
                    color = "#e0cf7d" if light else "#b7b367"
                canvas.create_rectangle(x - size/2, y - size/2, x + size/2, y + size/2,
                                        fill=color, outline=color)
                if square == self._selected or square == checked_king:
                    canvas.create_rectangle(x - size/2 + 2, y - size/2 + 2,
                                            x + size/2 - 2, y + size/2 - 2,
                                            outline="#d45550" if square == checked_king else "#217fc0",
                                            width=3)
                piece = self.board.sq[square]
                if square in targets:
                    radius = size * (0.40 if piece else 0.095)
                    canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                       fill="" if piece else "#426858", outline="#426858", width=3)
                if piece:
                    tag = "piece_%d" % square
                    glyph = self.GLYPHS[kind_of(piece)]
                    font = ("DejaVu Sans", max(10, int(size * 0.64)))
                    if color_of(piece) == WHITE:
                        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                            canvas.create_text(x+dx, y+dy, text=glyph, font=font,
                                               fill="#26343a", tags=tag)
                    canvas.create_text(x, y, text=glyph, font=font,
                                       fill="#fffaf0" if color_of(piece) == WHITE else "#18262f",
                                       tags=tag)
        for i in range(8):
            canvas.create_text(left+(i+0.5)*size, top+8*size+11,
                               text=FILES[7-i if self.flipped else i], fill="#e8eced")
            canvas.create_text(left-11, top+(i+0.5)*size,
                               text=str(i+1 if self.flipped else 8-i), fill="#e8eced")

    def _on_press(self, event):
        self._press_consumed = False
        if not self._can_human_move():
            return
        square = self._event_square(event)
        if square is None:
            self._selected = None
            self._draw_board()
            return
        if self._selected is not None and square != self._selected:
            if self._try_move(self._selected, square):
                self._press_consumed = True
                return
        piece = self.board.sq[square]
        if piece and color_of(piece) == self.board.side:
            self._selected = self._drag_from = square
            self._drag_xy = (event.x, event.y)
        else:
            self._selected = self._drag_from = None
        self._draw_board()

    def _on_drag(self, event):
        if self._drag_from is None or not self._can_human_move():
            return
        x, y = self._drag_xy
        tag = "piece_%d" % self._drag_from
        self.canvas.move(tag, event.x-x, event.y-y)
        self.canvas.tag_raise(tag)
        self._drag_xy = (event.x, event.y)

    def _on_release(self, event):
        if self._press_consumed:
            self._press_consumed = False
            return
        source, target = self._drag_from, self._event_square(event)
        self._drag_from = None
        if source is not None and target is not None and source != target:
            self._try_move(source, target)
        self._draw_board()

    def _try_move(self, source, target):
        if not self._can_human_move():
            return False
        moves = [move for move in self.board.legal_moves()
                 if move[0] == source and move[1] == target]
        if not moves:
            return False
        generation = self._generation
        if len(moves) > 1:
            promotion = self._choose_promotion()
            moves = [move for move in moves if move[2] == promotion]
        if not moves or self._closed or generation != self._generation:
            return False
        return self.play_move(moves[0])

    def _choose_promotion(self):
        window = self.tk.Toplevel(self.root)
        self._promotion_window = window
        window.title("Promote pawn")
        window.transient(self.root)
        window.resizable(False, False)
        answer = []
        self.ttk.Label(window, text="Choose a promotion piece:", padding=12).pack()
        buttons = self.ttk.Frame(window, padding=10)
        buttons.pack()

        def choose(piece):
            answer.append(piece)
            window.destroy()

        for piece in (QUEEN, ROOK, BISHOP, KNIGHT):
            self.ttk.Button(buttons, text=PIECE_NAMES[piece].title(),
                            command=lambda p=piece: choose(p)).pack(side="left", padx=3)
        window.bind("<Escape>", lambda _event: window.destroy())
        window.grab_set()
        self.root.wait_window(window)
        self._promotion_window = None
        return answer[0] if answer else None

    def _tick_clock(self):
        now = time.monotonic()
        elapsed, self._last_tick = max(0.0, now-self._last_tick), now
        if self._clock_enabled and not self.paused and self.record.result == "*":
            side = self.board.side
            self._clocks[side] = max(0.0, self._clocks[side]-elapsed)
            if self._clocks[side] <= 0:
                self.record.result = "0-1" if side == WHITE else "1-0"
                self.record.termination = "time forfeit"
                self._cancel_work()
                self._refresh()
                self.archive_game(automatic=True)
        self._update_clocks()

    def _update_clocks(self):
        for color, name in ((WHITE, "White"), (BLACK, "Black")):
            seconds = max(0, int(math.ceil(self._clocks[color])))
            clock = "%d:%02d" % divmod(seconds, 60) if self._clock_enabled else "--:--"
            marker = " >" if self.board.side == color and self.record.result == "*" else ""
            self.clock_vars[color].set("%s%s   %s" % (name, marker, clock))

    def _refresh(self):
        self.pause_var.set("Resume" if self.paused else "Pause")
        self._update_clocks()
        side = "White" if self.board.side == WHITE else "Black"
        if self.record.result != "*":
            status = "%s — %s" % (self.record.result, self.record.termination)
        else:
            status = "%s to move%s%s" % (side, " — check" if self.board.in_check() else "",
                                         " — paused" if self.paused else "")
        self.status_var.set(status)
        self.moves_tree.delete(*self.moves_tree.get_children())
        first_side = Board(self.record.start_fen).side
        for index, san in enumerate(self._sans):
            self.moves_tree.insert("", "end", iid=str(index), values=(index+1,
                "White" if (first_side+index) % 2 == WHITE else "Black", san))
        if self._sans:
            self.moves_tree.see(str(len(self._sans)-1))
        score = Evaluator().evaluate(self.board)
        self._show_eval(score if self.board.side == WHITE else -score, "static")
        self._draw_board()

    def _show_eval(self, score, label):
        if is_mate_score(score):
            text = "%s has a forced mate" % ("White" if score > 0 else "Black")
        else:
            text = "White %+.2f" % (score/100.0)
        self.eval_var.set("%s (%s)" % (text, label))
        self.eval_bar["value"] = 50 + 50 * math.tanh(score/600.0)

    # Worker functions intentionally have no app, root, widget or Tk variable.
    @staticmethod
    def _search_worker(events, generation, board, searcher, cancel, depth, seconds):
        side = board.side

        def snapshot(info):
            return {"side": side, "score": info.score, "depth": info.depth,
                    "nodes": info.nodes, "time": info.time,
                    "best_move": info.best_move,
                    "pv": " ".join(board.uci(move) for move in list(info.pv))}

        def update(info):
            if cancel.is_set():
                searcher.stop()
                raise SearchTimeout()
            events.put((generation, "engine_update", snapshot(info)))

        try:
            if cancel.is_set():
                return
            info = searcher.search(board, depth, _GUIBudget(seconds, cancel), on_update=update)
            if not cancel.is_set():
                events.put((generation, "engine_done", snapshot(info)))
        except SearchTimeout:
            if not cancel.is_set():
                events.put((generation, "error", ("Engine", "Search interrupted")))
        except Exception as exc:
            events.put((generation, "error", ("Engine", "%s: %s" % (type(exc).__name__, exc))))

    @staticmethod
    def _analysis_worker(events, generation, record, cancel, seconds, depth):
        try:
            report = analyze_game(record, seconds=seconds, depth=depth, cancel=cancel,
                                  on_progress=lambda done, total: events.put(
                                      (generation, "analysis_progress", (done, total))))
            if not cancel.is_set():
                events.put((generation, "analysis_done", report))
        except SearchTimeout:
            if not cancel.is_set():
                events.put((generation, "error", ("Analysis", "Analysis interrupted")))
        except Exception as exc:
            events.put((generation, "error", ("Analysis", "%s: %s" % (type(exc).__name__, exc))))

    def _advance_work(self):
        if self._closed or self._job is not None:
            return
        if self._worker is not None and self._worker.is_alive():
            return
        if self._pending_analysis is not None:
            record, seconds, depth = self._pending_analysis
            self._pending_analysis = None
            self._cancel = threading.Event()
            self._job = "analysis"
            self._worker = threading.Thread(target=self._analysis_worker,
                args=(self._events, self._generation, record, self._cancel, seconds, depth),
                name="ChessArena-analysis", daemon=True)
        elif not self.paused and self.record.result == "*" and not self._is_human(self.board.side):
            depth, seconds = self.STRENGTHS.get(self.strength_var.get(), (2, 0.20))
            if self._clock_enabled:
                seconds = min(seconds, max(0.02, self._clocks[self.board.side]/20))
            style = self.style_var.get() if self.board.side == WHITE else self.black_style_var.get()
            self._cancel = threading.Event()
            self._searcher = Searcher(Evaluator(style), TranspositionTable())
            self._job = "engine"
            self.engine_var.set("%s AI thinking…" % ("White" if self.board.side == WHITE else "Black"))
            self._worker = threading.Thread(target=self._search_worker,
                args=(self._events, self._generation, self.board.clone(), self._searcher,
                      self._cancel, depth, seconds), name="ChessArena-search", daemon=True)
        else:
            return
        self._worker.start()

    def _pump(self):
        self._after_id = None
        if self._closed:
            return
        self._tick_clock()
        # Limit work per tick even if a long analysis produced many messages.
        for _ in range(100):
            try:
                generation, kind, payload = self._events.get_nowait()
            except self._queue_empty:
                break
            if generation != self._generation:
                continue
            if kind in ("engine_update", "engine_done"):
                score = payload["score"] if payload["side"] == WHITE else -payload["score"]
                self._show_eval(score, "search depth %d" % payload["depth"])
                self.engine_var.set("Depth %d · %s nodes · %.2f s\nPV: %s" % (
                    payload["depth"], format(payload["nodes"], ","), payload["time"], payload["pv"]))
                if kind == "engine_done":
                    self._job = None
                    if not self.paused and not self._is_human(self.board.side):
                        if not self._commit_move(payload["best_move"]):
                            self.paused = True
                            self._refresh()
                            self.status_var.set("Engine returned no legal move; paused")
                        else:
                            self._show_eval(score, "last search")
            elif kind == "analysis_progress":
                self.engine_var.set("Analyzing game: %d / %d plies" % payload)
            elif kind == "analysis_done":
                self._job = None
                self.report = payload
                self._display_report()
                self.engine_var.set("Analysis complete; game remains paused")
            elif kind == "error":
                self._job = None
                self.paused = True
                self._refresh()
                self.engine_var.set("%s error: %s" % payload)
                self.status_var.set("%s failed; paused. Change settings or Resume to retry." % payload[0])
        self._advance_work()
        if not self._closed:
            self._after_id = self.root.after(40, self._pump)

    def _clear_report(self):
        self.report = None
        self.analysis_tree.delete(*self.analysis_tree.get_children())
        self._set_report_text("Analyze a game to see move grades, alternatives and coaching hints.")

    def _set_report_text(self, text):
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", text)
        self.report_text.configure(state="disabled")

    def start_analysis(self, seconds=0.1, depth=3):
        if not self.record.moves:
            self.status_var.set("Play or import some moves before analyzing a game.")
            return False
        self._tick_clock()
        self._cancel_work()
        self.paused = True
        self._selected = self._drag_from = None
        self._clear_report()
        self._pending_analysis = (self._copy_record(self.record), max(0.02, float(seconds)),
                                  max(1, int(depth)))
        self._refresh()
        self.notebook.select(self.analysis_tab)
        self.engine_var.set("Analysis queued; game paused")
        self._advance_work()
        return True

    def cancel_analysis(self):
        if self._job == "analysis" or self._pending_analysis is not None:
            self._cancel_work()
            self.engine_var.set("Analysis canceled; game remains paused")

    def _display_report(self):
        self.analysis_tree.delete(*self.analysis_tree.get_children())
        for index, row in enumerate(self.report.get("moves", [])):
            self.analysis_tree.insert("", "end", iid=str(index), values=(
                row.get("ply", index+1), row.get("san", ""), row.get("best", ""),
                row.get("loss_cp", ""), row.get("grade", "")))
        self._set_report_text("Summary\n" + json.dumps(self.report.get("summary", {}),
                                                     indent=2, ensure_ascii=False))
        self.notebook.select(self.analysis_tab)

    def _analysis_selected(self, _event=None):
        selected = self.analysis_tree.selection()
        if not selected or not self.report:
            return
        row = self.report.get("moves", [])[int(selected[0])]
        self._set_report_text("Ply %s: %s\nBest: %s\nLoss: %s cp · %s\n\n%s" % (
            row.get("ply", ""), row.get("san", ""), row.get("best", ""),
            row.get("loss_cp", ""), row.get("grade", ""), row.get("hint", "")))

    def open_pgn(self):
        path = self.filedialog.askopenfilename(parent=self.root, title="Open PGN",
            filetypes=(("Chess PGN", "*.pgn"), ("All files", "*")))
        if not path or not self._confirm_replace():
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                text = handle.read(8 * 1024 * 1024 + 1)
            if len(text) > 8 * 1024 * 1024:
                raise ValueError("PGN is too large (maximum 8 MiB)")
            self.load_record(parse_pgn(text))
        except Exception as exc:
            self.messagebox.showerror("Cannot open PGN", str(exc), parent=self.root)

    def save_pgn(self):
        path = self.filedialog.asksaveasfilename(parent=self.root, title="Save PGN",
            defaultextension=".pgn", filetypes=(("Chess PGN", "*.pgn"),))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(export_pgn(self._copy_record(self.record), report=self.report))
            self.status_var.set("PGN saved: " + path)
        except Exception as exc:
            self.messagebox.showerror("Cannot save PGN", str(exc), parent=self.root)

    def export_report(self):
        if self.report is None:
            self.status_var.set("Analyze the current game before exporting its report.")
            return
        path = self.filedialog.asksaveasfilename(parent=self.root, title="Export analysis report",
            defaultextension=".json", filetypes=(("JSON report", "*.json"),))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.report, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            self.status_var.set("Report saved: " + path)
        except Exception as exc:
            self.messagebox.showerror("Cannot export report", str(exc), parent=self.root)

    def archive_game(self, automatic=False):
        if not self.record.moves:
            return
        signature = (self.record.start_fen, tuple(self.record.moves), self.record.result,
                     self.record.termination)
        if signature == self._archived_signature:
            return
        try:
            identifier = self.store.archive(self._copy_record(self.record))
            self._archived_signature = signature
            self.refresh_history()
            if not automatic:
                self.status_var.set("Game archived: " + str(identifier))
        except Exception as exc:
            self.status_var.set("Could not archive game: " + str(exc))

    def refresh_history(self):
        try:
            entries = self.store.history()
            self.history_tree.delete(*self.history_tree.get_children())
            self._archives = {}
            for index, entry in enumerate(entries):
                headers = entry.get("headers", {})
                label = "%s: %s – %s" % (headers.get("Date", str(entry.get("id", "Game"))),
                                         headers.get("White", "White"), headers.get("Black", "Black"))
                key = str(index)
                self._archives[key] = entry
                self.history_tree.insert("", "end", iid=key, values=(
                    label, entry.get("result", "*"), len(entry.get("moves", []))))
        except Exception as exc:
            self.status_var.set("Could not load archive: " + str(exc))

    def load_archive(self):
        selected = self.history_tree.selection()
        if not selected or not self._confirm_replace():
            return
        try:
            entry = self._archives[selected[0]]
            self.load_record(GameRecord(start_fen=entry.get("start_fen", START_FEN),
                moves=list(entry.get("moves", [])), headers=dict(entry.get("headers", {})),
                result=entry.get("result", "*"), termination=entry.get("termination", "*")))
            self.notebook.select(0)
        except Exception as exc:
            self.messagebox.showerror("Cannot load archived game", str(exc), parent=self.root)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel_work()
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._profile["gui"] = {"mode": self.mode_var.get(),
            "human_color": self.human_color_var.get(), "white_style": self.style_var.get(),
            "black_style": self.black_style_var.get(), "strength": self.strength_var.get(),
            "clock": self.time_control_var.get(), "flipped": self.flipped}
        try:
            self.store.save_profile(self._profile)
        except Exception as exc:
            print("Chess Arena: profile could not be saved: %s" % exc, file=sys.stderr)
        self.root.destroy()


def launch_gui(store=None) -> int:
    """Launch Tk, or report missing Tk/display and return a nonzero exit code."""
    try:
        import tkinter as tk
    except ImportError as exc:
        print("Chess Arena GUI requires tkinter: %s. Headless commands still work." % exc,
              file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print("Chess Arena cannot open a display: %s. Use a headless CLI command instead." % exc,
              file=sys.stderr)
        return 1
    try:
        ChessApp(root, Store() if store is None else store)
        root.mainloop()
    except Exception as exc:
        print("Chess Arena GUI error: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        try:
            root.destroy()
        except tk.TclError:
            pass
        return 1
    return 0
