
# ==========================================================================
#  GAME RECORDS, PGN AND SAFE JSON PERSISTENCE
# ==========================================================================
import tempfile
import uuid
import warnings

_PGN_RESULTS = frozenset(("1-0", "0-1", "1/2-1/2", "*"))
_PGN_TAG_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_UCI_MOVE = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?\Z")


def _record_board(fen: str) -> Board:
    """Validate a standard six-field FEN before giving it to the engine.

    This checks local legality, not whether a position is historically reachable.
    FEN may specify an en-passant target even when no capture is available.
    """
    if not isinstance(fen, str):
        raise ValueError("FEN must be text")
    parts = fen.split()
    if len(parts) != 6:
        raise ValueError("FEN must have six fields")
    rows = parts[0].split("/")
    if len(rows) != 8:
        raise ValueError("FEN must have eight ranks")
    for row in rows:
        width = 0
        previous_digit = False
        for ch in row:
            if ch in "12345678":
                if previous_digit:
                    raise ValueError("FEN contains adjacent empty-square counts")
                width += int(ch)
                previous_digit = True
            elif ch in "PNBRQKpnbrqk":
                width += 1
                previous_digit = False
            else:
                raise ValueError("Invalid FEN piece or empty-square count")
        if width != 8:
            raise ValueError("Each FEN rank must contain eight squares")
    if parts[0].count("K") != 1 or parts[0].count("k") != 1:
        raise ValueError("FEN must contain exactly one king of each color")
    if any(ch in "Pp" for ch in rows[0] + rows[-1]):
        raise ValueError("FEN has an unpromoted pawn on a back rank")
    for pieces in ("PNBRQK", "pnbrqk"):
        if sum(parts[0].count(ch) for ch in pieces) > 16 or parts[0].count(pieces[0]) > 8:
            raise ValueError("FEN has too many pieces or pawns")
    if parts[1] not in ("w", "b"):
        raise ValueError("FEN side must be w or b")
    rights = parts[2]
    if rights != "-" and (not rights or any(ch not in "KQkq" for ch in rights)
                            or len(set(rights)) != len(rights)):
        raise ValueError("Invalid FEN castling rights")
    if parts[3] != "-" and not re.fullmatch(r"[a-h][36]", parts[3]):
        raise ValueError("Invalid FEN en-passant square")
    if not re.fullmatch(r"[0-9]+", parts[4]) or not re.fullmatch(r"[0-9]+", parts[5]):
        raise ValueError("FEN counters must be nonnegative integers")
    if int(parts[5]) < 1:
        raise ValueError("FEN move number must be at least one")
    try:
        board = Board(fen)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError("Invalid FEN: %s" % exc) from exc
    for right, color, king, rook in (("K", WHITE, 4, 7), ("Q", WHITE, 4, 0),
                                      ("k", BLACK, 116, 119), ("q", BLACK, 116, 112)):
        if right in rights and (board.sq[king] != make_piece(KING, color)
                               or board.sq[rook] != make_piece(ROOK, color)):
            raise ValueError("FEN castling right has no home king/rook")
    if parts[3] != "-":
        ep = parse_square(parts[3])
        forward = 16 if board.side == WHITE else -16
        if (rank_of(ep) != (5 if board.side == WHITE else 2)
                or board.sq[ep] or board.sq[ep + forward]
                or board.sq[ep - forward] != make_piece(PAWN, opposite(board.side))
                or board.half != 0):
            raise ValueError("FEN en-passant target is inconsistent with a double pawn move")
    if board.in_check(opposite(board.side)):
        raise ValueError("FEN leaves the side that just moved in check")
    return board


def _record_text(value, name):
    if not isinstance(value, str) or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("%s must be text without control characters" % name)
    return value


@dataclass
class GameRecord:
    start_fen: str = START_FEN
    moves: list[str] = field(default_factory=list)
    headers: dict = field(default_factory=dict)
    result: str = "*"
    termination: str = "*"

    def replay(self) -> Board:
        """Return a fresh board after all legal UCI moves, or raise ValueError."""
        board = _record_start(self)
        for ply, text in enumerate(self.moves, 1):
            board.make_move(_record_move(board, text, ply))
        return board


