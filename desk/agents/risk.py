"""Risk agent: deterministic rules. Grok's opinion is one input; it cannot override a rule.

Missing data is treated as a failed check, never as a pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..rules import safety_checks
from .analyzer import Analysis
from .base import Agent
from .scanner import Candidate


@dataclass
class RiskDecision:
    approved: bool
    checks: list[dict] = field(default_factory=list)  # {rule, passed, detail}

    @property
    def reasons(self) -> list[str]:
        return [c["detail"] for c in self.checks if not c["passed"]]


class RiskAgent(Agent):
    name = "risk"

    def evaluate(self, c: Candidate, a: Analysis) -> RiskDecision:
        cfg = self.config
        checks = safety_checks(cfg, c.facts, a.rug)

        def check(rule: str, passed: bool, detail: str) -> None:
            checks.append({"rule": rule, "passed": bool(passed), "detail": detail})

        g = a.grok
        if g is None:
            check("grok", False, a.grok_note or "no Grok analysis")
        else:
            check("grok_verdict", g["verdict"] == "candidate", f"Grok verdict: {g['verdict']}")
            check("grok_confidence", g["confidence"] >= cfg.min_grok_confidence,
                  f"Grok confidence {g['confidence']:.0%} (min {cfg.min_grok_confidence:.0%})")

        account = self.db.account(cfg.paper_bankroll_usd)
        traded = self.db.has_traded(c.token_address)
        check("max_positions", account["open_positions"] < cfg.max_open_positions,
              f"{account['open_positions']} open paper positions (max {cfg.max_open_positions})")
        check("paper_cash", account["cash_usd"] >= cfg.paper_trade_size_usd,
              f"paper cash ${account['cash_usd']:,.2f} (need ${cfg.paper_trade_size_usd:,.2f})")
        check("not_already_traded", not traded,
              "already paper-traded this token" if traded else "first trade on this token")

        decision = RiskDecision(approved=all(ch["passed"] for ch in checks), checks=checks)
        if decision.approved:
            self.log("approved", "risk checks passed: approved for paper trade",
                     token=c.token_address, symbol=c.symbol, data={"checks": checks})
        else:
            self.log("blocked", "blocked: " + "; ".join(decision.reasons),
                     token=c.token_address, symbol=c.symbol, data={"checks": checks})
        self.db.upsert_token(c.token_address,
                             status="approved" if decision.approved else "blocked",
                             risk_reasons=decision.reasons)
        return decision
