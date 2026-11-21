"""SQLite store: agent_log, tokens, trades. The dashboard reads only from here.

Nothing in this module creates example or seeded rows. Every row is written by an
agent reacting to a real API response or a real paper fill.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    agent         TEXT NOT NULL,
    event         TEXT NOT NULL,
    token_address TEXT,
    symbol        TEXT,
    message       TEXT NOT NULL,
    data          TEXT
);
CREATE INDEX IF NOT EXISTS agent_log_ts ON agent_log(id DESC);

CREATE TABLE IF NOT EXISTS tokens (
    token_address   TEXT PRIMARY KEY,
    symbol          TEXT,
    name            TEXT,
    first_seen_at   TEXT NOT NULL,
    pair_address    TEXT,
    pair_url        TEXT,
    status          TEXT NOT NULL,      -- seen | skipped | analyzed | approved | blocked | traded | error
    grok_summary    TEXT,
    grok_verdict    TEXT,
    grok_confidence REAL,
    risk_reasons    TEXT,               -- JSON list
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    token_address   TEXT NOT NULL,
    symbol          TEXT,
    pair_address    TEXT NOT NULL,
    pair_url        TEXT,
    status          TEXT NOT NULL,      -- open | closed
    opened_at       TEXT NOT NULL,
    quote_price_usd REAL NOT NULL,      -- live DexScreener price at entry
    entry_price_usd REAL NOT NULL,      -- after paper slippage
    size_usd        REAL NOT NULL,
    qty             REAL NOT NULL,
    stop_price_usd  REAL NOT NULL,
    target_price_usd REAL NOT NULL,
    last_price_usd  REAL,
    last_checked_at TEXT,
    closed_at       TEXT,
    exit_quote_usd  REAL,
    exit_price_usd  REAL,
    exit_reason     TEXT,
    pnl_usd         REAL,
    pnl_pct         REAL,
    grok_summary    TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._memory = sqlite3.connect(path, check_same_thread=False) if path == ":memory:" else None
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        if self._memory is not None:
            c = self._memory
        else:
            c = sqlite3.connect(self.path, timeout=15)
            c.execute("PRAGMA journal_mode=WAL")
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            if self._memory is None:
                c.close()

    # -- agent log -------------------------------------------------------------
    def log(self, agent: str, event: str, message: str, *, token_address: str | None = None,
            symbol: str | None = None, data: dict | None = None) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO agent_log(ts, agent, event, token_address, symbol, message, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now_iso(), agent, event, token_address, symbol, message,
                 json.dumps(data, default=str) if data is not None else None),
            )

    def recent_logs(self, limit: int = 100) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM agent_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # -- tokens ----------------------------------------------------------------
    def is_seen(self, token_address: str) -> bool:
        with self.conn() as c:
            return c.execute("SELECT 1 FROM tokens WHERE token_address = ?",
                             (token_address,)).fetchone() is not None

    def upsert_token(self, token_address: str, **fields) -> None:
        fields["updated_at"] = now_iso()
        if "risk_reasons" in fields and not isinstance(fields["risk_reasons"], (str, type(None))):
            fields["risk_reasons"] = json.dumps(fields["risk_reasons"])
        with self.conn() as c:
            exists = c.execute("SELECT 1 FROM tokens WHERE token_address = ?",
                               (token_address,)).fetchone()
            if exists:
                sets = ", ".join(f"{k} = ?" for k in fields)
                c.execute(f"UPDATE tokens SET {sets} WHERE token_address = ?",
                          (*fields.values(), token_address))
            else:
                fields.setdefault("status", "seen")
                fields["first_seen_at"] = now_iso()
                cols = ", ".join(["token_address", *fields])
                marks = ", ".join("?" * (len(fields) + 1))
                c.execute(f"INSERT INTO tokens({cols}) VALUES ({marks})",
                          (token_address, *fields.values()))

    def recent_tokens(self, limit: int = 30) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM tokens WHERE status != 'skipped' ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- trades ----------------------------------------------------------------
    def open_trade(self, **t) -> int:
        t.setdefault("status", "open")
        t.setdefault("opened_at", now_iso())
        t.setdefault("last_price_usd", t.get("quote_price_usd"))
        t.setdefault("last_checked_at", t["opened_at"])
        cols = ", ".join(t)
        marks = ", ".join("?" * len(t))
        with self.conn() as c:
            cur = c.execute(f"INSERT INTO trades({cols}) VALUES ({marks})", tuple(t.values()))
            return int(cur.lastrowid)

    def get_trade(self, trade_id: int) -> dict | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None

    def open_trades(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM trades WHERE status = 'open' ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def closed_trades(self, limit: int = 100) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM trades WHERE status = 'closed' ORDER BY closed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def has_traded(self, token_address: str) -> bool:
        with self.conn() as c:
            return c.execute("SELECT 1 FROM trades WHERE token_address = ?",
                             (token_address,)).fetchone() is not None

    def mark_price(self, trade_id: int, price_usd: float) -> None:
        with self.conn() as c:
            c.execute("UPDATE trades SET last_price_usd = ?, last_checked_at = ? WHERE id = ?",
                      (price_usd, now_iso(), trade_id))

    def close_trade(self, trade_id: int, *, exit_quote_usd: float, exit_price_usd: float,
                    reason: str) -> dict:
        with self.conn() as c:
            t = c.execute("SELECT * FROM trades WHERE id = ? AND status = 'open'",
                          (trade_id,)).fetchone()
            if t is None:
                raise ValueError(f"trade {trade_id} is not open")
            proceeds = t["qty"] * exit_price_usd
            pnl = proceeds - t["size_usd"]
            c.execute(
                """UPDATE trades SET status = 'closed', closed_at = ?, exit_quote_usd = ?,
                   exit_price_usd = ?, exit_reason = ?, pnl_usd = ?, pnl_pct = ?,
                   last_price_usd = ?, last_checked_at = ? WHERE id = ?""",
                (now_iso(), exit_quote_usd, exit_price_usd, reason, pnl,
                 pnl / t["size_usd"] * 100, exit_quote_usd, now_iso(), trade_id),
            )
        return self.get_trade(trade_id)

    # -- paper account ---------------------------------------------------------
    def account(self, bankroll_usd: float) -> dict:
        """Paper account derived from trade records only."""
        with self.conn() as c:
            closed = c.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(pnl_usd), 0) pnl, "
                "COALESCE(SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END), 0) wins "
                "FROM trades WHERE status = 'closed'"
            ).fetchone()
            open_ = c.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(size_usd), 0) committed, "
                "COALESCE(SUM(qty * COALESCE(last_price_usd, entry_price_usd)), 0) value "
                "FROM trades WHERE status = 'open'"
            ).fetchone()
        realized = float(closed["pnl"])
        committed = float(open_["committed"])
        open_value = float(open_["value"])
        cash = bankroll_usd + realized - committed
        return {
            "bankroll_usd": bankroll_usd,
            "cash_usd": cash,
            "open_positions": int(open_["n"]),
            "committed_usd": committed,
            "open_value_usd": open_value,
            "unrealized_pnl_usd": open_value - committed,
            "realized_pnl_usd": realized,
            "equity_usd": cash + open_value,
            "closed_trades": int(closed["n"]),
            "wins": int(closed["wins"]),
        }