def _record_start(record: GameRecord) -> Board:
    if not isinstance(record, GameRecord):
        raise ValueError("Expected a GameRecord")
    if not isinstance(record.moves, list):
        raise ValueError("Record moves must be a list of UCI strings")
    if not isinstance(record.result, str) or record.result not in _PGN_RESULTS:
        raise ValueError("Invalid game result")
    _record_text(record.termination, "Termination")
    if not isinstance(record.headers, dict):
        raise ValueError("Record headers must be a dictionary")
    for key, value in record.headers.items():
        if not isinstance(key, str) or not _PGN_TAG_NAME.fullmatch(key):
            raise ValueError("Invalid PGN tag name")
        _record_text(value, "PGN header " + key)
    return _record_board(record.start_fen)


def _record_move(board: Board, text: str, ply: int):
    if not isinstance(text, str) or not _UCI_MOVE.fullmatch(text):
        raise ValueError("Invalid UCI move at ply %d: %r" % (ply, text))
    for move in board.legal_moves():
        if board.uci(move) == text:
            return move
    raise ValueError("Illegal move at ply %d: %s" % (ply, text))


def _pgn_tokens(text):
    """Strict lexer: balanced RAVs are skipped, never truncated at bad input."""
    index, depth = 0, 0
    length = len(text)
    tag = re.compile(r'\[\s*([A-Za-z][A-Za-z0-9_]*)\s+"((?:\\["\\]|[^"\\\r\n])*)"\s*\]')
    while index < length:
        ch = text[index]
        if ch.isspace():
            index += 1
            continue
        if ch == "%" and (index == 0 or text[index - 1] in "\r\n"):
            end = text.find("\n", index)
            index = length if end < 0 else end + 1
            continue
        if ch == ";":
            end = text.find("\n", index)
            index = length if end < 0 else end + 1
            continue
        if ch == "{":
            end = text.find("}", index + 1)
            if end < 0 or "{" in text[index + 1:end]:
                raise ValueError("Unclosed or nested PGN brace comment")
            index = end + 1
            continue
        if ch == "}":
            raise ValueError("Unexpected closing PGN comment brace")
        if ch == "(":
            if not depth:
                yield "variation", "("
            depth += 1
            index += 1
            continue
        if ch == ")":
            if not depth:
                raise ValueError("Unexpected closing PGN variation")
            depth -= 1
            index += 1
            continue
        if ch in "[]":
            if depth:
                raise ValueError("PGN headers cannot occur inside variations")
            match = tag.match(text, index)
            if not match:
                raise ValueError("Malformed PGN tag at character %d" % index)
            value = re.sub(r'\\(["\\])', r'\1', match.group(2))
            yield "tag", (match.group(1), value)
            index = match.end()
            continue
        if depth:
            index += 1
            continue
        match = re.match(r"([0-9]+)(\.\.\.|\.)", text[index:])
        if match:
            yield "number", (int(match.group(1)), len(match.group(2)))
            index += match.end()
            continue
        if ch == "$":
            match = re.match(r"\$([0-9]+)", text[index:])
            if not match or int(match.group(1)) > 255:
                raise ValueError("Invalid PGN numeric annotation glyph")
            yield "nag", int(match.group(1))
            index += match.end()
            continue
        end = index
        while end < length and not text[end].isspace() and text[end] not in "{}();[]$":
            end += 1
        if end == index:
            raise ValueError("Unrecognized PGN input at character %d" % index)
        yield "symbol", text[index:end]
        index = end
    if depth:
        raise ValueError("Unclosed PGN variation")


def _pgn_san_move(board, token):
    token = re.sub(r"(?:!!|\?\?|!\?|\?!|!|\?)$", "", token)
    if token.startswith("0-0"):
        token = token.replace("0", "O")
    if token.endswith("++"):
        token = token[:-1]
    pattern = r"(?:O-O(?:-O)?|[KQRBN](?:[a-h][1-8]|[a-h]|[1-8])?x?[a-h][1-8]|[a-h](?:x[a-h])?[1-8](?:=[QRBN])?)[+#]?"
    if not re.fullmatch(pattern, token):
        raise ValueError("Unrecognized SAN token: %r" % token)
    candidates = []
    for move in board.legal_moves():
        san = board.san(move)
        # Missing check suffixes are a common import convention. An explicit
        # but incorrect check/mate suffix is never accepted.
        if san == token or (not token.endswith(("+", "#")) and san.rstrip("+#") == token):
            candidates.append(move)
    if len(candidates) != 1:
        raise ValueError("Illegal or ambiguous SAN move: %s" % token)
    return candidates[0]


