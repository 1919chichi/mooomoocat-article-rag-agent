from __future__ import annotations

import math
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 1.5)


def is_retryable(error: Exception) -> bool:
    msg = str(error).lower()
    return "429" in msg or "500" in msg or "502" in msg or "503" in msg or "504" in msg


def retry_with_backoff(fn: Callable[[], T], max_attempts: int = 4) -> T:
    wait_time = 1.0
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise
            if not is_retryable(e):
                raise
            time.sleep(wait_time)
            wait_time *= 2
    raise AssertionError("unreachable")  # pragma: no cover
