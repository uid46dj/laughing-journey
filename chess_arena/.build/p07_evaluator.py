

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

