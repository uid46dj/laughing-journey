
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
