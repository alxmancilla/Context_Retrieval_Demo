from threading import Lock


class MemoryMetrics:
    """Content-free process counters for memory and context behavior."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.write_candidates = 0
        self.write_accepted = 0
        self.write_rejected = 0
        self.created = 0
        self.reinforced = 0
        self.merged = 0
        self.suppressed_deleted = 0
        self.retrieval_requests = 0
        self.retrieval_hits = 0
        self.context_messages = 0
        self.context_chars = 0
        self.context_compacted = 0

    def record_decision(self, accepted: bool) -> None:
        with self._lock:
            self.write_candidates += 1
            self.write_accepted += int(accepted)
            self.write_rejected += int(not accepted)

    def record_outcome(self, outcome: str) -> None:
        with self._lock:
            if outcome == "created":
                self.created += 1
            elif outcome == "reinforced":
                self.reinforced += 1
            elif outcome == "merged":
                self.merged += 1
            elif outcome == "suppressed_deleted":
                self.suppressed_deleted += 1

    def record_retrieval(self, hits: int) -> None:
        with self._lock:
            self.retrieval_requests += 1
            self.retrieval_hits += hits

    def record_context(self, messages: int, chars: int = 0, compacted: int = 0) -> None:
        with self._lock:
            self.context_messages += messages
            self.context_chars += chars
            self.context_compacted += compacted

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "write_candidates": self.write_candidates,
                "write_accepted": self.write_accepted,
                "write_rejected": self.write_rejected,
                "created": self.created,
                "reinforced": self.reinforced,
                "merged": self.merged,
                "suppressed_deleted": self.suppressed_deleted,
                "retrieval_requests": self.retrieval_requests,
                "retrieval_hits": self.retrieval_hits,
                "context_messages": self.context_messages,
                "context_chars": self.context_chars,
                "context_compacted": self.context_compacted,
            }