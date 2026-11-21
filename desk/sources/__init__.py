"""Read-only clients for public market data, Grok, and Telegram. No signing, no wallets."""

import httpx

USER_AGENT = "grok-trading-desk/0.1 (paper trading)"


def http_client(timeout: float = 20) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT,
                                                  "Accept": "application/json"})


class SourceError(Exception):
    pass
