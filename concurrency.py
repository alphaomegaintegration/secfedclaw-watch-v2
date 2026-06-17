#!/usr/bin/env python3
"""Lightweight concurrency primitives for SECFEDCLAW v0.2 (stdlib only).

Phase 0 of the architecture plan: instead of adopting a workflow engine, the
scan parallelizes its I/O-bound source fetches in-process and adds per-source
rate limiting and retry. These helpers are deliberately small and dependency-
free so the no-third-party-deps footprint (a compliance asset) is preserved.

  - run_concurrent: fan out (name, thunk) work onto a thread pool, returning a
    dict whose key ORDER follows the spec list — never completion order. This
    determinism is what keeps `review_queue.json` byte-stable under concurrency.
  - retry: bounded retry-with-backoff for transient network errors.
  - RateLimiter: thread-safe token bucket; clock/sleep are injectable for tests.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable


def run_concurrent(specs: Iterable[tuple[str, Callable[[], Any]]],
                   max_workers: int = 8) -> dict[str, Any]:
    """Run each thunk concurrently; return {name: result} in SPEC order.

    A thunk that raises propagates: the first failing spec (in declared order)
    re-raises from this call, mirroring the old sequential behavior where the
    first failure aborted the gather.
    """
    specs = list(specs)
    if not specs:
        return {}
    workers = max(1, min(max_workers, len(specs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [(name, pool.submit(thunk)) for name, thunk in specs]
        # Resolve in spec order → deterministic key order and deterministic
        # first-exception, regardless of which thunk finished first.
        return {name: fut.result() for name, fut in futures}


def retry(fn: Callable[[], Any], attempts: int = 3, *, backoff: float = 0.0,
          retry_on: tuple[type[BaseException], ...] = (Exception,),
          sleep: Callable[[float], None] = time.sleep) -> Any:
    """Call fn; on a retry_on exception, retry up to `attempts` total tries.

    backoff is the base delay; the nth retry waits backoff * 2**n (0 = no wait).
    Exceptions not in retry_on propagate immediately (no retry).
    """
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as e:  # type: ignore[misc]
            last = e
            if i < attempts - 1 and backoff > 0:
                sleep(backoff * (2 ** i))
    assert last is not None
    raise last


class RateLimiter:
    """Thread-safe token-bucket rate limiter.

    `now` and `sleep` are injectable so timing behavior is deterministically
    testable. acquire() returns the number of seconds it slept (0.0 if a token
    was immediately available).
    """

    def __init__(self, rate_per_sec: float, burst: int = 1, *,
                 now: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec must be > 0")
        self.rate = float(rate_per_sec)
        self.capacity = float(max(1, burst))
        self._tokens = self.capacity
        self._now = now
        self._sleep = sleep
        self._last = now()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        t = self._now()
        self._tokens = min(self.capacity, self._tokens + (t - self._last) * self.rate)
        self._last = t

    def acquire(self, n: int = 1) -> float:
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return 0.0
            wait = (n - self._tokens) / self.rate
            self._sleep(wait)
            self._refill()
            self._tokens = max(0.0, self._tokens - n)
            return wait