def parse_pgn(text: str) -> GameRecord:
    """Parse one standard-chess PGN game; a movetext result is mandatory.

    Comments, NAGs and balanced nested variations are ignored. Legal mainline
    SAN, move numbers, tags, FEN and result agreement are checked. Multiple
    games, unsupported variants, garbage and unfinished syntax raise ValueError.
    """
    if not isinstance(text, str):
        raise ValueError("PGN must be text")
    text = text.lstrip("\ufeff")
    headers, moves = {}, []
    board = None
    pending_number, finished = False, False
    result, start_fen = "*", START_FEN
    for kind, value in _pgn_tokens(text):
        if finished:
            raise ValueError("Unexpected input after PGN result (only one game is supported)")
        if kind == "tag":
            if board is not None:
                raise ValueError("PGN tags must precede movetext")
            key, val = value
            if key in headers:
                raise ValueError("Duplicate PGN tag: " + key)
            headers[key] = _record_text(val, "PGN header " + key)
            continue
        if board is None:
            if headers.get("Variant", "Standard").lower() not in ("standard", "chess"):
                raise ValueError("Only standard chess PGN is supported")
            setup = headers.get("SetUp")
            if setup not in (None, "0", "1"):
                raise ValueError("PGN SetUp must be 0 or 1")
            if setup == "1" and "FEN" not in headers:
                raise ValueError("PGN SetUp 1 requires a FEN tag")
            if setup == "0" and "FEN" in headers:
                raise ValueError("PGN FEN conflicts with SetUp 0")
            if "Result" in headers and headers["Result"] not in _PGN_RESULTS:
                raise ValueError("Invalid PGN Result tag")
            start_fen = headers.get("FEN", START_FEN)
            board = _record_board(start_fen)
        if kind in ("variation", "nag") or (kind == "symbol" and value in ("!", "?", "!!", "??", "!?", "?!")):
            if not moves or pending_number:
                raise ValueError("PGN annotation must follow a move")
            continue
        if kind == "number":
            number, dots = value
            if pending_number or number != board.full or dots != (1 if board.side == WHITE else 3):
                raise ValueError("Incorrect PGN move number or side")
            pending_number = True
            continue
        if value in _PGN_RESULTS:
            if pending_number:
                raise ValueError("PGN ends after an unplayed move number")
            result, finished = value, True
            continue
        try:
            move = _pgn_san_move(board, value)
        except ValueError as exc:
            raise ValueError("PGN ply %d: %s" % (len(moves) + 1, exc)) from exc
        moves.append(board.uci(move))
        board.make_move(move)
        pending_number = False
    if not finished:
        raise ValueError("PGN is missing its movetext result marker")
    if "Result" in headers and headers["Result"] != result:
        raise ValueError("PGN header and movetext results disagree")
    if result != "*" and not board.legal_moves():
        forced = "1-0" if board.side == BLACK else "0-1"
        if not board.in_check():
            forced = "1/2-1/2"
        if result != forced:
            raise ValueError("PGN result contradicts the final checkmate/stalemate position")
    return GameRecord(start_fen, moves, headers, result, headers.get("Termination", "*"))


def export_pgn(record: GameRecord, report: dict | None = None) -> str:
    """Export legal SAN with escaped tags and optional, safely quoted comments."""
    board = _record_start(record)
    headers = {"Event": "Chess Arena", "Site": "?", "Date": "????.??.??", "Round": "?",
               "White": "White", "Black": "Black", "Result": record.result}
    headers.update(record.headers)
    headers["Result"] = record.result
    if record.start_fen != START_FEN:
        headers.update({"SetUp": "1", "FEN": record.start_fen})
    else:
        headers.pop("SetUp", None)
        headers.pop("FEN", None)
    if record.termination != "*":
        headers["Termination"] = record.termination
    else:
        headers.pop("Termination", None)
    lines = []
    for key, value in headers.items():
        value = _record_text(value, "PGN header " + key).replace("\\", "\\\\").replace('"', '\\"')
        lines.append('[%s "%s"]' % (key, value))
    annotations = {}
    if isinstance(report, dict):
        for row in report.get("moves", []):
            if isinstance(row, dict) and isinstance(row.get("ply"), int):
                annotations[row["ply"]] = row
    tokens = []
    for ply, uci in enumerate(record.moves, 1):
        move = _record_move(board, uci, ply)
        if board.side == WHITE:
            tokens.append("%d." % board.full)
        elif ply == 1:
            tokens.append("%d..." % board.full)
        tokens.append(board.san(move))
        board.make_move(move)
        row = annotations.get(ply)
        if row:
            parts = [str(row[key]) for key in ("grade", "hint") if row.get(key)]
            if row.get("loss_cp") is not None:
                parts.append("estimated loss %s cp" % row["loss_cp"])
            if row.get("best"):
                parts.append("engine choice " + str(row["best"]))
            comment = "; ".join(parts).replace("{", "(").replace("}", ")")
            comment = " ".join(comment.split())
            if comment:
                tokens.append("{ " + comment + " }")
    tokens.append(record.result)
    # Wrap between tokens, not inside tags/SAN or brace comments.
    body, current = [], ""
    for token in tokens:
        if current and len(current) + len(token) + 1 > 88:
            body.append(current)
            current = ""
        current = (current + " " + token).strip()
    if current:
        body.append(current)
    return "\n".join(lines) + "\n\n" + "\n".join(body) + "\n"


