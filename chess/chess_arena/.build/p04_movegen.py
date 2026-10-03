
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
