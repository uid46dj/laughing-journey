

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
