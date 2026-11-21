"""Position monitor: re-prices open paper trades from DexScreener and closes them on rules."""

from __future__ import annotations

from datetime import datetime, timezone

from ..sources import SourceError
from ..sources.dexscreener import DexScreener, pair_price
from .base import Agent


class PositionMonitor(Agent):
    name = "monitor"

    def __init__(self, db, config, dex: DexScreener):
        super().__init__(db, config)
        self.dex = dex

    def check(self) -> list[dict]:
        """Returns trades closed during this check."""
        trades = self.db.open_trades()
        if not trades:
            return []
        try:
            pairs = self.dex.tokens([t["token_address"] for t in trades])
        except SourceError as exc:
            self.log("error", f"could not re-price open positions: {exc}")
            return []
        prices = {p.get("pairAddress"): pair_price(p) for p in pairs}

        closed = []
        now = datetime.now(timezone.utc)
        cfg = self.config
        for t in trades:
            quote = prices.get(t["pair_address"])
            if not quote:
                continue  # keep the last real price; never guess one
            self.db.mark_price(t["id"], quote)
            held_min = (now - datetime.fromisoformat(t["opened_at"])).total_seconds() / 60
            reason = None
            if quote <= t["stop_price_usd"]:
                reason = f"stop loss (-{cfg.stop_loss_pct:g}%)"
            elif quote >= t["target_price_usd"]:
                reason = f"take profit (+{cfg.take_profit_pct:g}%)"
            elif held_min >= cfg.max_hold_minutes:
                reason = f"time exit ({cfg.max_hold_minutes:g} min)"
            if reason:
                exit_price = quote * (1 - cfg.paper_slippage_pct / 100)
                trade = self.db.close_trade(t["id"], exit_quote_usd=quote,
                                            exit_price_usd=exit_price, reason=reason)
                self.log("paper_close",
                         f"PAPER SELL {t['symbol']} at ${exit_price:.10g}: {reason}, "
                         f"P&L ${trade['pnl_usd']:+,.2f} ({trade['pnl_pct']:+.1f}%)",
                         token=t["token_address"], symbol=t["symbol"], data=trade)
                closed.append(trade)
        self.db.record_equity(cfg.paper_bankroll_usd)
        return closed
