"""Free safety rules (DexScreener + RugCheck data only, no Grok call needed).

Shared by the analyzer, which skips Grok for tokens that already fail these checks so
Grok calls are spent only on tokens that could be traded, and by the risk agent, which
makes the final decision.
"""

from __future__ import annotations

from .config import Config


def safety_checks(cfg: Config, facts: dict, rug: dict | None) -> list[dict]:
    checks: list[dict] = []

    def check(rule: str, passed: bool, detail: str) -> None:
        checks.append({"rule": rule, "passed": bool(passed), "detail": detail})

    if rug is None:
        check("rugcheck", False, "no RugCheck report")
    else:
        check("not_rugged", not rug["rugged"],
              "RugCheck flags token as rugged" if rug["rugged"] else "not flagged rugged")
        check("mint_authority", rug["mint_authority"] is None,
              "mint authority still enabled" if rug["mint_authority"] else "mint authority revoked")
        check("freeze_authority", rug["freeze_authority"] is None,
              "freeze authority still enabled" if rug["freeze_authority"] else "freeze authority revoked")
        top10 = rug["top10_holder_pct"]
        check("holder_concentration", top10 is not None and top10 <= cfg.max_top10_holder_pct,
              "top-holder data unavailable" if top10 is None
              else f"top-10 holders own {top10:.1f}% (max {cfg.max_top10_holder_pct:.0f}%)")
        lp = rug["lp_locked_pct"]
        check("lp_locked", lp is not None and lp >= cfg.min_lp_locked_pct,
              "LP lock status unknown" if lp is None
              else f"LP locked {lp:.0f}% (min {cfg.min_lp_locked_pct:.0f}%)")
        check("rugcheck_danger", not rug["danger_risks"],
              "RugCheck danger: " + ", ".join(rug["danger_risks"]) if rug["danger_risks"]
              else "no RugCheck danger risks")

    liquidity = facts.get("liquidity_usd")
    if liquidity is None and rug:
        liquidity = rug.get("total_market_liquidity_usd")
    check("liquidity", liquidity is not None and liquidity >= cfg.min_liquidity_usd,
          "liquidity unknown" if liquidity is None
          else f"liquidity ${liquidity:,.0f} (min ${cfg.min_liquidity_usd:,.0f})")
    return checks
