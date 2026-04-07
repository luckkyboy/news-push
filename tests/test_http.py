import httpx
import pytest

from news_push.http import retry_http_call


def test_retry_http_call_retries_on_http_503() -> None:
    calls = 0

    def flaky_action() -> httpx.Response:
        nonlocal calls
        calls += 1
        response = httpx.Response(
            503 if calls == 1 else 200,
            request=httpx.Request("GET", "https://example.com"),
        )
        response.raise_for_status()
        return response

    response = retry_http_call(flaky_action, operation="fetch example")

    assert response.status_code == 200
    assert calls == 2


def test_retry_http_call_retries_on_http_429() -> None:
    calls = 0

    def throttled_action() -> httpx.Response:
        nonlocal calls
        calls += 1
        response = httpx.Response(
            429 if calls == 1 else 200,
            request=httpx.Request("POST", "https://example.com"),
        )
        response.raise_for_status()
        return response

    response = retry_http_call(throttled_action, operation="post example")

    assert response.status_code == 200
    assert calls == 2


def test_retry_http_call_does_not_retry_on_http_404() -> None:
    calls = 0

    def missing_action() -> httpx.Response:
        nonlocal calls
        calls += 1
        response = httpx.Response(
            404,
            request=httpx.Request("GET", "https://example.com/missing"),
        )
        response.raise_for_status()
        return response

    with pytest.raises(httpx.HTTPStatusError):
        retry_http_call(missing_action, operation="fetch missing")

    assert calls == 1
