
# ==========================================================================
#  TK INTERFACE - Tk is deliberately imported only when a GUI is requested.
# ==========================================================================
class _GUIBudget(TimeManager):
    """The cancellation event also covers stop-before-search-start races."""

    def __init__(self, seconds, cancel):
        super().__init__(3600.0, 0.0, 30, seconds, seconds)
        self.cancel = cancel

    def expired(self, hard=False):
        return self.cancel.is_set() or super().expired(hard)


class ChessApp:
    """Tk application. Construct on the Tk thread as ChessApp(root, store).

    All widgets, variables and the live board belong exclusively to that
    thread. Workers receive detached records/boards and communicate through a
    queue. Undo rewinds one ply and pauses; imported games open paused without
    clocks. Strength names describe search budgets, not calibrated Elo ratings.
    """

    MODES = ("Human vs AI", "AI vs AI", "Human vs Human")
    STRENGTHS = {"Quick": (1, 0.06), "Casual": (2, 0.20),
                 "Club": (3, 0.65), "Strong": (5, 2.0)}
    CLOCKS = {"No clock": (0, 0), "1 + 0": (60, 0),
              "3 + 2": (180, 2), "5 + 0": (300, 0),
              "10 + 5": (600, 5), "15 + 10": (900, 10)}
    GLYPHS = {PAWN: "\u265f", KNIGHT: "\u265e", BISHOP: "\u265d",
              ROOK: "\u265c", QUEEN: "\u265b", KING: "\u265a"}

    def __init__(self, root, store):
        import queue
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox

        self.root, self.store = root, store
        self.tk, self.ttk = tk, ttk
        self.filedialog, self.messagebox = filedialog, messagebox
        self._events = queue.Queue()
        self._queue_empty = queue.Empty
        self._generation = 0
        self._worker = None
        self._searcher = None
        self._cancel = threading.Event()
        self._job = None
        self._pending_analysis = None
        self._after_id = None
        self._closed = False
        self._promotion_window = None
        self._selected = None
        self._drag_from = None
        self._press_consumed = False
        self._archived_signature = None
        self._archives = {}
        self.report = None
        self.paused = False
        self.flipped = False
        self.board = Board()
        self.record = GameRecord()
        self._sans = []
        self._clock_history = []
        self._clocks = [0.0, 0.0]
        self._clock_enabled = False
        self._increment = 0
        self._last_tick = time.monotonic()
        try:
            profile = store.load_profile()
            self._profile = profile if isinstance(profile, dict) else {}
        except Exception as exc:
            self._profile = {}
            print("Chess Arena: profile could not be loaded: %s" % exc, file=sys.stderr)
        settings = self._profile.get("gui", {})
        if not isinstance(settings, dict):
            settings = {}
        self.styles = tuple(globals().get("STYLE_WEIGHTS", globals().get(
            "STYLES", {"balanced": ()})))

        def choice(key, options, default):
            value = settings.get(key, default)
            return tk.StringVar(root, value=value if value in options else default)

        self.mode_var = choice("mode", self.MODES, self.MODES[0])
        self.human_color_var = choice("human_color", ("White", "Black"), "White")
        self.style_var = choice("white_style", self.styles, "balanced")
        self.black_style_var = choice("black_style", self.styles, "balanced")
        self.strength_var = choice("strength", self.STRENGTHS, "Casual")
        self.time_control_var = choice("clock", self.CLOCKS, "No clock")
        self.status_var = tk.StringVar(root, value="Ready")
        self.engine_var = tk.StringVar(root, value="Engine idle")
        self.eval_var = tk.StringVar(root, value="White +0.00 (static)")
        self.clock_vars = [tk.StringVar(root), tk.StringVar(root)]
        self.pause_var = tk.StringVar(root, value="Pause")
        self.flipped = bool(settings.get("flipped", False))
        self._build_ui()
        self.new_game()
        self.refresh_history()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._after_id = self.root.after(40, self._pump)

    def _build_ui(self):
        tk, ttk, root = self.tk, self.ttk, self.root
        root.title("Chess Arena")
        root.geometry("1120x780")
        root.minsize(840, 610)
        outer = ttk.Frame(root, padding=8)
        outer.pack(fill="both", expand=True)
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(0, 6))
        for text, command in (("New / Reset", lambda: self.new_game(confirm=True)),
                              ("Undo ply", self.undo),
                              ("Flip board", self.flip_board),
                              ("Open PGN", self.open_pgn),
                              ("Save PGN", self.save_pgn),
                              ("Archive", self.archive_game)):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=2)
        ttk.Button(bar, textvariable=self.pause_var,
                   command=self.toggle_pause).pack(side="left", padx=2)

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 5))
        self._combo(controls, "Mode", self.mode_var, self.MODES, 17, self._mode_changed)
        self._combo(controls, "Human", self.human_color_var,
                    ("White", "Black"), 7, self._mode_changed)
        self._combo(controls, "Strength", self.strength_var,
                    tuple(self.STRENGTHS), 9, self._engine_settings_changed)
        self._combo(controls, "Clock (new game)", self.time_control_var,
                    tuple(self.CLOCKS), 10)
        styles = ttk.Frame(outer)
        styles.pack(fill="x", pady=(0, 7))
        self._combo(styles, "White AI style", self.style_var,
                    self.styles, 12, self._engine_settings_changed)
        self._combo(styles, "Black AI style", self.black_style_var,
                    self.styles, 12, self._engine_settings_changed)
        ttk.Label(styles, text="Strength is a search budget, not an Elo rating.").pack(
            side="left", padx=12)

        body = ttk.Panedwindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True)
        left, right = ttk.Frame(body), ttk.Frame(body, width=390)
        body.add(left, weight=3)
        body.add(right, weight=2)
        clocks = ttk.Frame(left)
        clocks.pack(fill="x")
        for color in (WHITE, BLACK):
            ttk.Label(clocks, textvariable=self.clock_vars[color],
                      font=("TkDefaultFont", 14, "bold")).pack(
                          side="left" if color == WHITE else "right", padx=10, pady=5)
        self.canvas = tk.Canvas(left, width=540, height=540, background="#23313c",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw_board())
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        ttk.Label(left, text="Click two squares or drag a piece. Dots mark legal moves.").pack(
            pady=(6, 2))
        ttk.Label(left, textvariable=self.eval_var).pack()
        self.eval_bar = ttk.Progressbar(left, maximum=100, value=50)
        self.eval_bar.pack(fill="x", padx=15, pady=3)
        ttk.Label(left, textvariable=self.engine_var, wraplength=530,
                  justify="left").pack(fill="x", padx=8, pady=5)

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True, padx=(8, 0))
        moves_tab = ttk.Frame(self.notebook, padding=5)
        self.analysis_tab = ttk.Frame(self.notebook, padding=5)
        history_tab = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(moves_tab, text="Moves")
        self.notebook.add(self.analysis_tab, text="Analysis")
        self.notebook.add(history_tab, text="Archive")
        self.moves_tree = self._tree(moves_tab, ("ply", "side", "san"),
                                    ("Ply", "Side", "Move"), (45, 65, 120))
        ttk.Label(moves_tab, text="Undo takes back one ply and pauses the game.",
                  wraplength=340).pack(fill="x", pady=5)
        analysis_bar = ttk.Frame(self.analysis_tab)
        analysis_bar.pack(fill="x", pady=(0, 6))
        ttk.Button(analysis_bar, text="Analyze game", command=self.start_analysis).pack(
            side="left")
        ttk.Button(analysis_bar, text="Cancel", command=self.cancel_analysis).pack(
            side="left", padx=3)
        ttk.Button(analysis_bar, text="Export JSON", command=self.export_report).pack(
            side="left")
        self.analysis_tree = self._tree(
            self.analysis_tab, ("ply", "san", "best", "loss", "grade"),
            ("Ply", "Move", "Best", "Loss cp", "Grade"), (35, 65, 70, 60, 80))
        self.analysis_tree.bind("<<TreeviewSelect>>", self._analysis_selected)
        self.report_text = tk.Text(self.analysis_tab, height=10, width=36,
                                   wrap="word", state="disabled")
        self.report_text.pack(fill="x", pady=(6, 0))
        history_bar = ttk.Frame(history_tab)
        history_bar.pack(fill="x", pady=(0, 6))
        ttk.Button(history_bar, text="Refresh", command=self.refresh_history).pack(side="left")
        ttk.Button(history_bar, text="Load selected", command=self.load_archive).pack(
            side="left", padx=5)
        self.history_tree = self._tree(history_tab, ("game", "result", "plies"),
                                      ("Game", "Result", "Plies"), (200, 70, 45))
        self.history_tree.bind("<Double-1>", lambda _event: self.load_archive())
        ttk.Label(outer, textvariable=self.status_var, anchor="w", wraplength=1050).pack(
            fill="x", pady=(7, 0))

    def _combo(self, parent, text, variable, values, width, callback=None):
        self.ttk.Label(parent, text=text).pack(side="left", padx=(4, 3))
        widget = self.ttk.Combobox(parent, textvariable=variable, values=values,
                                   state="readonly", width=width)
        widget.pack(side="left", padx=(0, 7))
        if callback:
            widget.bind("<<ComboboxSelected>>", callback)
        return widget

    def _tree(self, parent, columns, headings, widths):
        frame = self.ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = self.ttk.Treeview(frame, columns=columns, show="headings",
                                 selectmode="browse", height=12)
        scroll = self.ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        for column, heading, width in zip(columns, headings, widths):
            tree.heading(column, text=heading)
            tree.column(column, width=width, minwidth=30, stretch=True)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return tree

    @staticmethod
    def _copy_record(record):
        return GameRecord(start_fen=record.start_fen, moves=list(record.moves),
                          headers=dict(record.headers), result=record.result,
                          termination=record.termination)

    def _cancel_work(self):
        self._generation += 1
        self._cancel.set()
        if self._searcher is not None:
            self._searcher.stop()
        self._searcher = None
        self._job = None
        self._pending_analysis = None
        # A retiring worker is not joined on the Tk thread. No replacement is
        # launched until it exits, so repeated resets cannot accumulate workers.
        if self._promotion_window is not None:
            self._promotion_window.destroy()
            self._promotion_window = None

    def _confirm_replace(self):
        return not self.record.moves or self.messagebox.askyesno(
            "Replace game?", "Replace the current game? Save PGN or Archive first to keep it.",
            parent=self.root)

    def new_game(self, confirm=False):
        if confirm and not self._confirm_replace():
            return False
        self._cancel_work()
        self.board = Board()
        mode = self.mode_var.get()
        human = WHITE if self.human_color_var.get() == "White" else BLACK
        names = []
        for color in (WHITE, BLACK):
            is_human = mode == "Human vs Human" or (mode == "Human vs AI" and color == human)
            names.append("Human" if is_human else "Chess Arena")
        self.record = GameRecord(headers={"Event": "Chess Arena", "White": names[WHITE],
                                          "Black": names[BLACK],
                                          "Date": datetime.now().strftime("%Y.%m.%d")})
        self._sans, self._clock_history = [], []
        seconds, self._increment = self.CLOCKS.get(self.time_control_var.get(), (0, 0))
        self._clocks = [float(seconds), float(seconds)]
        self._clock_enabled = seconds > 0
        self._last_tick = time.monotonic()
        self.paused = False
        self._archived_signature = None
        self._selected = self._drag_from = None
        self._clear_report()
        self.engine_var.set("Engine idle")
        self._refresh()
        return True

    def load_record(self, record):
        """Replace the game with a validated detached record, initially paused."""
        candidate = self._copy_record(record)
        board = candidate.replay()
        replay, sans = Board(candidate.start_fen), []
        for text in candidate.moves:
            move = replay.find_move(text)
            if move is None:
                raise ValueError("Illegal move in game: " + text)
            sans.append(replay.san(move))
            replay.make_move(move)
        self._cancel_work()
        self.record, self.board, self._sans = candidate, board, sans
        outcome = board.outcome()
        if candidate.result == "*" and outcome["result"] != "*":
            candidate.result, candidate.termination = outcome["result"], outcome["termination"]
        self.paused = True
        self._clock_enabled = False
        self._clocks = [0.0, 0.0]
        self._clock_history = [None] * len(candidate.moves)
        self._last_tick = time.monotonic()
        self._selected = self._drag_from = None
        self._archived_signature = None
        self._clear_report()
        self.engine_var.set("Imported game; clocks disabled")
        self._refresh()

    def _is_human(self, color):
        mode = self.mode_var.get()
        return mode == "Human vs Human" or (mode == "Human vs AI" and
            color == (WHITE if self.human_color_var.get() == "White" else BLACK))

    def _can_human_move(self):
        return (not self._closed and not self.paused and self.record.result == "*"
                and self._is_human(self.board.side) and self._job != "analysis")

    def play_move(self, move):
        """Play a legal human move (UCI/SAN or move tuple); return success."""
        if not self._can_human_move():
            return False
        if isinstance(move, str):
            move = self.board.find_move(move)
        if move not in self.board.legal_moves():
            return False
        return self._commit_move(move)

    def _commit_move(self, move):
        self._tick_clock()
        if self._closed or self.paused or self.record.result != "*":
            return False
        if move not in self.board.legal_moves():
            return False
        san, uci, side = self.board.san(move), self.board.uci(move), self.board.side
        self._clock_history.append(list(self._clocks) if self._clock_enabled else None)
        self._cancel_work()
        self.board.make_move(move)
        self.record.moves.append(uci)
        self._sans.append(san)
        if self._clock_enabled:
            self._clocks[side] += self._increment
        self._last_tick = time.monotonic()
        self._selected = self._drag_from = None
        self._clear_report()
        outcome = self.board.outcome()
        self.record.result, self.record.termination = outcome["result"], outcome["termination"]
        self._refresh()
        if self.record.result != "*":
            self.archive_game(automatic=True)
        return True

    def undo(self):
        self._tick_clock()
        self._cancel_work()
        self.paused = True
        if self.record.moves:
            self.record.moves.pop()
            self._sans.pop()
            previous_clock = self._clock_history.pop()
            if previous_clock is not None:
                self._clocks = previous_clock
            # Replaying also works with Board.clone(), whose undo stack is empty.
            self.record.result = self.record.termination = "*"
            self.record.headers.pop("Result", None)
            self.record.headers.pop("Termination", None)
            self.board = self.record.replay()
        self._last_tick = time.monotonic()
        self._selected = self._drag_from = None
        self._clear_report()
        self.engine_var.set("Undo: paused; Resume to continue")
        self._refresh()

    def toggle_pause(self):
        self._tick_clock()
        self._cancel_work()
        self.paused = not self.paused
        self._last_tick = time.monotonic()
        self._selected = self._drag_from = None
        self.engine_var.set("Paused" if self.paused else "Engine idle")
        self._refresh()

    def _mode_changed(self, _event=None):
        self._tick_clock()
        self._cancel_work()
        self.paused = True
        self._selected = self._drag_from = None
        self.engine_var.set("Mode changed; Resume or New / Reset to play")
        self._refresh()

    def _engine_settings_changed(self, _event=None):
        self._tick_clock()
        self._cancel_work()
        self.engine_var.set("Engine settings updated")
        self._refresh()

    def flip_board(self):
        self.flipped = not self.flipped
        self._drag_from = None
        self._draw_board()

    def _board_geometry(self):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        size = max(8.0, (min(width, height) - 36) / 8)
        return size, (width - size * 8) / 2, (height - size * 8) / 2

    def _square_center(self, square):
        size, left, top = self._board_geometry()
        file_index, rank = file_of(square), rank_of(square)
        column, row = (7 - file_index, rank) if self.flipped else (file_index, 7 - rank)
        return left + (column + 0.5) * size, top + (row + 0.5) * size

    def _event_square(self, event):
        size, left, top = self._board_geometry()
        column, row = int((event.x - left) // size), int((event.y - top) // size)
        if not (0 <= column < 8 and 0 <= row < 8):
            return None
        return square_of(7 - column, row) if self.flipped else square_of(column, 7 - row)

    def _draw_board(self):
        if self._closed:
            return
        canvas = self.canvas
        canvas.delete("all")
        size, left, top = self._board_geometry()
        last = set()
        if self.record.moves:
            uci = self.record.moves[-1]
            last = {parse_square(uci[:2]), parse_square(uci[2:4])}
        targets = {m[1] for m in self.board.legal_moves() if m[0] == self._selected}
        checked_king = self.board.kings[self.board.side] if self.board.in_check() else None
        for rank in range(8):
            for file_index in range(8):
                square = square_of(file_index, rank)
                x, y = self._square_center(square)
                light = (rank + file_index) % 2 != 0
                color = "#e9e3d2" if light else "#789486"
                if square in last:
                    color = "#e0cf7d" if light else "#b7b367"
                canvas.create_rectangle(x - size/2, y - size/2, x + size/2, y + size/2,
                                        fill=color, outline=color)
                if square == self._selected or square == checked_king:
                    canvas.create_rectangle(x - size/2 + 2, y - size/2 + 2,
                                            x + size/2 - 2, y + size/2 - 2,
                                            outline="#d45550" if square == checked_king else "#217fc0",
                                            width=3)
                piece = self.board.sq[square]
                if square in targets:
                    radius = size * (0.40 if piece else 0.095)
                    canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                       fill="" if piece else "#426858", outline="#426858", width=3)
                if piece:
                    tag = "piece_%d" % square
                    glyph = self.GLYPHS[kind_of(piece)]
                    font = ("DejaVu Sans", max(10, int(size * 0.64)))
                    if color_of(piece) == WHITE:
                        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                            canvas.create_text(x+dx, y+dy, text=glyph, font=font,
                                               fill="#26343a", tags=tag)
                    canvas.create_text(x, y, text=glyph, font=font,
                                       fill="#fffaf0" if color_of(piece) == WHITE else "#18262f",
                                       tags=tag)
        for i in range(8):
            canvas.create_text(left+(i+0.5)*size, top+8*size+11,
                               text=FILES[7-i if self.flipped else i], fill="#e8eced")
            canvas.create_text(left-11, top+(i+0.5)*size,
                               text=str(i+1 if self.flipped else 8-i), fill="#e8eced")

    def _on_press(self, event):
        self._press_consumed = False
        if not self._can_human_move():
            return
        square = self._event_square(event)
        if square is None:
            self._selected = None
            self._draw_board()
            return
        if self._selected is not None and square != self._selected:
            if self._try_move(self._selected, square):
                self._press_consumed = True
                return
        piece = self.board.sq[square]
        if piece and color_of(piece) == self.board.side:
            self._selected = self._drag_from = square
            self._drag_xy = (event.x, event.y)
        else:
            self._selected = self._drag_from = None
        self._draw_board()

    def _on_drag(self, event):
        if self._drag_from is None or not self._can_human_move():
            return
        x, y = self._drag_xy
        tag = "piece_%d" % self._drag_from
        self.canvas.move(tag, event.x-x, event.y-y)
        self.canvas.tag_raise(tag)
        self._drag_xy = (event.x, event.y)

    def _on_release(self, event):
        if self._press_consumed:
            self._press_consumed = False
            return
        source, target = self._drag_from, self._event_square(event)
        self._drag_from = None
        if source is not None and target is not None and source != target:
            self._try_move(source, target)
        self._draw_board()

    def _try_move(self, source, target):
        if not self._can_human_move():
            return False
        moves = [move for move in self.board.legal_moves()
                 if move[0] == source and move[1] == target]
        if not moves:
            return False
        generation = self._generation
        if len(moves) > 1:
            promotion = self._choose_promotion()
            moves = [move for move in moves if move[2] == promotion]
        if not moves or self._closed or generation != self._generation:
            return False
        return self.play_move(moves[0])

    def _choose_promotion(self):
        window = self.tk.Toplevel(self.root)
        self._promotion_window = window
        window.title("Promote pawn")
        window.transient(self.root)
        window.resizable(False, False)
        answer = []
        self.ttk.Label(window, text="Choose a promotion piece:", padding=12).pack()
        buttons = self.ttk.Frame(window, padding=10)
        buttons.pack()

        def choose(piece):
            answer.append(piece)
            window.destroy()

        for piece in (QUEEN, ROOK, BISHOP, KNIGHT):
            self.ttk.Button(buttons, text=PIECE_NAMES[piece].title(),
                            command=lambda p=piece: choose(p)).pack(side="left", padx=3)
        window.bind("<Escape>", lambda _event: window.destroy())
        window.grab_set()
        self.root.wait_window(window)
        self._promotion_window = None
        return answer[0] if answer else None

    def _tick_clock(self):
        now = time.monotonic()
        elapsed, self._last_tick = max(0.0, now-self._last_tick), now
        if self._clock_enabled and not self.paused and self.record.result == "*":
            side = self.board.side
            self._clocks[side] = max(0.0, self._clocks[side]-elapsed)
            if self._clocks[side] <= 0:
                self.record.result = "0-1" if side == WHITE else "1-0"
                self.record.termination = "time forfeit"
                self._cancel_work()
                self._refresh()
                self.archive_game(automatic=True)
        self._update_clocks()

    def _update_clocks(self):
        for color, name in ((WHITE, "White"), (BLACK, "Black")):
            seconds = max(0, int(math.ceil(self._clocks[color])))
            clock = "%d:%02d" % divmod(seconds, 60) if self._clock_enabled else "--:--"
            marker = " >" if self.board.side == color and self.record.result == "*" else ""
            self.clock_vars[color].set("%s%s   %s" % (name, marker, clock))

    def _refresh(self):
        self.pause_var.set("Resume" if self.paused else "Pause")
        self._update_clocks()
        side = "White" if self.board.side == WHITE else "Black"
        if self.record.result != "*":
            status = "%s — %s" % (self.record.result, self.record.termination)
        else:
            status = "%s to move%s%s" % (side, " — check" if self.board.in_check() else "",
                                         " — paused" if self.paused else "")
        self.status_var.set(status)
        self.moves_tree.delete(*self.moves_tree.get_children())
        first_side = Board(self.record.start_fen).side
        for index, san in enumerate(self._sans):
            self.moves_tree.insert("", "end", iid=str(index), values=(index+1,
                "White" if (first_side+index) % 2 == WHITE else "Black", san))
        if self._sans:
            self.moves_tree.see(str(len(self._sans)-1))
        score = Evaluator().evaluate(self.board)
        self._show_eval(score if self.board.side == WHITE else -score, "static")
        self._draw_board()

    def _show_eval(self, score, label):
        if is_mate_score(score):
            text = "%s has a forced mate" % ("White" if score > 0 else "Black")
        else:
            text = "White %+.2f" % (score/100.0)
        self.eval_var.set("%s (%s)" % (text, label))
        self.eval_bar["value"] = 50 + 50 * math.tanh(score/600.0)

    # Worker functions intentionally have no app, root, widget or Tk variable.
    @staticmethod
    def _search_worker(events, generation, board, searcher, cancel, depth, seconds):
        side = board.side

        def snapshot(info):
            return {"side": side, "score": info.score, "depth": info.depth,
                    "nodes": info.nodes, "time": info.time,
                    "best_move": info.best_move,
                    "pv": " ".join(board.uci(move) for move in list(info.pv))}

        def update(info):
            if cancel.is_set():
                searcher.stop()
                raise SearchTimeout()
            events.put((generation, "engine_update", snapshot(info)))

        try:
            if cancel.is_set():
                return
            info = searcher.search(board, depth, _GUIBudget(seconds, cancel), on_update=update)
            if not cancel.is_set():
                events.put((generation, "engine_done", snapshot(info)))
        except SearchTimeout:
            if not cancel.is_set():
                events.put((generation, "error", ("Engine", "Search interrupted")))
        except Exception as exc:
            events.put((generation, "error", ("Engine", "%s: %s" % (type(exc).__name__, exc))))

    @staticmethod
    def _analysis_worker(events, generation, record, cancel, seconds, depth):
        try:
            report = analyze_game(record, seconds=seconds, depth=depth, cancel=cancel,
                                  on_progress=lambda done, total: events.put(
                                      (generation, "analysis_progress", (done, total))))
            if not cancel.is_set():
                events.put((generation, "analysis_done", report))
        except SearchTimeout:
            if not cancel.is_set():
                events.put((generation, "error", ("Analysis", "Analysis interrupted")))
        except Exception as exc:
            events.put((generation, "error", ("Analysis", "%s: %s" % (type(exc).__name__, exc))))

    def _advance_work(self):
        if self._closed or self._job is not None:
            return
        if self._worker is not None and self._worker.is_alive():
            return
        if self._pending_analysis is not None:
            record, seconds, depth = self._pending_analysis
            self._pending_analysis = None
            self._cancel = threading.Event()
            self._job = "analysis"
            self._worker = threading.Thread(target=self._analysis_worker,
                args=(self._events, self._generation, record, self._cancel, seconds, depth),
                name="ChessArena-analysis", daemon=True)
        elif not self.paused and self.record.result == "*" and not self._is_human(self.board.side):
            depth, seconds = self.STRENGTHS.get(self.strength_var.get(), (2, 0.20))
            if self._clock_enabled:
                seconds = min(seconds, max(0.02, self._clocks[self.board.side]/20))
            style = self.style_var.get() if self.board.side == WHITE else self.black_style_var.get()
            self._cancel = threading.Event()
            self._searcher = Searcher(Evaluator(style), TranspositionTable())
            self._job = "engine"
            self.engine_var.set("%s AI thinking…" % ("White" if self.board.side == WHITE else "Black"))
            self._worker = threading.Thread(target=self._search_worker,
                args=(self._events, self._generation, self.board.clone(), self._searcher,
                      self._cancel, depth, seconds), name="ChessArena-search", daemon=True)
        else:
            return
        self._worker.start()

    def _pump(self):
        self._after_id = None
        if self._closed:
            return
        self._tick_clock()
        # Limit work per tick even if a long analysis produced many messages.
        for _ in range(100):
            try:
                generation, kind, payload = self._events.get_nowait()
            except self._queue_empty:
                break
            if generation != self._generation:
                continue
            if kind in ("engine_update", "engine_done"):
                score = payload["score"] if payload["side"] == WHITE else -payload["score"]
                self._show_eval(score, "search depth %d" % payload["depth"])
                self.engine_var.set("Depth %d · %s nodes · %.2f s\nPV: %s" % (
                    payload["depth"], format(payload["nodes"], ","), payload["time"], payload["pv"]))
                if kind == "engine_done":
                    self._job = None
                    if not self.paused and not self._is_human(self.board.side):
                        if not self._commit_move(payload["best_move"]):
                            self.paused = True
                            self._refresh()
                            self.status_var.set("Engine returned no legal move; paused")
                        else:
                            self._show_eval(score, "last search")
            elif kind == "analysis_progress":
                self.engine_var.set("Analyzing game: %d / %d plies" % payload)
            elif kind == "analysis_done":
                self._job = None
                self.report = payload
                self._display_report()
                self.engine_var.set("Analysis complete; game remains paused")
            elif kind == "error":
                self._job = None
                self.paused = True
                self._refresh()
                self.engine_var.set("%s error: %s" % payload)
                self.status_var.set("%s failed; paused. Change settings or Resume to retry." % payload[0])
        self._advance_work()
        if not self._closed:
            self._after_id = self.root.after(40, self._pump)

    def _clear_report(self):
        self.report = None
        self.analysis_tree.delete(*self.analysis_tree.get_children())
        self._set_report_text("Analyze a game to see move grades, alternatives and coaching hints.")

    def _set_report_text(self, text):
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", text)
        self.report_text.configure(state="disabled")

    def start_analysis(self, seconds=0.1, depth=3):
        if not self.record.moves:
            self.status_var.set("Play or import some moves before analyzing a game.")
            return False
        self._tick_clock()
        self._cancel_work()
        self.paused = True
        self._selected = self._drag_from = None
        self._clear_report()
        self._pending_analysis = (self._copy_record(self.record), max(0.02, float(seconds)),
                                  max(1, int(depth)))
        self._refresh()
        self.notebook.select(self.analysis_tab)
        self.engine_var.set("Analysis queued; game paused")
        self._advance_work()
        return True

    def cancel_analysis(self):
        if self._job == "analysis" or self._pending_analysis is not None:
            self._cancel_work()
            self.engine_var.set("Analysis canceled; game remains paused")

    def _display_report(self):
        self.analysis_tree.delete(*self.analysis_tree.get_children())
        for index, row in enumerate(self.report.get("moves", [])):
            self.analysis_tree.insert("", "end", iid=str(index), values=(
                row.get("ply", index+1), row.get("san", ""), row.get("best", ""),
                row.get("loss_cp", ""), row.get("grade", "")))
        self._set_report_text("Summary\n" + json.dumps(self.report.get("summary", {}),
                                                     indent=2, ensure_ascii=False))
        self.notebook.select(self.analysis_tab)

    def _analysis_selected(self, _event=None):
        selected = self.analysis_tree.selection()
        if not selected or not self.report:
            return
        row = self.report.get("moves", [])[int(selected[0])]
        self._set_report_text("Ply %s: %s\nBest: %s\nLoss: %s cp · %s\n\n%s" % (
            row.get("ply", ""), row.get("san", ""), row.get("best", ""),
            row.get("loss_cp", ""), row.get("grade", ""), row.get("hint", "")))

    def open_pgn(self):
        path = self.filedialog.askopenfilename(parent=self.root, title="Open PGN",
            filetypes=(("Chess PGN", "*.pgn"), ("All files", "*")))
        if not path or not self._confirm_replace():
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                text = handle.read(8 * 1024 * 1024 + 1)
            if len(text) > 8 * 1024 * 1024:
                raise ValueError("PGN is too large (maximum 8 MiB)")
            self.load_record(parse_pgn(text))
        except Exception as exc:
            self.messagebox.showerror("Cannot open PGN", str(exc), parent=self.root)

    def save_pgn(self):
        path = self.filedialog.asksaveasfilename(parent=self.root, title="Save PGN",
            defaultextension=".pgn", filetypes=(("Chess PGN", "*.pgn"),))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(export_pgn(self._copy_record(self.record), report=self.report))
            self.status_var.set("PGN saved: " + path)
        except Exception as exc:
            self.messagebox.showerror("Cannot save PGN", str(exc), parent=self.root)

    def export_report(self):
        if self.report is None:
            self.status_var.set("Analyze the current game before exporting its report.")
            return
        path = self.filedialog.asksaveasfilename(parent=self.root, title="Export analysis report",
            defaultextension=".json", filetypes=(("JSON report", "*.json"),))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self.report, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            self.status_var.set("Report saved: " + path)
        except Exception as exc:
            self.messagebox.showerror("Cannot export report", str(exc), parent=self.root)

    def archive_game(self, automatic=False):
        if not self.record.moves:
            return
        signature = (self.record.start_fen, tuple(self.record.moves), self.record.result,
                     self.record.termination)
        if signature == self._archived_signature:
            return
        try:
            identifier = self.store.archive(self._copy_record(self.record))
            self._archived_signature = signature
            self.refresh_history()
            if not automatic:
                self.status_var.set("Game archived: " + str(identifier))
        except Exception as exc:
            self.status_var.set("Could not archive game: " + str(exc))

    def refresh_history(self):
        try:
            entries = self.store.history()
            self.history_tree.delete(*self.history_tree.get_children())
            self._archives = {}
            for index, entry in enumerate(entries):
                headers = entry.get("headers", {})
                label = "%s: %s – %s" % (headers.get("Date", str(entry.get("id", "Game"))),
                                         headers.get("White", "White"), headers.get("Black", "Black"))
                key = str(index)
                self._archives[key] = entry
                self.history_tree.insert("", "end", iid=key, values=(
                    label, entry.get("result", "*"), len(entry.get("moves", []))))
        except Exception as exc:
            self.status_var.set("Could not load archive: " + str(exc))

    def load_archive(self):
        selected = self.history_tree.selection()
        if not selected or not self._confirm_replace():
            return
        try:
            entry = self._archives[selected[0]]
            self.load_record(GameRecord(start_fen=entry.get("start_fen", START_FEN),
                moves=list(entry.get("moves", [])), headers=dict(entry.get("headers", {})),
                result=entry.get("result", "*"), termination=entry.get("termination", "*")))
            self.notebook.select(0)
        except Exception as exc:
            self.messagebox.showerror("Cannot load archived game", str(exc), parent=self.root)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel_work()
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._profile["gui"] = {"mode": self.mode_var.get(),
            "human_color": self.human_color_var.get(), "white_style": self.style_var.get(),
            "black_style": self.black_style_var.get(), "strength": self.strength_var.get(),
            "clock": self.time_control_var.get(), "flipped": self.flipped}
        try:
            self.store.save_profile(self._profile)
        except Exception as exc:
            print("Chess Arena: profile could not be saved: %s" % exc, file=sys.stderr)
        self.root.destroy()


def launch_gui(store=None) -> int:
    """Launch Tk, or report missing Tk/display and return a nonzero exit code."""
    try:
        import tkinter as tk
    except ImportError as exc:
        print("Chess Arena GUI requires tkinter: %s. Headless commands still work." % exc,
              file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print("Chess Arena cannot open a display: %s. Use a headless CLI command instead." % exc,
              file=sys.stderr)
        return 1
    try:
        ChessApp(root, Store() if store is None else store)
        root.mainloop()
    except Exception as exc:
        print("Chess Arena GUI error: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        try:
            root.destroy()
        except tk.TclError:
            pass
        return 1
    return 0
