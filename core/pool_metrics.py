from threading import Lock
from typing import Any

from pymongo.monitoring import ConnectionPoolListener


class PoolMetrics(ConnectionPoolListener):
    """Content-free MongoDB pool counters suitable for readiness/metrics export."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.checkout_started = 0
        self.checkout_succeeded = 0
        self.checkout_failed = 0
        self.checked_out = 0
        self.max_checked_out = 0

    def connection_check_out_started(self, _event: Any) -> None:
        with self._lock:
            self.checkout_started += 1

    def connection_checked_out(self, _event: Any) -> None:
        with self._lock:
            self.checkout_succeeded += 1
            self.checked_out += 1
            self.max_checked_out = max(self.max_checked_out, self.checked_out)

    def connection_check_out_failed(self, _event: Any) -> None:
        with self._lock:
            self.checkout_failed += 1

    def connection_checked_in(self, _event: Any) -> None:
        with self._lock:
            self.checked_out = max(self.checked_out - 1, 0)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "checkout_started": self.checkout_started,
                "checkout_succeeded": self.checkout_succeeded,
                "checkout_failed": self.checkout_failed,
                "checked_out": self.checked_out,
                "max_checked_out": self.max_checked_out,
            }

    def pool_created(self, _event: Any) -> None:
        pass

    def pool_ready(self, _event: Any) -> None:
        pass

    def pool_cleared(self, _event: Any) -> None:
        pass

    def pool_closed(self, _event: Any) -> None:
        pass

    def connection_created(self, _event: Any) -> None:
        pass

    def connection_ready(self, _event: Any) -> None:
        pass

    def connection_closed(self, _event: Any) -> None:
        pass