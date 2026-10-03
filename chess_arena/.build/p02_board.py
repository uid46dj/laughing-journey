

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
