"""Streamlit dashboard. Reads only from SQLite; every value is a real API result or paper record.

    streamlit run dashboard.py
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from desk import PAPER_LABEL
from desk.config import load_config
from desk.db import DB

st.set_page_config(page_title="Grok Trading Desk", page_icon="📈", layout="wide")

config = load_config()
db = DB(config.db_path)

st.markdown(
    """
    <style>
      .paper-label { display:inline-block; padding:6px 14px; border-radius:999px; font-weight:700;
        letter-spacing:.02em; background:#fff4d6; color:#7a5300; border:1px solid #f0d58a; }
      @media (prefers-color-scheme: dark) {
        .paper-label { background:#3a2f12; color:#f5cd6b; border-color:#6b5520; } }
      .agent { font-weight:600; text-transform:uppercase; font-size:.75rem; letter-spacing:.05em; }
    </style>
    """,
    unsafe_allow_html=True,
)

head_l, head_r = st.columns([3, 2])
head_l.title("Grok Multi-Agent Trading Desk")
head_l.caption("Scanner → Analyzer (Grok) → Risk agent → Paper executor → Notifier · Position monitor")
head_r.markdown(f"<div style='text-align:right;padding-top:28px'><span class='paper-label'>"
                f"{PAPER_LABEL}</span></div>", unsafe_allow_html=True)


_MD_SPECIAL = str.maketrans({c: "\\" + c for c in "\\`*_{}[]()#+-.!|<>~$"})


def safe(text: str | None) -> str:
    """Token names, descriptions and Grok output are untrusted: neutralize HTML and markdown."""
    # quote=False: only &, <, > become entities, so no '#' for the markdown escaping to break
    return html.escape(str(text or ""), quote=False).translate(_MD_SPECIAL)


def ago(ts: str | None) -> str:
    if not ts:
        return "never"
    s = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
    if s < 60:
        return f"{s:.0f}s ago"
    if s < 3600:
        return f"{s / 60:.0f}m ago"
    return f"{s / 3600:.1f}h ago"


def money(v: float | None) -> str:
    return "–" if v is None else f"${v:,.2f}"


def price(v: float | None) -> str:
    return "–" if v is None else f"${v:.8g}"


AGENT_ICON = {"scanner": "🔎", "analyzer": "🧠", "risk": "🛡️", "executor": "📝",
              "notifier": "📨", "monitor": "⏱️", "desk": "⚙️"}


@st.fragment(run_every=3)
def live() -> None:
    acct = db.account(config.paper_bankroll_usd)
    logs = db.recent_logs(1)
    k = st.columns(5)
    k[0].metric("Paper equity", money(acct["equity_usd"]),
                f"{acct['equity_usd'] - acct['bankroll_usd']:+,.2f} vs ${acct['bankroll_usd']:,.0f} start")
    k[1].metric("Paper cash", money(acct["cash_usd"]))
    k[2].metric("Open positions", acct["open_positions"],
                f"{acct['unrealized_pnl_usd']:+,.2f} unrealized" if acct["open_positions"] else None)
    k[3].metric("Closed trades", acct["closed_trades"],
                f"{acct['realized_pnl_usd']:+,.2f} realized" if acct["closed_trades"] else None)
    k[4].metric("Last agent activity", ago(logs[0]["ts"]) if logs else "never")

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("Open paper positions")
        trades = db.open_trades()
        if not trades:
            st.info("No open paper positions yet.")
        else:
            rows = []
            for t in trades:
                last = t["last_price_usd"]
                value = t["qty"] * last if last else None
                rows.append({
                    "Token": t["symbol"], "Size": money(t["size_usd"]),
                    "Entry": price(t["entry_price_usd"]), "Last": price(last),
                    "P&L": f"{(value - t['size_usd']):+,.2f} ({(value / t['size_usd'] - 1) * 100:+.1f}%)" if value else "–",
                    "Stop": price(t["stop_price_usd"]), "Target": price(t["target_price_usd"]),
                    "Priced": ago(t["last_checked_at"]), "Opened": ago(t["opened_at"]),
                    "Chart": t["pair_url"],
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={"Chart": st.column_config.LinkColumn("Chart", display_text="DexScreener")})

        st.subheader("Token pipeline")
        tokens = db.recent_tokens(12)
        if not tokens:
            st.info("Waiting for the scanner to find new Solana tokens.")
        for tk in tokens:
            status = tk["status"]
            badge = {"traded": "🟢 paper trade opened", "approved": "🟢 approved",
                     "blocked": "🔴 blocked by risk agent", "analyzed": "🟡 analyzed",
                     "seen": "⚪ queued", "error": "⚠️ error"}.get(status, status)
            with st.container(border=True):
                a, b = st.columns([3, 2])
                a.markdown(f"**{safe(tk['symbol'] or tk['token_address'][:8])}** · {safe(tk['name'])}")
                b.markdown(f"<div style='text-align:right'>{badge}</div>", unsafe_allow_html=True)
                if tk["grok_summary"]:
                    conf = f" · {tk['grok_confidence']:.0%}" if tk["grok_confidence"] is not None else ""
                    st.markdown(f"🧠 **Grok ({safe(tk['grok_verdict'])}{conf}):** {safe(tk['grok_summary'])}")
                reasons = json.loads(tk["risk_reasons"]) if tk["risk_reasons"] else []
                if status == "blocked" and reasons:
                    st.markdown("🛡️ " + " · ".join(safe(r) for r in reasons))
                if tk["pair_url"]:
                    st.caption(f"[DexScreener]({tk['pair_url']}) · seen {ago(tk['first_seen_at'])}")

    with right:
        st.subheader("Agent log")
        entries = db.recent_logs(40)
        if not entries:
            st.info("No agent activity yet. Start the desk with `python run_desk.py`.")
        for e in entries:
            icon = AGENT_ICON.get(e["agent"], "•")
            sym = f" <b>{safe(e['symbol'])}</b>" if e["symbol"] else ""
            st.markdown(f"{icon} <span class='agent'>{e['agent']}</span>{sym} · "
                        f"<small>{ago(e['ts'])}</small><br>{safe(e['message'])}", unsafe_allow_html=True)

    st.subheader("Closed paper trades")
    closed = db.closed_trades(50)
    if not closed:
        st.info("No closed paper trades yet.")
    else:
        st.dataframe(pd.DataFrame([{
            "Token": t["symbol"], "Size": money(t["size_usd"]),
            "Entry": price(t["entry_price_usd"]), "Exit": price(t["exit_price_usd"]),
            "P&L": f"{t['pnl_usd']:+,.2f}", "P&L %": f"{t['pnl_pct']:+.1f}%",
            "Reason": t["exit_reason"], "Closed": ago(t["closed_at"]),
        } for t in closed]), hide_index=True, width="stretch")

    st.caption(f"{PAPER_LABEL}. Prices from DexScreener, safety data from RugCheck, analysis by "
               f"xAI Grok ({config.xai_model}). Simulated fills include {config.paper_slippage_pct:g}% "
               "slippage each way. No wallet is connected and no real orders are placed. Not financial advice.")


live()
