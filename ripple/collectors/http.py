"""Polite HTTP: a rate limiter plus retries with back-off."""
from __future__ import annotations

import threading
import time

import requests


class RateLimiter:
    """Allow at most `per_second` calls per second (sliding one-second window)."""

    def __init__(self, per_second: float):
        self.min_interval = 1.0 / per_second
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._last + self.min_interval - now
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


class PoliteSession:
    def __init__(self, headers: dict, per_second: float, timeout: float = 60, retries: int = 4):
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.limiter = RateLimiter(per_second)
        self.timeout = timeout
        self.retries = retries
        self.request_count = 0

    def get(self, url: str, **kw) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self.limiter.wait()
            self.request_count += 1
            try:
                resp = self.session.get(url, timeout=self.timeout, **kw)
            except requests.RequestException as exc:  # network trouble: wait and retry
                last_exc = exc
                time.sleep(2 ** attempt)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                # Too many requests or a server hiccup: back off and try again.
                time.sleep(min(60, 2 ** (attempt + 1)))
                last_exc = requests.HTTPError(f"{resp.status_code} for {url}")
                continue
            resp.raise_for_status()
            return resp
        raise last_exc or RuntimeError(f"failed to fetch {url}")
