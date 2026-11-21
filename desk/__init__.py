"""Grok Multi-Agent Trading Desk. Paper trading only: no wallet, no keys, no real orders."""

import logging

PAPER_LABEL = "Paper trading · live market data"

# httpx logs full request URLs at INFO, and the Telegram URL contains the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
