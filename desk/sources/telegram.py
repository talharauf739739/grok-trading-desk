"""Telegram Bot API sendMessage. Errors are sanitized so the bot token never reaches logs."""

from __future__ import annotations

import httpx

from . import SourceError, http_client


class Telegram:
    def __init__(self, bot_token: str | None, chat_id: str | None,
                 client: httpx.Client | None = None):
        self._token = bot_token
        self._chat_id = chat_id
        self.http = client or http_client()

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, text: str) -> None:
        if not self.enabled:
            raise SourceError("telegram not configured")
        try:
            resp = self.http.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": text,
                      "disable_web_page_preview": True},
            )
        except httpx.HTTPError as exc:
            # str(exc) can include the request URL, which contains the token. Don't use it.
            raise SourceError(f"telegram send failed: {type(exc).__name__}") from None
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("description", "")
            except ValueError:
                detail = ""
            raise SourceError(f"telegram HTTP {resp.status_code} {detail}".strip())
