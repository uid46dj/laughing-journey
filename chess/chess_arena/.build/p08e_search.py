
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
