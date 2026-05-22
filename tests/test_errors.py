import json

import httpx
import pytest

from crawler.errors import classify

def _http_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com/x")
    response = httpx.Response(status_code, request=request)

    return httpx.HTTPStatusError("boom", request=request, response=response)

@pytest.mark.parametrize(
    "exc, expected",
    [
        (_http_error(404), "fatal"),
        (_http_error(403), "fatal"),
        (_http_error(429), "retriable"),
        (_http_error(500), "retriable"),
        (_http_error(502), "retriable"),
        (_http_error(503), "retriable"),
        (_http_error(504), "retriable"),
        (httpx.TimeoutException("timed out"), "retriable"),
        (httpx.ConnectError("no route"), "retriable"),
        (httpx.NetworkError("network down"), "retriable"),
        (json.JSONDecodeError("bad json", "", 0), "fatal"),
        (ValueError("missing name"), "fatal"),
        (RuntimeError("unexpected"), "fatal"),
    ],
)


def test_classify(exc, expected):
    assert classify(exc) == expected