def _json_check(value):
    """Reject non-JSON types, non-string keys and NaN/Infinity before saving."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _json_check(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_check(item)
        return
    raise ValueError("Persistence accepts only finite JSON values with string dictionary keys")


class Store:
    """Atomic JSON profile/archive plus a small result-weighted opening book.

    Bad files are preserved, skipped/defaulted and reported both through
    ``warnings`` and RuntimeWarning. Writes raise OSError when unsuccessful.
    One instance is thread-safe; simultaneous independent processes are not
    coordinated when updating the derived opening statistics.
    """

    BOOK_PLIES = 20
    BOOK_POSITIONS = 10000
    MAX_JSON_BYTES = 8 * 1024 * 1024

    def __init__(self, data_dir=None):
        self.data_dir = os.path.abspath(os.path.expanduser(os.fspath(data_dir) if data_dir is not None
                                                         else "~/.chess_arena"))
        self.archive_dir = os.path.join(self.data_dir, "games")
        os.makedirs(self.archive_dir, mode=0o700, exist_ok=True)
        self.warnings = []
        self._lock = threading.RLock()

    def _warn(self, message):
        self.warnings.append(message)
        warnings.warn(message, RuntimeWarning, stacklevel=3)

    def _read_json(self, path, default, validator):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read(self.MAX_JSON_BYTES + 1)
            if len(text.encode("utf-8")) > self.MAX_JSON_BYTES:
                raise ValueError("JSON file exceeds size limit")
            def pairs(items):
                result = {}
                for key, val in items:
                    if key in result:
                        raise ValueError("Duplicate JSON key: " + key)
                    result[key] = val
                return result
            value = json.loads(text, object_pairs_hook=pairs)
            _json_check(value)
            validator(value)
            return value
        except FileNotFoundError:
            return default
        except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
            self._warn("Cannot load %s: %s; file preserved, using default/skipping" % (path, exc))
            return default

    def _write_json(self, path, value):
        _json_check(value)
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        if len(text.encode("utf-8")) > self.MAX_JSON_BYTES:
            raise ValueError("JSON data exceeds size limit")
        descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=os.path.dirname(path))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _profile_ok(profile):
        if not isinstance(profile, dict):
            raise ValueError("Profile must be a JSON object")

    def load_profile(self) -> dict:
        with self._lock:
            return self._read_json(os.path.join(self.data_dir, "profile.json"),
                                   {"version": 1, "games_played": 0, "settings": {}}, self._profile_ok)

    def save_profile(self, profile: dict):
        self._profile_ok(profile)
        with self._lock:
            self._write_json(os.path.join(self.data_dir, "profile.json"), profile)

    @staticmethod
    def _entry_ok(entry):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not re.fullmatch(r"[0-9a-f]{32}", entry["id"]):
            raise ValueError("Invalid archive identifier")
        required = ("start_fen", "moves", "headers", "result", "termination", "created_utc")
        if any(key not in entry for key in required):
            raise ValueError("Archive entry is missing record fields")
        _record_text(entry["created_utc"], "Archive timestamp")
        GameRecord(entry["start_fen"], entry["moves"], entry["headers"],
                   entry["result"], entry["termination"]).replay()

    def archive(self, record: GameRecord) -> str:
        record.replay()
        identifier = uuid.uuid4().hex
        entry = {"id": identifier, "created_utc": utc_stamp(), "start_fen": record.start_fen,
                 "moves": list(record.moves), "headers": dict(record.headers),
                 "result": record.result, "termination": record.termination}
        with self._lock:
            # Load before adding the archive: a rebuild must not count it twice.
            book = self.opening_stats()
            self._write_json(os.path.join(self.archive_dir, identifier + ".json"), entry)
            self._learn(book, record)
            try:
                self._write_json(os.path.join(self.data_dir, "openings.json"), book)
            except (OSError, ValueError) as exc:
                self._warn("Game %s was archived, but opening statistics could not be saved: %s" % (identifier, exc))
        return identifier

    def history(self) -> list[dict]:
        with self._lock:
            entries = []
            for filename in sorted(os.listdir(self.archive_dir)):
                if not filename.endswith(".json") or filename.startswith(".tmp-"):
                    continue
                path = os.path.join(self.archive_dir, filename)
                entry = self._read_json(path, None, self._entry_ok)
                if entry is not None:
                    if filename != entry["id"] + ".json":
                        self._warn("Archive filename/identifier mismatch: " + path)
                    else:
                        entries.append(entry)
            return sorted(entries, key=lambda row: (row["created_utc"], row["id"]), reverse=True)

    @staticmethod
    def _book_ok(book):
        if not isinstance(book, dict) or book.get("version") != 1 or not isinstance(book.get("positions"), dict):
            raise ValueError("Invalid opening book schema")
        if type(book.get("games")) is not int or book["games"] < 0:
            raise ValueError("Invalid opening game count")
        if len(book["positions"]) > Store.BOOK_POSITIONS:
            raise ValueError("Opening book has too many positions")
        for position, choices in book["positions"].items():
            if not isinstance(position, str) or not isinstance(choices, dict):
                raise ValueError("Invalid opening book position")
            for uci, stats in choices.items():
                if not _UCI_MOVE.fullmatch(uci) or not isinstance(stats, dict):
                    raise ValueError("Invalid opening move")
                for field_name in ("wins", "draws", "losses", "unfinished"):
                    if type(stats.get(field_name)) is not int or stats[field_name] < 0:
                        raise ValueError("Invalid opening result counts")

    @staticmethod
    def _book_key(board):
        return " ".join(board.fen().split()[:4])

    def _learn(self, book, record):
        board = _record_board(record.start_fen)
        for ply, text in enumerate(record.moves[:self.BOOK_PLIES], 1):
            key = self._book_key(board)
            move = _record_move(board, text, ply)
            if key in book["positions"] or len(book["positions"]) < self.BOOK_POSITIONS:
                stats = book["positions"].setdefault(key, {}).setdefault(text,
                            {"wins": 0, "draws": 0, "losses": 0, "unfinished": 0})
                if record.result == "*":
                    label = "unfinished"
                elif record.result == "1/2-1/2":
                    label = "draws"
                else:
                    winner = WHITE if record.result == "1-0" else BLACK
                    label = "wins" if board.side == winner else "losses"
                stats[label] += 1
            board.make_move(move)
        book["games"] += 1

    def opening_stats(self) -> dict:
        """Return JSON data; recover a missing/corrupt derived book from archives."""
        with self._lock:
            path = os.path.join(self.data_dir, "openings.json")
            book = self._read_json(path, None, self._book_ok)
            if book is not None:
                return book
            book = {"version": 1, "games": 0, "positions": {}}
            for entry in self.history():
                self._learn(book, GameRecord(entry["start_fen"], entry["moves"], entry["headers"],
                                            entry["result"], entry["termination"]))
            return book

    def choose_book_move(self, board: Board):
        """Choose a legal learned move using smoothed, result-weighted counts.

        No built-in repertoire or claim of optimality: only completed archived
        games contribute evidence. Sparse data is deliberately smoothed.
        """
        choices = self.opening_stats()["positions"].get(self._book_key(board), {})
        candidates = []
        for move in board.legal_moves():
            uci = board.uci(move)
            stats = choices.get(uci)
            if not stats:
                continue
            finished = stats["wins"] + stats["draws"] + stats["losses"]
            if finished:
                score = (stats["wins"] + 0.5 * stats["draws"] + 1) / (finished + 2)
                candidates.append((score, finished, uci, move))
        return max(candidates)[-1] if candidates else None
