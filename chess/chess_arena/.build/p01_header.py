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
