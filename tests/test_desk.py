"""Unit tests. Fixtures mirror the shape of real API responses; they live only in tests
and never touch the desk database."""

import time

import pytest

from desk.agents import Analysis, Candidate, RiskAgent
from desk.agents.monitor import PositionMonitor
from desk.config import Config
from desk.db import DB
from desk.sources import SourceError
from desk.sources.dexscreener import best_pair, pair_facts
from desk.sources.grok import parse_analysis
from desk.sources.rugcheck import rug_facts

MINT = "Mint1111111111111111111111111111111111111pump"
PAIR = "Pair11111111111111111111111111111111111111111"


def make_pair(price="0.0001", liq=50_000, age_min=30, pair=PAIR):
    return {
        "pairAddress": pair, "dexId": "raydium", "url": f"https://dexscreener.com/solana/{pair}",
        "baseToken": {"address": MINT, "name": "Test", "symbol": "TST"},
        "quoteToken": {"symbol": "SOL"}, "priceUsd": price,
        "liquidity": {"usd": liq} if liq is not None else None,
        "volume": {"h1": 1000, "h24": 5000}, "txns": {"h1": {"buys": 10, "sells": 5}},
        "priceChange": {"h1": 3.2}, "fdv": 100_000, "marketCap": 100_000,
        "pairCreatedAt": int(time.time() * 1000) - age_min * 60_000,
    }


def clean_rug(**overrides):
    rug = {"mint_authority": None, "freeze_authority": None, "rugged": False,
           "score_normalised": 1, "total_holders": 500, "total_market_liquidity_usd": 50_000,
           "top10_holder_pct": 18.0, "insider_holders_in_top": 0, "lp_locked_pct": 100,
           "danger_risks": [], "warning_risks": []}
    rug.update(overrides)
    return rug


GOOD_GROK = {"summary": "s", "verdict": "candidate", "confidence": 0.8,
             "green_flags": [], "red_flags": []}


@pytest.fixture
def db():
    return DB(":memory:")


@pytest.fixture
def cfg():
    return Config()


def candidate(**fact_overrides):
    facts = pair_facts(make_pair())
    facts.update(fact_overrides)
    return Candidate(token_address=MINT, symbol="TST", name="Test", pair=make_pair(), facts=facts)


# -- sources ----------------------------------------------------------------------

def test_pair_facts_parses_string_price_and_ms_age():
    f = pair_facts(make_pair(price="0.000009120", age_min=90))
    assert f["price_usd"] == pytest.approx(9.12e-6)
    assert f["pair_age_minutes"] == pytest.approx(90, abs=0.2)


def test_pair_facts_handles_null_liquidity():
    assert pair_facts(make_pair(liq=None))["liquidity_usd"] is None


def test_best_pair_picks_most_liquid_own_pool():
    small, big = make_pair(liq=1_000, pair="A"), make_pair(liq=90_000, pair="B")
    assert best_pair([small, big], MINT)["pairAddress"] == "B"
    assert best_pair([small], "other-mint") is None


def test_rug_facts_excludes_pool_accounts_from_concentration():
    report = {
        "mintAuthority": None, "freezeAuthority": None, "rugged": False,
        "topHolders": [
            {"owner": PAIR, "pct": 41.8},          # the pool itself
            {"owner": "amm1", "pct": 10.0},        # known AMM account
            {"owner": "w1", "pct": 3.3, "insider": True},
            {"owner": "w2", "pct": 2.6},
        ],
        "knownAccounts": {"amm1": {"name": "Pump Fun AMM", "type": "AMM"}},
        "markets": [{"pubkey": "m1", "lp": {"lpLockedPct": 100, "quoteUSD": 2000, "baseUSD": 1800}}],
        "risks": [{"name": "Low Liquidity", "level": "danger"}, {"name": "x", "level": "warn"}],
    }
    f = rug_facts(report, {PAIR})
    assert f["top10_holder_pct"] == pytest.approx(5.9)
    assert f["insider_holders_in_top"] == 1
    assert f["lp_locked_pct"] == 100
    assert f["danger_risks"] == ["Low Liquidity"]


def test_rug_facts_unknown_when_fields_missing():
    f = rug_facts({"topHolders": None, "markets": None})
    assert f["top10_holder_pct"] is None and f["lp_locked_pct"] is None


def test_parse_analysis_validates():
    out = parse_analysis('{"summary":"ok","verdict":"Avoid","confidence":1.7,'
                         '"green_flags":[],"red_flags":["a"]}')
    assert out["verdict"] == "avoid" and out["confidence"] == 1.0
    with pytest.raises(SourceError):
        parse_analysis('{"verdict":"moon","confidence":0.9}')
    with pytest.raises(SourceError):
        parse_analysis("not json")


