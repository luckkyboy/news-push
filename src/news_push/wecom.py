from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from news_push.http import retry_http_call

logger = logging.getLogger(__name__)


def build_image_payload(image_bytes: bytes) -> dict[str, Any]:
    return {
        "msgtype": "image",
        "image": {
            "base64": base64.b64encode(image_bytes).decode("utf-8"),
            "md5": hashlib.md5(image_bytes).hexdigest(),
        },
    }


@dataclass
class WeComBotClient:
    webhook_url: str
    timeout: float = 10.0

    def send_text(self, content: str) -> None:
        self._post({"msgtype": "text", "text": {"content": content}})

    def send_image(self, image_bytes: bytes) -> None:
        self._post(build_image_payload(image_bytes))

    def _post(self, payload: dict[str, Any]) -> None:
        response = retry_http_call(
            lambda: httpx.post(self.webhook_url, json=payload, timeout=self.timeout),
            operation=f"post wecom message to {self.webhook_url}",
        )
        response.raise_for_status()
        body = response.json()
        if body.get("errcode") != 0:
            raise RuntimeError(f"wecom webhook error: {body}")
        logger.info("wecom message delivered: %s", payload["msgtype"])
