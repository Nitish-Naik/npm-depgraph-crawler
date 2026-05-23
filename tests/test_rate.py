from datetime import datetime, timezone

import pytest

from crawler.rate import RateLimiter, parse_retry_after


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_rate_limiter_sleeps_between_requests():
    clock = FakeClock()
    limiter = RateLimiter(2.0, clock=clock.monotonic, sleeper=clock.sleep)

    assert limiter.wait() == 0.0
    assert limiter.wait() == pytest.approx(0.5)
    assert clock.sleeps == [0.5]


def test_rate_limiter_can_be_disabled():
    clock = FakeClock()
    limiter = RateLimiter(0, clock=clock.monotonic, sleeper=clock.sleep)

    assert limiter.wait() == 0.0
    assert limiter.wait() == 0.0
    assert clock.sleeps == []


def test_rate_limiter_pause_honors_retry_after():
    clock = FakeClock()
    limiter = RateLimiter(1.0, clock=clock.monotonic, sleeper=clock.sleep)

    limiter.wait()
    assert limiter.pause(3.0) == 3.0
    assert limiter.wait() == pytest.approx(1.0)
    assert clock.sleeps == [3.0, 1.0]


def test_parse_retry_after_delta_seconds():
    assert parse_retry_after("7") == 7.0
    assert parse_retry_after("-1") == 0.0


def test_parse_retry_after_http_date():
    now = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

    assert parse_retry_after("Sat, 23 May 2026 12:00:05 GMT", now=now) == 5.0


def test_parse_retry_after_invalid_values():
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("eventually") is None