# -- risk agent ---------------------------------------------------------------------

def test_risk_approves_clean_token(db, cfg):
    d = RiskAgent(db, cfg).evaluate(candidate(), Analysis(clean_rug(), GOOD_GROK, []))
    assert d.approved, d.reasons


@pytest.mark.parametrize("rug, grok, facts, expected", [
    (clean_rug(mint_authority="abc"), GOOD_GROK, {}, "mint authority still enabled"),
    (clean_rug(freeze_authority="abc"), GOOD_GROK, {}, "freeze authority still enabled"),
    (clean_rug(top10_holder_pct=55.0), GOOD_GROK, {}, "top-10 holders own 55.0%"),
    (clean_rug(top10_holder_pct=None), GOOD_GROK, {}, "top-holder data unavailable"),
    (clean_rug(lp_locked_pct=None), GOOD_GROK, {}, "LP lock status unknown"),
    (clean_rug(lp_locked_pct=20), GOOD_GROK, {}, "LP locked 20%"),
    (clean_rug(rugged=True), GOOD_GROK, {}, "rugged"),
    (clean_rug(), {**GOOD_GROK, "verdict": "avoid"}, {}, "Grok verdict: avoid"),
    (clean_rug(), {**GOOD_GROK, "confidence": 0.3}, {}, "Grok confidence 30%"),
    (clean_rug(), None, {}, "no Grok analysis"),
    (None, GOOD_GROK, {}, "no RugCheck report"),
    (clean_rug(total_market_liquidity_usd=None), GOOD_GROK, {"liquidity_usd": None}, "liquidity unknown"),
    (clean_rug(), GOOD_GROK, {"liquidity_usd": 2_000}, "liquidity $2,000"),
])
def test_risk_blocks(db, cfg, rug, grok, facts, expected):
    d = RiskAgent(db, cfg).evaluate(candidate(**facts), Analysis(rug, grok, []))
    assert not d.approved
    assert any(expected in r for r in d.reasons), d.reasons


def test_risk_blocks_repeat_token_and_full_book(db):
    cfg = Config(max_open_positions=1)
    db.open_trade(token_address=MINT, symbol="TST", pair_address=PAIR, quote_price_usd=1,
                  entry_price_usd=1, size_usd=100, qty=100, stop_price_usd=0.75,
                  target_price_usd=1.5)
    d = RiskAgent(db, cfg).evaluate(candidate(), Analysis(clean_rug(), GOOD_GROK, []))
    assert "already paper-traded this token" in d.reasons
    assert any("open paper positions" in r for r in d.reasons)


# -- paper account and monitor ----------------------------------------------------------

class FakeDex:
    def __init__(self, price):
        self.price = price

    def tokens(self, addrs):
        return [make_pair(price=str(self.price))]


def open_paper(db, entry=1.0):
    return db.open_trade(token_address=MINT, symbol="TST", pair_address=PAIR,
                         quote_price_usd=entry, entry_price_usd=entry, size_usd=100,
                         qty=100 / entry, stop_price_usd=entry * 0.75, target_price_usd=entry * 1.5)


def test_monitor_marks_price_without_closing(db, cfg):
    tid = open_paper(db)
    assert PositionMonitor(db, cfg, FakeDex(1.1)).check() == []
    assert db.get_trade(tid)["last_price_usd"] == pytest.approx(1.1)
    assert db.account(1000)["unrealized_pnl_usd"] == pytest.approx(10)


def test_monitor_take_profit_records_pnl_with_slippage(db, cfg):
    open_paper(db)
    closed = PositionMonitor(db, cfg, FakeDex(1.6)).check()
    assert len(closed) == 1 and "take profit" in closed[0]["exit_reason"]
    # 100 units sold at 1.6 * (1 - 1%) = 1.584
    assert closed[0]["pnl_usd"] == pytest.approx(58.4)
    acct = db.account(1000)
    assert acct["realized_pnl_usd"] == pytest.approx(58.4)
    assert acct["cash_usd"] == pytest.approx(1058.4)


def test_monitor_stop_loss(db, cfg):
    open_paper(db)
    closed = PositionMonitor(db, cfg, FakeDex(0.7)).check()
    assert "stop loss" in closed[0]["exit_reason"] and closed[0]["pnl_usd"] < 0


def test_empty_db_has_no_fake_history(db):
    acct = db.account(1000)
    assert acct["equity_usd"] == 1000 and acct["closed_trades"] == 0
    assert db.recent_logs() == [] and db.open_trades() == [] and db.recent_tokens() == []
