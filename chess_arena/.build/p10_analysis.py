
# ==========================================================================
#  BOUNDED POST-GAME ANALYSIS (HEURISTIC, NOT A CALIBRATED RATING MODEL)
# ==========================================================================
def _analysis_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise SearchTimeout("Game analysis cancelled")


class _AnalysisSearcher(Searcher):
    """Check cancellation at search nodes, without a monitoring thread."""

    def __init__(self, cancel):
        super().__init__(Evaluator("balanced"), TranspositionTable())
        self._analysis_event = cancel

    def _check_time(self):
        _analysis_cancel(self._analysis_event)
        super()._check_time()


def _analysis_search(searcher, board, depth, seconds, cancel):
    _analysis_cancel(cancel)
    legal = board.legal_moves()
    if not legal:
        return {"score": -MATE if board.in_check() else 0, "depth": 0,
                "best_move": None, "nodes": 0, "exact": True}
    if board.insufficient_material() or board.half >= 100 or board.rep.get(board.key(), 0) >= 3:
        return {"score": 0, "depth": 0, "best_move": legal[0], "nodes": 0, "exact": True}
    # Never let a timed-out/cancelled search mutate the replay board. The
    # engine's scores are side-to-move scores, including at Black positions.
    snapshot = board.clone()
    manager = TimeManager(max(3600.0, seconds * 100), 0, 30, seconds, seconds)
    info = searcher.search(snapshot, depth, manager)
    # Searcher normally catches its own timeouts; cancellation must propagate.
    _analysis_cancel(cancel)
    best = info.best_move if info.best_move in legal else None
    return {"score": int(info.score), "depth": int(info.depth), "best_move": best,
            "nodes": int(info.nodes), "exact": False}


def _analysis_phase(board):
    material_phase = sum(PHASE_WEIGHT[kind_of(piece)] for square, piece in enumerate(board.sq)
                         if not square & 0x88 and piece)
    if material_phase <= 8:
        return "endgame"
    if board.full <= 10 and material_phase >= 20:
        return "opening"
    return "middlegame"


def _analysis_grade(loss, played_best, before, after, reliable):
    if not reliable:
        return "unrated"
    if played_best:
        return "best"
    # A non-mating continuation under shallow search is not proof that a
    # longer mate no longer exists, so explicitly qualify missed-mate labels.
    if before > MATE_BOUND and after <= MATE_BOUND:
        return "possible missed mate"
    if after < -MATE_BOUND and before >= -MATE_BOUND:
        return "allows mate"
    if loss is None:
        return "mate line"
    if loss <= 20:
        return "excellent"
    if loss <= 60:
        return "good"
    if loss <= 120:
        return "inaccuracy"
    if loss <= 250:
        return "mistake"
    return "blunder"


def _analysis_hint(grade, best, phase, in_check):
    if grade == "unrated":
        return "No completed search at this budget; increase analysis time before judging this move."
    if grade == "possible missed mate":
        return ("The engine found a mating line with %s, but not after the played move. "
                "This is a search-limited warning, not proof that every longer mate was lost." % best)
    if grade == "allows mate":
        return "The searched continuation permits forced mate; compare the defensive alternative %s." % best
    if grade == "mate line":
        return "A mating score is not a centipawn value; compare the forcing lines rather than material."
    if grade == "best":
        return "Matches the engine's choice at this search budget; deeper analysis may choose differently."
    if grade in ("excellent", "good"):
        return "Close to the engine's estimate; compare %s to understand the alternative plan." % best
    if in_check:
        return "Compare all legal check evasions, starting with %s, before committing to a defense." % best
    if phase == "opening":
        return "Compare %s; review development, central control and king safety before moving again." % best
    if phase == "endgame":
        return "Compare %s; count pawn races and check king activity before exchanging material." % best
    return "Compare %s and check the opponent's checks, captures and threats." % best


def _analysis_totals(rows):
    losses = [row["loss_cp"] for row in rows if row["loss_cp"] is not None]
    grades = {}
    for row in rows:
        grades[row["grade"]] = grades.get(row["grade"], 0) + 1
    return {"plies": len(rows), "cp_scored_plies": len(losses),
            "mean_loss_cp": round(sum(losses) / len(losses), 1) if losses else None,
            "max_loss_cp": max(losses) if losses else None, "grades": grades}


