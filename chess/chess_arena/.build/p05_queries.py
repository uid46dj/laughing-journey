
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
