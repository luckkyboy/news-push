import base64
import hashlib

import httpx

from news_push.wecom import WeComBotClient, build_image_payload


def test_build_image_payload_uses_base64_and_md5() -> None:
    content = b"hello-image"

    payload = build_image_payload(content)

    assert payload["msgtype"] == "image"
    assert payload["image"]["base64"] == base64.b64encode(content).decode("utf-8")
    assert payload["image"]["md5"] == hashlib.md5(content).hexdigest()


def test_send_text_retries_after_transient_request_error(monkeypatch) -> None:
    calls = 0

    def fake_post(url: str, json: dict, timeout: float) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary failure")
        return httpx.Response(
            200,
            json={"errcode": 0},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = WeComBotClient("https://example.com/webhook", timeout=1.0)

    client.send_text("hello")

    assert calls == 2
