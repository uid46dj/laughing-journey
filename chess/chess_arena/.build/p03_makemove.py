
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
