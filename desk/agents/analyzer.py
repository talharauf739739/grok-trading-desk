"""Analyzer: pulls the RugCheck report and asks Grok to explain the token.

To keep Grok inside its budget, Grok is only called when the token already passes the
free safety checks (RugCheck + liquidity) and the daily Grok limit is not used up.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..budget import GrokBudget
from ..rules import safety_checks
from ..sources import SourceError
from ..sources.grok import Grok
from ..sources.rugcheck import RugCheck, rug_facts
from .base import Agent
from .scanner import Candidate


@dataclass
class Analysis:
    rug: dict | None         # None if RugCheck had no report
    grok: dict | None        # None if Grok was skipped or failed
    errors: list[str]
    grok_note: str | None = None  # why Grok has no analysis, if it doesn't


class AnalyzerAgent(Agent):
    name = "analyzer"

    def __init__(self, db, config, rugcheck: RugCheck, grok: Grok | None,
                 budget: GrokBudget | None = None):
        super().__init__(db, config)
        self.rugcheck = rugcheck
        self.grok = grok
        self.budget = budget or GrokBudget(db, config.grok_daily_call_limit)
        if grok is not None:
            grok.before_request = self.budget.record_call

    def analyze(self, c: Candidate) -> Analysis:
        errors: list[str] = []
        rug = None
        try:
            rug = rug_facts(self.rugcheck.report(c.token_address), c.all_pair_addresses)
            self.log("rugcheck",
                     f"RugCheck: mint auth {'set' if rug['mint_authority'] else 'revoked'}, "
                     f"freeze auth {'set' if rug['freeze_authority'] else 'revoked'}, "
                     f"top-10 holders {_pct(rug['top10_holder_pct'])}, LP locked {_pct(rug['lp_locked_pct'])}",
                     token=c.token_address, symbol=c.symbol, data=rug)
        except SourceError as exc:
            errors.append(str(exc))
            self.log("error", f"RugCheck unavailable: {exc}", token=c.token_address, symbol=c.symbol)

        grok, note = None, None
        failed = [ch["detail"] for ch in safety_checks(self.config, c.facts, rug) if not ch["passed"]]
        if failed:
            note = "Grok skipped: token failed free safety checks"
            self.log("grok_skipped", f"{note} ({failed[0]})", token=c.token_address, symbol=c.symbol)
        elif self.grok is None:
            note = "Grok not configured (XAI_API_KEY missing)"
        elif reason := self.budget.blocked_reason():
            note = f"Grok paused: {reason}"
            self.log("grok_skipped", note, token=c.token_address, symbol=c.symbol)
        else:
            payload = {
                "token": {"symbol": c.symbol, "name": c.name, "mint": c.token_address},
                "market_data_dexscreener": c.facts,
                "safety_report_rugcheck": rug,
                "creator_profile_unverified": c.profile,
            }
            try:
                grok = self.grok.analyze(payload)
                self.log("grok_analysis",
                         f"Grok ({grok['verdict']}, {grok['confidence']:.0%}): {grok['summary']}",
                         token=c.token_address, symbol=c.symbol, data=grok)
            except SourceError as exc:
                errors.append(str(exc))
                paused = self.budget.handle_http_error(exc.status) if exc.status else None
                note = f"Grok paused: {paused}" if paused else "Grok analysis failed"
                self.log("error", f"Grok analysis failed: {exc}" + (f" -> {note}" if paused else ""),
                         token=c.token_address, symbol=c.symbol)

        self.db.upsert_token(
            c.token_address, status="analyzed",
            grok_summary=grok["summary"] if grok else None,
            grok_verdict=grok["verdict"] if grok else None,
            grok_confidence=grok["confidence"] if grok else None,
        )
        return Analysis(rug=rug, grok=grok, errors=errors, grok_note=note)


def _pct(v) -> str:
    return "unknown" if v is None else f"{v:.0f}%"
