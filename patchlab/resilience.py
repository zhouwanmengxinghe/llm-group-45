"""Bounded retries for transient failures; never repeat a failed test or patch."""
from __future__ import annotations

import errno
import random
import socket
import ssl
import time
from urllib.error import HTTPError, URLError

TRANSIENT = {errno.EAGAIN, errno.EBUSY, errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNREFUSED, errno.ENETUNREACH}


def transient_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code in {408, 429, 500, 502, 503, 504}
    if isinstance(exc, URLError):
        return transient_error(exc.reason) if isinstance(exc.reason, Exception) else False
    if isinstance(exc, ssl.SSLError):
        return False
    if isinstance(exc, socket.gaierror):
        return exc.errno == socket.EAI_AGAIN
    return isinstance(exc, (TimeoutError, socket.timeout, ConnectionError)) or (
        isinstance(exc, OSError) and (exc.errno in TRANSIENT or getattr(exc, "winerror", None) in {10035, 10054, 10060}))


def retry(operation, *, attempts=3, on_retry=None, sleep=time.sleep, jitter=random.random):
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt == attempts or not transient_error(exc):
                raise
            delay = min(4.0, 0.5 * (2 ** (attempt - 1)) + 0.2 * jitter())
            if isinstance(exc, HTTPError) and exc.code == 429:
                try:
                    delay = max(delay, min(10.0, max(0.0, float(exc.headers.get("Retry-After", "0")))))
                except (TypeError, ValueError, AttributeError):
                    pass
            if on_retry:
                on_retry({"attempt": attempt, "max_attempts": attempts, "delay_seconds": round(delay, 2),
                          "error_type": type(exc).__name__, "status": getattr(exc, "code", None)})
            sleep(delay)
