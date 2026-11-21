"""Analyzer: pulls the RugCheck report and asks Grok to explain the token."""

from __future__ import annotations

from dataclasses import dataclass

from ..sources import SourceError
from ..sources.grok import Grok
from ..sources.rugcheck import RugCheck, rug_facts
from .base import Agent
from .scanner import Candidate


@dataclass
class Analysis:
    rug: dict | None         # None if RugCheck had no report
    grok: dict | None        # None if Grok failed
    errors: list[str]


class AnalyzerAgent(Agent):
    name = "analyzer"

    def __init__(self, db, config, rugcheck: RugCheck, grok: Grok | None):
        super().__init__(db, config)
        self.rugcheck = rugcheck
        self.grok = grok

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

        grok = None
        if self.grok is None:
            errors.append("Grok not configured")
        else:
            payload = {
                "token": {"symbol": c.symbol, "name": c.name, "mint": c.token_address},
                "market_data_dexscreener": c.facts,
                "safety_report_rugcheck": rug or "unavailable",
                "creator_profile_unverified": c.profile,
            }
            try:
                grok = self.grok.analyze(payload)
                self.log("grok_analysis",
                         f"Grok ({grok['verdict']}, {grok['confidence']:.0%}): {grok['summary']}",
                         token=c.token_address, symbol=c.symbol, data=grok)
            except SourceError as exc:
                errors.append(str(exc))
                self.log("error", f"Grok analysis failed: {exc}", token=c.token_address, symbol=c.symbol)

        self.db.upsert_token(
            c.token_address, status="analyzed",
            grok_summary=grok["summary"] if grok else None,
            grok_verdict=grok["verdict"] if grok else None,
            grok_confidence=grok["confidence"] if grok else None,
        )
        return Analysis(rug=rug, grok=grok, errors=errors)


def _pct(v) -> str:
    return "unknown" if v is None else f"{v:.0f}%"
