import time
from collections import defaultdict, deque
from threading import Lock


class LoginRateLimiter:
    """In-memory sliding window of failed logins per client IP and per account.

    Single-process only: counters reset on restart and are not shared between
    workers. Good enough to slow down password guessing on one instance.
    """

    def __init__(self, max_failures: int, window_seconds: int, clock=time.monotonic):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        attempts = self._failures[key]
        while attempts and now - attempts[0] >= self.window_seconds:
            attempts.popleft()
        if not attempts:
            self._failures.pop(key, None)
        return attempts

    def retry_after(self, *keys: str) -> int:
        """Seconds until the caller may try again, or 0 if not blocked."""
        now = self._clock()
        with self._lock:
            wait = 0.0
            for key in keys:
                attempts = self._prune(key, now)
                if len(attempts) >= self.max_failures:
                    wait = max(wait, attempts[0] + self.window_seconds - now)
            return int(wait) + 1 if wait > 0 else 0

    def record_failure(self, *keys: str) -> None:
        now = self._clock()
        with self._lock:
            for key in keys:
                self._prune(key, now)
                self._failures[key].append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()
