import json
from typing import Literal

import httpx

ErrorClass = Literal["retriable", "fatal"]

RETRIABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})

def classify(exc: BaseException) -> ErrorClass:
    """Classify a fetch-time exception as retriable or fatal."""

    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in RETRIABLE_HTTP_STATUS:
            return "retriable"
        return "fatal"
    
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)):
        return "retriable"
    if isinstance(exc, json.JSONDecodeError):
        return "fatal"
    
    return "fatal"
    
    