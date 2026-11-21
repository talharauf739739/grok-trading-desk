"""Hard limit on Grok usage. When the limit is reached, Grok stops until the next UTC day.

Three stops:
  1. A daily call cap (GROK_DAILY_CALL_LIMIT), counted before each request.
  2. If xAI says the account has no credits or the key is refused (HTTP 401/402/403),
     Grok pauses until the next UTC day.
  3. If xAI rate-limits (HTTP 429), Grok pauses for 15 minutes.

While paused, the desk keeps running on the free data sources and blocks every token
with the reason "Grok paused". It never retries in a loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import DB

RATE_LIMIT_PAUSE = timedelta(minutes=15)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _next_utc_midnight() -> datetime:
    now = datetime.now(timezone.utc)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


class GrokBudget:
    def __init__(self, db: DB, daily_limit: int):
        self.db = db
        self.daily_limit = max(0, int(daily_limit))

    def used_today(self) -> int:
        return int(self.db.get_kv(f"grok_calls:{_today()}") or 0)

    def paused_until(self) -> tuple[datetime, str] | None:
        until = self.db.get_kv("grok_paused_until")
        if not until:
            return None
        ts = datetime.fromisoformat(until)
        if ts <= datetime.now(timezone.utc):
            return None
        return ts, self.db.get_kv("grok_paused_reason") or "paused"

    def blocked_reason(self) -> str | None:
        if self.daily_limit == 0:
            return "Grok disabled (GROK_DAILY_CALL_LIMIT=0)"
        if self.used_today() >= self.daily_limit:
            return f"daily Grok limit reached ({self.daily_limit} calls); resumes 00:00 UTC"
        paused = self.paused_until()
        if paused:
            return f"{paused[1]}; resumes {paused[0].strftime('%H:%M')} UTC"
        return None

    def record_call(self) -> int:
        return self.db.incr_kv(f"grok_calls:{_today()}")

    def pause(self, reason: str, *, until: datetime | None = None) -> None:
        until = until or _next_utc_midnight()
        self.db.set_kv("grok_paused_until", until.isoformat())
        self.db.set_kv("grok_paused_reason", reason)

    def handle_http_error(self, status: int) -> str | None:
        """Pause on errors that would repeat. Returns the pause reason, if any."""
        if status in (401, 402, 403):
            reason = f"xAI refused the request (HTTP {status}: no credits or invalid key)"
            self.pause(reason)
            return reason
        if status == 429:
            reason = "xAI rate limit (HTTP 429)"
            self.pause(reason, until=datetime.now(timezone.utc) + RATE_LIMIT_PAUSE)
            return reason
        return None

    def status(self) -> dict:
        return {"used_today": self.used_today(), "daily_limit": self.daily_limit,
                "blocked_reason": self.blocked_reason()}
