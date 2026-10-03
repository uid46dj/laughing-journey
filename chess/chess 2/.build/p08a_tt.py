
# ==========================================================================
#  TRANSPOSITION TABLE
# ==========================================================================
TT_EXACT, TT_LOWER, TT_UPPER = 0, 1, 2
TT_BUCKET_BITS = 16                      # 65 536 buckets
TT_MASK = (1 << TT_BUCKET_BITS) - 1


class TTEntry:
    """One transposition slot (plain class with __slots__ for speed)."""

    __slots__ = ("key", "depth", "score", "flag", "move", "age")

    def __init__(self, key=0, depth=-1, score=0, flag=TT_EXACT, move=None, age=0):
        self.key = key
        self.depth = depth
        self.score = score
        self.flag = flag
        self.move = move
        self.age = age


class TranspositionTable:
    """Fixed-capacity table with bucket replacement (fast + bounded memory)."""

    def __init__(self, max_mb: int = 48):
        self.entries = {}
        self.order = 0
        self.hits = 0
        self.misses = 0
        self.enabled = True
        self.max_mb = max_mb
        self._limit = max(4096, max_mb * 1024)

    def clear(self) -> None:
        self.entries.clear()
        self.order = 0
        self.hits = 0
        self.misses = 0

    def resize(self, max_mb: int) -> None:
        self.max_mb = max_mb
        self._limit = max(4096, max_mb * 1024)
        self.clear()

    def store(self, key: int, depth: int, score: int, flag: int, move) -> None:
        if not self.enabled:
            return
        self.order += 1
        slot = key & TT_MASK
        current = self.entries.get(slot)
        if current is not None and current.key == key and \
                current.depth > depth + 2 and self.order - current.age < 16:
            return
        self.entries[slot] = TTEntry(key, depth, score, flag, move, self.order)
        if len(self.entries) > self._limit:
            self._evict()

    def _evict(self) -> None:
        victims = sorted(self.entries.items(), key=lambda kv: kv[1].age)
        for slot, _ in victims[:max(1, len(self.entries) // 4)]:
            del self.entries[slot]

    def probe(self, key: int, depth: int):
        """Return (flag, entry); flag is None when the entry is too shallow."""
        entry = self.entries.get(key & TT_MASK) if self.enabled else None
        if entry is None or entry.key != key:
            self.misses += 1
            return None, None
        self.hits += 1
        if entry.depth >= depth:
            return entry.flag, entry
        return None, entry

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"entries": len(self.entries), "limit": self._limit,
                "hits": self.hits, "misses": self.misses,
                "hit_rate": (100.0 * self.hits / total) if total else 0.0}


class TimeManager:
    """Turns a clock position into a wall-clock deadline for a single search."""

    def __init__(self, time_left: float, increment: float, moves_left: int,
                 base: float, cap: float):
        time_left = max(0.0, time_left)
        self.time_left = time_left
        self.increment = increment
        self.moves_left = max(1, moves_left)
        self.base = base
        budget = max(0.0, min(cap, base, time_left * 0.45 + increment * 0.8))
        now = time.monotonic()
        self.deadline = now + budget
        self.soft_deadline = self.deadline

    def expired(self, hard: bool = False) -> bool:
        return time.monotonic() >= (self.soft_deadline if hard else self.deadline)

    def remaining(self) -> float:
        return max(0.0, self.soft_deadline - time.monotonic())


@dataclass
class SearchInfo:
    """Snapshot of engine progress (consumed by the GUI and the analyser)."""
    depth: int = 0
    seldepth: int = 0
    score: int = 0
    nodes: int = 0
    time: float = 0.0
    pv: list = field(default_factory=list)
    best_move: object = None
    mate_in: int = 0
    completed: bool = False

    def score_text(self) -> str:
        if is_mate_score(self.score):
            return '#%s%d' % ('-' if self.score < 0 else '', abs(self.mate_in))
        return "%+.2f" % (self.score / 100.0)
