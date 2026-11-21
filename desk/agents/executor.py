"""Paper executor: records a simulated fill at a freshly fetched live price.

PAPER ONLY. This module has no wallet, no keys, no transaction building and no signing.
It only writes rows to the local SQLite database.
"""

from __future__ import annotations

from ..sources import SourceError
from ..sources.dexscreener import DexScreener, pair_price
from .analyzer import Analysis
from .base import Agent
from .scanner import Candidate


class PaperExecutor(Agent):
    name = "executor"

    def __init__(self, db, config, dex: DexScreener):
        super().__init__(db, config)
        self.dex = dex

    def live_quote(self, token_address: str, pair_address: str) -> float | None:
        pairs = self.dex.token_pairs(token_address)
        for p in pairs:
            if p.get("pairAddress") == pair_address:
                return pair_price(p)
        return None

    def open(self, c: Candidate, a: Analysis) -> dict | None:
        cfg = self.config
        pair_address = c.facts["pair_address"]
        try:
            quote = self.live_quote(c.token_address, pair_address)
        except SourceError as exc:
            self.log("error", f"no live quote, paper trade not opened: {exc}",
                     token=c.token_address, symbol=c.symbol)
            return None
        if not quote:
            self.log("error", "pool returned no price, paper trade not opened",
                     token=c.token_address, symbol=c.symbol)
            return None

        entry = quote * (1 + cfg.paper_slippage_pct / 100)
        size = cfg.paper_trade_size_usd
        trade_id = self.db.open_trade(
            token_address=c.token_address, symbol=c.symbol, pair_address=pair_address,
            pair_url=c.facts.get("pair_url"), quote_price_usd=quote, entry_price_usd=entry,
            size_usd=size, qty=size / entry,
            stop_price_usd=entry * (1 - cfg.stop_loss_pct / 100),
            target_price_usd=entry * (1 + cfg.take_profit_pct / 100),
            grok_summary=a.grok["summary"] if a.grok else None,
        )
        self.db.upsert_token(c.token_address, status="traded")
        self.db.mark_price(trade_id, quote)  # first point of the position's price history
        self.db.record_equity(cfg.paper_bankroll_usd)
        trade = self.db.get_trade(trade_id)
        self.log("paper_open",
                 f"PAPER BUY ${size:,.2f} of {c.symbol} at ${entry:.10g} "
                 f"(live quote ${quote:.10g} + {cfg.paper_slippage_pct}% simulated slippage)",
                 token=c.token_address, symbol=c.symbol, data=trade)
        return trade
