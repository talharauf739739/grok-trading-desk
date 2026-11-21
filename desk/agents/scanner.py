"""Scanner: finds newly profiled Solana tokens on DexScreener and picks their main pool."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..sources import SourceError
from ..sources.dexscreener import DexScreener, best_pair, pair_facts
from .base import Agent


@dataclass
class Candidate:
    token_address: str
    symbol: str
    name: str
    pair: dict
    facts: dict
    profile: dict = field(default_factory=dict)
    all_pair_addresses: set[str] = field(default_factory=set)


class ScannerAgent(Agent):
    name = "scanner"

    def __init__(self, db, config, dex: DexScreener):
        super().__init__(db, config)
        self.dex = dex

    def scan(self) -> list[Candidate]:
        try:
            profiles = self.dex.latest_profiles()
        except SourceError as exc:
            self.log("error", f"could not fetch latest profiles: {exc}")
            return []
        new = [p for p in profiles if not self.db.is_seen(p["tokenAddress"])]
        self.log("scan", f"{len(profiles)} Solana profiles, {len(new)} new",
                 data={"profiles": len(profiles), "new": len(new)})

        candidates: list[Candidate] = []
        for profile in new:
            if len(candidates) >= self.config.max_analyses_per_scan:
                break  # the rest stay unseen and are picked up next scan
            mint = profile["tokenAddress"]
            try:
                pairs = self.dex.token_pairs(mint)
            except SourceError as exc:
                self.log("error", f"pairs lookup failed: {exc}", token=mint)
                continue
            pair = best_pair(pairs, mint)
            if pair is None:
                self.db.upsert_token(mint, status="skipped", risk_reasons=["no priced pool"])
                continue
            facts = pair_facts(pair)
            symbol = facts["symbol"] or mint[:6]
            age_h = (facts["pair_age_minutes"] or 0) / 60
            if facts["pair_age_minutes"] is None or age_h > self.config.max_pair_age_hours:
                self.db.upsert_token(mint, symbol=symbol, name=facts["name"], status="skipped",
                                     pair_address=facts["pair_address"], pair_url=facts["pair_url"],
                                     risk_reasons=[f"pool not new (age {age_h:.1f}h)"])
                continue
            self.db.upsert_token(mint, symbol=symbol, name=facts["name"], status="seen",
                                 pair_address=facts["pair_address"], pair_url=facts["pair_url"])
            self.log("new_token",
                     f"new token {symbol} on {facts['dex']}: ${facts['price_usd']:.10g}, "
                     f"pool age {facts['pair_age_minutes']:.0f} min",
                     token=mint, symbol=symbol, data=facts)
            candidates.append(Candidate(
                token_address=mint, symbol=symbol, name=facts["name"] or "", pair=pair,
                facts=facts,
                profile={"description": profile.get("description"),
                         "links": [{"type": l.get("type"), "label": l.get("label"), "url": l.get("url")}
                                   for l in (profile.get("links") or [])][:8]},
                all_pair_addresses={p.get("pairAddress") for p in pairs if p.get("pairAddress")},
            ))
        return candidates
