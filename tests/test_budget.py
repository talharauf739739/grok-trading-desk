"""Grok budget: the desk must stop calling Grok on its own when limits are hit."""

import pytest

from desk.agents import AnalyzerAgent, Candidate
from desk.budget import GrokBudget
from desk.config import Config
from desk.db import DB
from desk.sources import SourceError
from desk.sources.dexscreener import pair_facts
from tests.test_desk import MINT, PAIR, make_pair

CLEAN_REPORT = {
    "mintAuthority": None, "freezeAuthority": None, "rugged": False, "totalMarketLiquidity": 50_000,
    "topHolders": [{"owner": "w1", "pct": 5.0}],
    "markets": [{"pubkey": "m1", "lp": {"lpLockedPct": 100, "quoteUSD": 30_000, "baseUSD": 20_000}}],
    "risks": [],
}


class FakeRug:
    def __init__(self, report):
        self.r = report

    def report(self, mint):
        return self.r


class FakeGrok:
    def __init__(self, fail_status=None):
        self.calls = 0
        self.fail_status = fail_status
        self.before_request = None

    def analyze(self, payload):
        if self.before_request:
            self.before_request()
        self.calls += 1
        if self.fail_status:
            raise SourceError("nope", status=self.fail_status)
        return {"summary": "s", "verdict": "candidate", "confidence": 0.8,
                "green_flags": [], "red_flags": []}


def cand(liq=50_000):
    p = make_pair(liq=liq)
    return Candidate(token_address=MINT, symbol="TST", name="Test", pair=p,
                     facts=pair_facts(p), all_pair_addresses={PAIR})


@pytest.fixture
def db():
    return DB(":memory:")


def test_daily_limit_blocks_after_cap(db):
    b = GrokBudget(db, 2)
    assert b.blocked_reason() is None
    b.record_call()
    b.record_call()
    assert "daily Grok limit reached" in b.blocked_reason()


def test_zero_limit_disables_grok(db):
    assert "disabled" in GrokBudget(db, 0).blocked_reason()


@pytest.mark.parametrize("status", [401, 402, 403])
def test_no_credit_errors_pause_until_tomorrow(db, status):
    b = GrokBudget(db, 100)
    assert b.handle_http_error(status)
    assert "xAI refused" in b.blocked_reason()


def test_rate_limit_pauses_briefly(db):
    b = GrokBudget(db, 100)
    b.handle_http_error(429)
    assert "rate limit" in b.blocked_reason()
    assert GrokBudget(db, 100).handle_http_error(500) is None


def test_analyzer_skips_grok_when_free_checks_fail(db):
    grok = FakeGrok()
    a = AnalyzerAgent(db, Config(), FakeRug(CLEAN_REPORT), grok).analyze(cand(liq=500))
    assert grok.calls == 0 and a.grok is None
    assert "failed free safety checks" in a.grok_note


def test_analyzer_calls_grok_for_clean_token_and_counts_it(db):
    grok = FakeGrok()
    agent = AnalyzerAgent(db, Config(grok_daily_call_limit=1), FakeRug(CLEAN_REPORT), grok)
    assert agent.analyze(cand()).grok is not None
    assert agent.budget.used_today() == 1
    # the limit is now used up: the next clean token must not reach Grok
    second = agent.analyze(cand())
    assert grok.calls == 1 and second.grok is None and "daily Grok limit" in second.grok_note


def test_analyzer_pauses_grok_when_out_of_credits(db):
    grok = FakeGrok(fail_status=402)
    agent = AnalyzerAgent(db, Config(), FakeRug(CLEAN_REPORT), grok)
    first = agent.analyze(cand())
    assert first.grok is None and "Grok paused" in first.grok_note
    agent.analyze(cand())
    assert grok.calls == 1  # no retry after the credit error
