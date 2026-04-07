from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _is_retryable_status_error(exc: httpx.HTTPStatusError) -> bool:
    status_code = exc.response.status_code
    return status_code == 429 or 500 <= status_code < 600


def retry_http_call(
    action: Callable[[], T],
    *,
    operation: str,
    attempts: int = 2,
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_error: httpx.RequestError | httpx.HTTPStatusError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except httpx.RequestError as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            logger.warning(
                "%s failed on attempt %s/%s: %s",
                operation,
                attempt,
                attempts,
                exc,
            )
        except httpx.HTTPStatusError as exc:
            if not _is_retryable_status_error(exc):
                raise
            last_error = exc
            if attempt >= attempts:
                raise
            logger.warning(
                "%s failed on attempt %s/%s with status %s",
                operation,
                attempt,
                attempts,
                exc.response.status_code,
            )

    assert last_error is not None
    raise last_error
