from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable


Clock = Callable[[], float]
Sleeper = Callable[[float], None]


class RateLimiter:
    """Small synchronous rate limiter for polite single-process crawling."""

    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if requests_per_second < 0:
            raise ValueError("requests_per_second must be >= 0")

        self.min_interval = 1.0 / requests_per_second if requests_per_second else 0.0
        self._clock = clock
        self._sleeper = sleeper
        self._next_allowed_at = 0.0

    def wait(self) -> float:
        """Block until the next request may be sent. Returns seconds slept."""
        if self.min_interval <= 0:
            return 0.0

        now = self._clock()
        slept = 0.0
        if now < self._next_allowed_at:
            slept = self._next_allowed_at - now
            self._sleeper(slept)
            now = self._clock()

        self._next_allowed_at = now + self.min_interval
        return slept

    def pause(self, seconds: float) -> float:
        """Honor a server-directed pause, such as Retry-After."""
        if seconds <= 0:
            return 0.0

        self._sleeper(seconds)
        now = self._clock()
        self._next_allowed_at = max(self._next_allowed_at, now + self.min_interval)
        return seconds


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Parse Retry-After seconds or HTTP-date values into a non-negative delay."""
    if not value:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    try:
        seconds = float(stripped)
    except ValueError:
        seconds = None

    if seconds is not None:
        return max(0.0, seconds)

    try:
        retry_at = parsedate_to_datetime(stripped)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)

    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)

    return max(0.0, (retry_at - base).total_seconds())