def analyze_game(record: GameRecord, seconds=0.1, depth=3, cancel=None,
                 on_progress=None) -> dict:
    """Return a JSON-serializable, shallow-engine coaching report.

    ``seconds`` is the per-search budget (the engine may impose a minimum).
    Each ply uses at most two searches: best play before the move, and the
    opponent's best reply afterwards, normally at one less nominal depth.
    Scores after the move are negated back to the mover's perspective before
    computing max(0, best_score - played_score). If the played move is the
    engine choice, its loss is zero by definition. Mate scores are NOT treated
    as enormous centipawn losses. Budget/depth differences can make estimates
    noisy, especially when only one iteration completes.

    A threading.Event cancellation raises SearchTimeout; progress receives
    (completed_plies, total_plies), including an initial (0, total) call.
    Neither an externally calibrated accuracy percentage nor Elo is inferred.
    """
    _analysis_cancel(cancel)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Analysis seconds must be finite and positive")
    if type(depth) is not int or not 1 <= depth <= 64:
        raise ValueError("Analysis depth must be an integer from 1 to 64")
    # Validate the complete mainline before doing expensive analysis. Check
    # cancellation during validation too, including long imported games.
    validator = _record_start(record)
    for ply, text in enumerate(record.moves, 1):
        _analysis_cancel(cancel)
        validator.make_move(_record_move(validator, text, ply))
    board = _record_start(record)
    searcher = _AnalysisSearcher(cancel)
    total, rows = len(record.moves), []
    started = time.monotonic()
    if on_progress is not None:
        on_progress(0, total)
    _analysis_cancel(cancel)
    for ply, uci in enumerate(record.moves, 1):
        _analysis_cancel(cancel)
        move = _record_move(board, uci, ply)
        san, color, fullmove = board.san(move), board.side, board.full
        phase, checked = _analysis_phase(board), board.in_check()
        # History-dependent draw evaluations must not leak across root calls.
        searcher.tt.clear()
        before = _analysis_search(searcher, board, depth, seconds, cancel)
        best_move = before["best_move"]
        best = board.san(best_move) if best_move is not None else "(none)"
        best_uci = board.uci(best_move) if best_move is not None else None
        board.make_move(move)
        # Clearing also prevents a deeper entry from giving a misleadingly
        # optimistic completed-depth label on the shallower played position.
        searcher.tt.clear()
        reply_depth = max(1, min(depth, before["depth"] or depth) - 1)
        after = _analysis_search(searcher, board, reply_depth, seconds, cancel)
        best_score = before["score"]
        played_score = -after["score"]
        played_best = move == best_move
        reliable = ((before["depth"] > 0 or before["exact"])
                    and (after["depth"] > 0 or after["exact"]))
        mate_before = is_mate_score(best_score)
        mate_after = is_mate_score(played_score)
        if not reliable:
            loss = None
        elif played_best:
            loss = 0
        elif mate_before or mate_after:
            loss = None
        else:
            loss = max(0, int(best_score - played_score))
        grade = _analysis_grade(loss, played_best, best_score, played_score, reliable)
        white_sign = 1 if color == WHITE else -1
        rows.append({
            "ply": ply, "fullmove": fullmove, "color": "white" if color == WHITE else "black",
            "uci": uci, "san": san, "best": best, "best_uci": best_uci,
            "loss_cp": loss, "grade": grade,
            "hint": _analysis_hint(grade, best, phase, checked), "phase": phase,
            "score_before_cp": None if mate_before else best_score,
            "score_after_cp": None if mate_after else played_score,
            "score_before_white_cp": None if mate_before else white_sign * best_score,
            "score_after_white_cp": None if mate_after else white_sign * played_score,
            "mate_before": mate_before, "mate_after": mate_after,
            "possible_missed_mate": grade == "possible missed mate",
            "depth_before": before["depth"], "depth_after": after["depth"],
            "nodes": before["nodes"] + after["nodes"],
            "horizon_warning": (not played_best and not before["exact"] and not after["exact"]
                                and before["depth"] != after["depth"] + 1),
        })
        if on_progress is not None:
            on_progress(ply, total)
        _analysis_cancel(cancel)
    summary = _analysis_totals(rows)
    summary["by_color"] = {color: _analysis_totals([row for row in rows if row["color"] == color])
                           for color in ("white", "black")}
    summary["phases"] = {phase: _analysis_totals([row for row in rows if row["phase"] == phase])
                         for phase in ("opening", "middlegame", "endgame")}
    summary["note"] = ("Heuristic centipawn-loss estimates from a small, time-limited engine; "
                       "not calibrated accuracy or Elo. Mate transitions without a finite "
                       "centipawn loss are excluded from averages. Claimable draws follow "
                       "the engine's automatic draw policy.")
    return {"version": 1, "start_fen": record.start_fen, "result": record.result,
            "termination": record.termination, "headers": dict(record.headers),
            "requested_depth": depth, "seconds_per_search": float(seconds),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "score_perspective": "score_before_cp and score_after_cp favor the player making that move; *_white_cp favors White",
            "moves": rows, "summary": summary}
