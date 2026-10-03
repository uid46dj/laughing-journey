
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
