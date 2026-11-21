from __future__ import annotations

import logging

from ..config import Config
from ..db import DB


class Agent:
    """An agent is one stage of the desk. Everything it does is written to agent_log."""

    name = "agent"

    def __init__(self, db: DB, config: Config):
        self.db = db
        self.config = config
        self.logger = logging.getLogger(f"desk.{self.name}")

    def log(self, event: str, message: str, *, token: str | None = None,
            symbol: str | None = None, data: dict | None = None, level: int = logging.INFO) -> None:
        self.logger.log(level, "%s %s", f"[{symbol}]" if symbol else "", message)
        self.db.log(self.name, event, message, token_address=token, symbol=symbol, data=data)
