"""Notifier: Telegram alerts for paper trades. Every message is labelled PAPER."""

from __future__ import annotations

from ..sources import SourceError
from ..sources.telegram import Telegram
from .base import Agent

HEADER = "[PAPER TRADE · live market data]"


class NotifierAgent(Agent):
    name = "notifier"

    def __init__(self, db, config, telegram: Telegram):
        super().__init__(db, config)
        self.telegram = telegram
        if not telegram.enabled:
            self.log("disabled", "Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID); alerts off")

    def _send(self, text: str, *, token=None, symbol=None) -> None:
        if not self.telegram.enabled:
            return
        try:
            self.telegram.send(text)
            self.log("sent", "Telegram alert sent", token=token, symbol=symbol)
        except SourceError as exc:
            self.log("error", f"Telegram alert failed: {exc}", token=token, symbol=symbol)

    def trade_opened(self, trade: dict) -> None:
        lines = [
            HEADER,
            f"Opened: {trade['symbol']}  ${trade['size_usd']:,.2f} simulated",
            f"Entry ${trade['entry_price_usd']:.10g}  stop ${trade['stop_price_usd']:.10g}  "
            f"target ${trade['target_price_usd']:.10g}",
        ]
        if trade.get("grok_summary"):
            lines += ["", f"Grok: {trade['grok_summary']}"]
        if trade.get("pair_url"):
            lines += ["", trade["pair_url"]]
        self._send("\n".join(lines), token=trade["token_address"], symbol=trade["symbol"])

    def trade_closed(self, trade: dict) -> None:
        text = (f"{HEADER}\nClosed: {trade['symbol']} ({trade['exit_reason']})\n"
                f"Exit ${trade['exit_price_usd']:.10g}  "
                f"P&L ${trade['pnl_usd']:+,.2f} ({trade['pnl_pct']:+.1f}%) simulated")
        self._send(text, token=trade["token_address"], symbol=trade["symbol"])

    def blocked(self, symbol: str, token: str, reasons: list[str]) -> None:
        if self.config.notify_blocked:
            self._send(f"{HEADER}\nBlocked: {symbol}\n- " + "\n- ".join(reasons[:5]),
                       token=token, symbol=symbol)
