"""RugCheck public API (https://api.rugcheck.xyz/swagger/doc.json).

Uses GET /v1/tokens/{mint}/report (no auth). The full report is used rather than
/report/summary because, in live checks, the summary's top-level lpLockedPct did not
match the per-market lp.lpLockedPct, and the summary has no authority/holder fields.

Verified field names: mintAuthority, freezeAuthority, rugged, score_normalised,
totalHolders, totalMarketLiquidity, risks[{name,value,description,score,level}],
topHolders[{owner,pct (0-100),insider}], markets[{pubkey, lp{lpLockedPct (0-100), quoteUSD, baseUSD}}],
knownAccounts{address: {name, type}} where type "AMM" marks pool accounts.
"""

from __future__ import annotations

import httpx

from . import SourceError, http_client

BASE_URL = "https://api.rugcheck.xyz/v1"


class RugCheck:
    def __init__(self, client: httpx.Client | None = None):
        self.http = client or http_client(timeout=30)

    def report(self, mint: str) -> dict:
        try:
            resp = self.http.get(f"{BASE_URL}/tokens/{mint}/report")
        except httpx.HTTPError as exc:
            raise SourceError(f"rugcheck report: {type(exc).__name__}") from exc
        if resp.status_code == 404:
            raise SourceError("rugcheck: token not found (no report yet)")
        if resp.status_code >= 400:
            raise SourceError(f"rugcheck report: HTTP {resp.status_code}")
        return resp.json()


def rug_facts(report: dict, pair_addresses: set[str] | frozenset = frozenset()) -> dict:
    """Extract the safety facts the risk agent checks."""
    markets = report.get("markets") or []
    known = report.get("knownAccounts") or {}
    pool_accounts = set(pair_addresses) | {m.get("pubkey") for m in markets if m.get("pubkey")}
    pool_accounts |= {addr for addr, info in known.items()
                      if isinstance(info, dict) and info.get("type") == "AMM"}

    holders = [h for h in (report.get("topHolders") or [])
               if h.get("owner") not in pool_accounts and h.get("address") not in pool_accounts]
    holders.sort(key=lambda h: h.get("pct") or 0, reverse=True)
    top10 = sum((h.get("pct") or 0) for h in holders[:10]) if report.get("topHolders") is not None else None

    lp_locked = None
    if markets:
        def market_usd(m):
            lp = m.get("lp") or {}
            return (lp.get("quoteUSD") or 0) + (lp.get("baseUSD") or 0)
        main = max(markets, key=market_usd)
        lp_locked = (main.get("lp") or {}).get("lpLockedPct")

    risks = report.get("risks") or []
    return {
        "mint_authority": report.get("mintAuthority"),
        "freeze_authority": report.get("freezeAuthority"),
        "rugged": bool(report.get("rugged")),
        "score_normalised": report.get("score_normalised"),
        "total_holders": report.get("totalHolders"),
        "total_market_liquidity_usd": report.get("totalMarketLiquidity"),
        "top10_holder_pct": round(top10, 2) if top10 is not None else None,
        "insider_holders_in_top": sum(1 for h in holders[:10] if h.get("insider")),
        "lp_locked_pct": lp_locked,
        "danger_risks": [r.get("name") for r in risks if r.get("level") == "danger"],
        "warning_risks": [r.get("name") for r in risks if r.get("level") == "warn"],
    }
