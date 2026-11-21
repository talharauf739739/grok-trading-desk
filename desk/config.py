"""Settings. Secrets come only from .env; tunables have defaults and optional env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


def _str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, "").strip()
    return value or default


def _num(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


@dataclass(frozen=True)
class Config:
    # secrets: repr=False so printing a Config never shows them
    xai_api_key: str | None = field(default=None, repr=False)
    telegram_bot_token: str | None = field(default=None, repr=False)
    telegram_chat_id: str | None = field(default=None, repr=False)

    xai_model: str = "grok-4.7"
    db_path: str = "data/desk.db"

    # loop timing
    scan_interval_s: float = 45
    monitor_interval_s: float = 15
    max_analyses_per_scan: int = 4   # caps Grok/RugCheck calls per scan

    # scanner
    max_pair_age_hours: float = 24

    # risk rules
    min_liquidity_usd: float = 10_000
    max_top10_holder_pct: float = 30   # excluding pool/AMM accounts
    min_lp_locked_pct: float = 90
    min_grok_confidence: float = 0.6
    max_open_positions: int = 5

    # paper execution
    paper_bankroll_usd: float = 1_000
    paper_trade_size_usd: float = 100
    paper_slippage_pct: float = 1.0    # applied against us on entry and exit

    # position monitor exits
    stop_loss_pct: float = 25
    take_profit_pct: float = 50
    max_hold_minutes: float = 240

    notify_blocked: bool = False

    # Grok budget: hard daily cap on calls; the desk pauses Grok when it is reached
    grok_daily_call_limit: int = 30

    # run the agents inside the Streamlit process (for Streamlit Community Cloud)
    embed_agents: bool = False
    built_by: str = "@ai_talha_agents"

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


def load_config() -> Config:
    load_dotenv()
    return Config(
        xai_api_key=_str("XAI_API_KEY"),
        telegram_bot_token=_str("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_str("TELEGRAM_CHAT_ID"),
        xai_model=_str("XAI_MODEL", "grok-4.7"),
        db_path=_str("DESK_DB_PATH", "data/desk.db"),
        scan_interval_s=_num("SCAN_INTERVAL_S", 45),
        monitor_interval_s=_num("MONITOR_INTERVAL_S", 15),
        max_analyses_per_scan=int(_num("MAX_ANALYSES_PER_SCAN", 4)),
        max_pair_age_hours=_num("MAX_PAIR_AGE_HOURS", 24),
        min_liquidity_usd=_num("MIN_LIQUIDITY_USD", 10_000),
        max_top10_holder_pct=_num("MAX_TOP10_HOLDER_PCT", 30),
        min_lp_locked_pct=_num("MIN_LP_LOCKED_PCT", 90),
        min_grok_confidence=_num("MIN_GROK_CONFIDENCE", 0.6),
        max_open_positions=int(_num("MAX_OPEN_POSITIONS", 5)),
        paper_bankroll_usd=_num("PAPER_BANKROLL_USD", 1_000),
        paper_trade_size_usd=_num("PAPER_TRADE_SIZE_USD", 100),
        paper_slippage_pct=_num("PAPER_SLIPPAGE_PCT", 1.0),
        stop_loss_pct=_num("STOP_LOSS_PCT", 25),
        take_profit_pct=_num("TAKE_PROFIT_PCT", 50),
        max_hold_minutes=_num("MAX_HOLD_MINUTES", 240),
        notify_blocked=_bool("NOTIFY_BLOCKED"),
        grok_daily_call_limit=int(_num("GROK_DAILY_CALL_LIMIT", 30)),
        embed_agents=_bool("EMBED_AGENTS"),
        built_by=_str("BUILT_BY", "@ai_talha_agents"),
    )


def _bool(name: str) -> bool:
    return (_str(name, "false") or "").lower() in ("1", "true", "yes")
