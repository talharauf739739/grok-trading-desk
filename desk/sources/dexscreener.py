"""DexScreener public API (https://docs.dexscreener.com/api/reference).

Endpoints used:
  GET /token-profiles/latest/v1                  latest token profiles (60 req/min)
  GET /token-pairs/v1/{chainId}/{tokenAddress}   pools for one token
  GET /tokens/v1/{chainId}/{addr1,addr2,...}     pairs for several tokens (chunked by 30)

Verified against live responses: priceUsd is a string, pairCreatedAt is epoch ms,
liquidity can be null (e.g. pump.fun bonding-curve pairs).
"""

from __future__ import annotations

import time

import httpx

from . import SourceError, http_client

BASE_URL = "https://api.dexscreener.com"
CHAIN = "solana"
TOKENS_PER_REQUEST = 30


def _float(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


class DexScreener:
    def __init__(self, client: httpx.Client | None = None):
        self.http = client or http_client()

    def _get(self, path: str):
        try:
            resp = self.http.get(BASE_URL + path)
        except httpx.HTTPError as exc:
            raise SourceError(f"dexscreener {path}: {type(exc).__name__}") from exc
        if resp.status_code == 429:
            raise SourceError("dexscreener rate limited (429)")
        if resp.status_code >= 400:
            raise SourceError(f"dexscreener {path}: HTTP {resp.status_code}")
        return resp.json()

    def latest_profiles(self) -> list[dict]:
        data = self._get("/token-profiles/latest/v1")
        return [p for p in (data or []) if p.get("chainId") == CHAIN and p.get("tokenAddress")]

    def token_pairs(self, token_address: str) -> list[dict]:
        return self._get(f"/token-pairs/v1/{CHAIN}/{token_address}") or []

    def tokens(self, token_addresses: list[str]) -> list[dict]:
        pairs: list[dict] = []
        unique = list(dict.fromkeys(token_addresses))
        for i in range(0, len(unique), TOKENS_PER_REQUEST):
            chunk = ",".join(unique[i:i + TOKENS_PER_REQUEST])
            pairs.extend(self._get(f"/tokens/v1/{CHAIN}/{chunk}") or [])
        return pairs


def best_pair(pairs: list[dict], token_address: str) -> dict | None:
    """The pool where this token is the base token with the most USD liquidity (then volume)."""
    own = [p for p in pairs if (p.get("baseToken") or {}).get("address") == token_address
           and _float(p.get("priceUsd"))]
    if not own:
        return None
    return max(own, key=lambda p: (((p.get("liquidity") or {}).get("usd") or 0),
                                   ((p.get("volume") or {}).get("h24") or 0)))


def pair_price(pair: dict) -> float | None:
    return _float(pair.get("priceUsd"))


def pair_facts(pair: dict, now_ms: int | None = None) -> dict:
    """Flatten a DexScreener pair into the numbers the agents use."""
    now_ms = now_ms or int(time.time() * 1000)
    created = pair.get("pairCreatedAt")
    txns = pair.get("txns") or {}
    vol = pair.get("volume") or {}
    chg = pair.get("priceChange") or {}
    base = pair.get("baseToken") or {}
    return {
        "symbol": base.get("symbol"),
        "name": base.get("name"),
        "token_address": base.get("address"),
        "pair_address": pair.get("pairAddress"),
        "pair_url": pair.get("url"),
        "dex": pair.get("dexId"),
        "quote_symbol": (pair.get("quoteToken") or {}).get("symbol"),
        "price_usd": _float(pair.get("priceUsd")),
        "liquidity_usd": _float((pair.get("liquidity") or {}).get("usd")),
        "fdv_usd": _float(pair.get("fdv")),
        "market_cap_usd": _float(pair.get("marketCap")),
        "volume_m5_usd": _float(vol.get("m5")),
        "volume_h1_usd": _float(vol.get("h1")),
        "volume_h24_usd": _float(vol.get("h24")),
        "buys_h1": (txns.get("h1") or {}).get("buys"),
        "sells_h1": (txns.get("h1") or {}).get("sells"),
        "price_change_m5_pct": _float(chg.get("m5")),
        "price_change_h1_pct": _float(chg.get("h1")),
        "price_change_h24_pct": _float(chg.get("h24")),
        "pair_age_minutes": round((now_ms - created) / 60000, 1) if created else None,
    }
