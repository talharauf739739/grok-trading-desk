"""Wires the agents together:

Scanner -> Analyzer (Grok) -> Risk agent -> Paper executor -> Notifier
Position monitor runs on its own timer and closes paper trades.
"""

from __future__ import annotations

import logging
import threading

from .agents import (AnalyzerAgent, NotifierAgent, PaperExecutor, PositionMonitor, RiskAgent,
                     ScannerAgent)
from .budget import GrokBudget
from .config import Config
from .db import DB
from .sources import SourceError
from .sources.dexscreener import DexScreener
from .sources.grok import Grok
from .sources.rugcheck import RugCheck
from .sources.telegram import Telegram

log = logging.getLogger("desk")


class Desk:
    def __init__(self, config: Config, *, db: DB | None = None, dex: DexScreener | None = None,
                 rugcheck: RugCheck | None = None, grok: Grok | None = None,
                 telegram: Telegram | None = None):
        self.config = config
        self.db = db or DB(config.db_path)
        dex = dex or DexScreener()
        if grok is None:
            try:
                grok = Grok(config.xai_api_key, config.xai_model)
            except SourceError as exc:
                self.db.log("analyzer", "disabled", f"Grok unavailable: {exc}; every token will be blocked")
        self.budget = GrokBudget(self.db, config.grok_daily_call_limit)
        self.scanner = ScannerAgent(self.db, config, dex)
        self.analyzer = AnalyzerAgent(self.db, config, rugcheck or RugCheck(), grok, self.budget)
        self.risk = RiskAgent(self.db, config)
        self.executor = PaperExecutor(self.db, config, dex)
        self.notifier = NotifierAgent(
            self.db, config,
            telegram or Telegram(config.telegram_bot_token, config.telegram_chat_id))
        self.monitor = PositionMonitor(self.db, config, dex)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def scan_once(self) -> dict:
        summary = {"candidates": 0, "approved": 0, "opened": 0}
        for c in self.scanner.scan():
            summary["candidates"] += 1
            try:
                analysis = self.analyzer.analyze(c)
                decision = self.risk.evaluate(c, analysis)
                if not decision.approved:
                    self.notifier.blocked(c.symbol, c.token_address, decision.reasons)
                    continue
                summary["approved"] += 1
                trade = self.executor.open(c, analysis)
                if trade:
                    summary["opened"] += 1
                    self.notifier.trade_opened(trade)
            except Exception as exc:  # one bad token must not stop the desk
                log.exception("pipeline error on %s", c.symbol)
                self.db.upsert_token(c.token_address, status="error")
                self.db.log("desk", "error", f"pipeline error: {type(exc).__name__}: {exc}",
                            token_address=c.token_address, symbol=c.symbol)
        return summary

    def monitor_once(self) -> int:
        closed = self.monitor.check()
        for trade in closed:
            self.notifier.trade_closed(trade)
        return len(closed)

    def _every(self, interval: float, fn, name: str) -> None:
        while not self._stop.is_set():
            try:
                fn()
            except Exception:
                log.exception("%s loop error", name)
            self._stop.wait(interval)

    @property
    def running(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def start_background(self) -> None:
        """Start the scanner and monitor loops in daemon threads and return."""
        if self.running:
            return
        self._stop.clear()
        if not self.db.equity_curve(1):
            self.db.record_equity(self.config.paper_bankroll_usd)
        self.db.log("desk", "start",
                    f"desk started (paper only): scan every {self.config.scan_interval_s:g}s, "
                    f"monitor every {self.config.monitor_interval_s:g}s, "
                    f"Grok limit {self.config.grok_daily_call_limit}/day")
        self._threads = [
            threading.Thread(target=self._every, name="monitor", daemon=True,
                             args=(self.config.monitor_interval_s, self.monitor_once, "monitor")),
            threading.Thread(target=self._every, name="scan", daemon=True,
                             args=(self.config.scan_interval_s, self.scan_once, "scan")),
        ]
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        self.start_background()
        try:
            while self.running:
                for t in self._threads:
                    t.join(timeout=1)
        except KeyboardInterrupt:
            self.stop()
            self.db.log("desk", "stop", "desk stopped")
