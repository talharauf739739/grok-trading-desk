"""Streamlit dashboard. Reads only from SQLite; every value is a real API result or paper record.

    streamlit run dashboard.py

With EMBED_AGENTS=true (used on Streamlit Community Cloud) this process also runs the agents.
"""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Grok Trading Desk · paper trading", page_icon="🤖", layout="wide")


def _secrets_to_env() -> None:
    """On Streamlit Cloud, keys live in the app's Secrets. Expose root-level ones as env vars."""
    try:
        for key, value in st.secrets.items():
            if isinstance(value, (str, int, float, bool)) and not os.getenv(key):
                os.environ[key] = str(value)
    except Exception:  # no secrets file locally: .env is used instead
        pass


_secrets_to_env()

from desk import PAPER_LABEL  # noqa: E402  (env must be populated first)
from desk.budget import GrokBudget  # noqa: E402
from desk.config import load_config  # noqa: E402
from desk.db import DB  # noqa: E402

config = load_config()
db = DB(config.db_path)


@st.cache_resource(show_spinner=False)
def _embedded_desk():
    from desk.pipeline import Desk
    desk = Desk(config, db=db)
    desk.start_background()
    return desk


if config.embed_agents:
    _embedded_desk()

esc = html.escape

# ---------------------------------------------------------------------------------- style
st.html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;600;700&display=swap');
:root { --bg:#06080c; --panel:#0d1117; --panel2:#111823; --line:#1d2633; --text:#e6edf3; --muted:#7d8a99;
        --green:#00e38c; --red:#ff4d5e; --amber:#ffb020; --violet:#a78bfa; --cyan:#22d3ee; }
.stApp { background: radial-gradient(1100px 520px at 0% -10%, rgba(0,227,140,.07), transparent 60%),
                     radial-gradient(900px 480px at 100% -5%, rgba(167,139,250,.09), transparent 60%), var(--bg); }
.block-container { padding-top: 1.2rem; max-width: 1500px; }
header[data-testid="stHeader"] { background: transparent; }
.mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
.gd-head { display:flex; flex-wrap:wrap; gap:14px; align-items:center; justify-content:space-between;
           padding:14px 18px; border:1px solid var(--line); border-radius:16px;
           background:linear-gradient(180deg, rgba(17,24,35,.9), rgba(13,17,23,.9)); }
.gd-brand { font-family:Inter, sans-serif; font-weight:800; font-size:26px; letter-spacing:-.02em; line-height:1.1;
            background:linear-gradient(90deg, #fff 0%, #9ff5cf 45%, #c4b5fd 100%);
            -webkit-background-clip:text; background-clip:text; color:transparent; }
.gd-sub { color:var(--muted); font-size:13px; margin-top:4px; }
.gd-pills { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.pill { font-family:'JetBrains Mono', monospace; font-size:12px; font-weight:600; padding:6px 12px; border-radius:999px;
        border:1px solid var(--line); background:var(--panel); color:var(--text); white-space:nowrap; }
.pill.paper { background:rgba(255,176,32,.12); color:var(--amber); border-color:rgba(255,176,32,.45); }
.pill.live  { color:var(--green); border-color:rgba(0,227,140,.45); }
.pill.idle  { color:var(--muted); }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:currentColor; margin-right:7px; vertical-align:1px; }
.live .dot { animation: pulse 1.4s infinite; box-shadow:0 0 0 0 rgba(0,227,140,.6); }
@keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(0,227,140,.6)} 70%{box-shadow:0 0 0 9px rgba(0,227,140,0)} 100%{box-shadow:0 0 0 0 rgba(0,227,140,0)} }
.meter { display:inline-block; width:70px; height:6px; border-radius:3px; background:var(--line); margin-left:8px; vertical-align:1px; overflow:hidden; }
.meter > i { display:block; height:100%; background:linear-gradient(90deg, var(--violet), var(--cyan)); }

.pipe { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:10px; margin:14px 0 4px; }
.agent { position:relative; padding:12px 14px; border-radius:14px; border:1px solid var(--line); background:var(--panel); min-height:132px; }
.agent.active { border-color:rgba(0,227,140,.7); box-shadow:0 0 0 1px rgba(0,227,140,.25), 0 0 28px rgba(0,227,140,.15); }
.agent .top { display:flex; justify-content:space-between; align-items:center; }
.agent .name { font-family:'JetBrains Mono', monospace; font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
.agent .icon { font-size:18px; }
.agent .count { font-family:'JetBrains Mono', monospace; font-size:26px; font-weight:700; margin-top:6px; }
.agent .unit { font-size:11px; color:var(--muted); }
.agent .msg { font-size:12px; color:var(--muted); margin-top:6px; line-height:1.35; overflow:hidden;
              display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
.agent .ago { position:absolute; top:12px; right:40px; font-size:10px; color:var(--muted); font-family:'JetBrains Mono', monospace; }
.c-scanner{color:var(--cyan)} .c-analyzer{color:var(--violet)} .c-risk{color:var(--amber)}
.c-executor{color:var(--green)} .c-notifier{color:#60a5fa} .c-monitor{color:#f472b6} .c-desk{color:var(--muted)}

.card { border:1px solid var(--line); border-radius:16px; background:var(--panel); padding:16px 18px; }
.card h3 { margin:0 0 10px; font-size:13px; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); font-family:'JetBrains Mono', monospace; }
.spot-top { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; flex-wrap:wrap; }
.spot-sym { font-family:Inter, sans-serif; font-size:30px; font-weight:800; letter-spacing:-.02em; }
.spot-name { color:var(--muted); font-size:13px; }
.stamp { font-family:'JetBrains Mono', monospace; font-weight:800; font-size:18px; letter-spacing:.12em; padding:8px 16px;
         border-radius:10px; border:2px solid currentColor; transform:rotate(-3deg); }
.stamp.blocked { color:var(--red); background:rgba(255,77,94,.08); }
.stamp.approved { color:var(--green); background:rgba(0,227,140,.08); }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
.chip { font-family:'JetBrains Mono', monospace; font-size:12px; padding:6px 10px; border-radius:8px; background:var(--panel2); border:1px solid var(--line); }
.chip b { color:var(--muted); font-weight:400; margin-right:6px; }
.checks { display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:6px 14px; margin:8px 0 12px; }
.ck { font-size:13px; }
.ck.ok::before { content:'✓'; color:var(--green); font-weight:700; margin-right:8px; }
.ck.no::before { content:'✗'; color:var(--red); font-weight:700; margin-right:8px; }
.ck.no { color:#ffc2c8; }
.grok { border:1px solid rgba(167,139,250,.35); background:linear-gradient(180deg, rgba(167,139,250,.09), rgba(167,139,250,.03));
        border-radius:12px; padding:12px 14px; }
.grok .who { font-family:'JetBrains Mono', monospace; font-size:12px; color:var(--violet); font-weight:700; letter-spacing:.06em; margin-bottom:6px; }
.grok p { margin:0; line-height:1.5; }
.flags { margin-top:8px; font-size:12px; color:var(--muted); }
.timeline { margin-top:12px; border-left:2px solid var(--line); padding-left:12px; }
.tl { font-size:12px; margin:6px 0; color:var(--muted); }
.tl .t { font-family:'JetBrains Mono', monospace; color:#9aa6b2; margin-right:8px; }

.term { font-family:'JetBrains Mono', monospace; font-size:12px; line-height:1.55; height:560px; overflow-y:auto;
        background:#05070a; border:1px solid var(--line); border-radius:12px; padding:10px 12px; }
.term .ln { padding:3px 0; border-bottom:1px dashed rgba(125,138,153,.12); }
.term .ts { color:#56606c; margin-right:8px; }
.term .ag { font-weight:700; margin-right:6px; }
.term .sym { color:#fff; margin-right:6px; }
.term .ev-blocked { color:#ffb3bb; } .term .ev-approved, .term .ev-paper_open { color:#8ff7c6; }
.term .ev-grok_analysis { color:#d9ccff; }

.tokens { display:grid; gap:6px; }
.tok { display:flex; justify-content:space-between; gap:10px; padding:8px 10px; border-radius:10px; background:var(--panel2); font-size:13px; }
.tok .s { font-weight:700; }
.tok .r { color:var(--muted); font-size:12px; text-align:right; }
.st { font-family:'JetBrains Mono', monospace; font-size:11px; font-weight:700; padding:2px 8px; border-radius:6px; }
.st.blocked{color:var(--red); background:rgba(255,77,94,.1)} .st.traded,.st.approved{color:var(--green); background:rgba(0,227,140,.1)}
.st.analyzed,.st.seen{color:var(--muted); background:var(--line)} .st.error{color:var(--amber); background:rgba(255,176,32,.1)}

[data-testid="stMetric"] { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:12px 16px; }
[data-testid="stMetricValue"] { font-family:'JetBrains Mono', monospace; }
.foot { color:var(--muted); font-size:12px; text-align:center; margin:18px 0 6px; line-height:1.6; }
.foot b { color:var(--text); }
.empty { color:var(--muted); font-size:13px; padding:18px 0; text-align:center; }
</style>
""")

# -------------------------------------------------------------------------------- helpers
AGENTS = [
    ("scanner", "🔎", "Scanner", "new tokens"),
    ("analyzer", "🧠", "Grok analyst", "explained"),
    ("risk", "🛡️", "Risk agent", "decisions"),
    ("executor", "📝", "Paper executor", "paper trades"),
    ("notifier", "📨", "Telegram", "alerts"),
    ("monitor", "⏱️", "Position monitor", "open"),
]


def parse_ts(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


def ago(ts: str | None) -> str:
    t = parse_ts(ts)
    if not t:
        return "never"
    s = (datetime.now(timezone.utc) - t).total_seconds()
    if s < 60:
        return f"{max(s, 0):.0f}s ago"
    if s < 3600:
        return f"{s / 60:.0f}m ago"
    return f"{s / 3600:.1f}h ago"


def money(v: float | None) -> str:
    return "–" if v is None else f"${v:,.2f}"


def price(v: float | None) -> str:
    return "–" if v is None else f"${v:.6g}"


def compact(v: float | None) -> str:
    if v is None:
        return "–"
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"${v / div:.1f}{suf}"
    return f"${v:,.0f}"


def clip(text: str | None, n: int) -> str:
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1] + "…"


# ------------------------------------------------------------------------------- sections
def header() -> None:
    last = db.recent_logs(1)
    last_t = parse_ts(last[0]["ts"]) if last else None
    window = max(config.scan_interval_s, config.monitor_interval_s) * 2.5
    live = bool(last_t and (datetime.now(timezone.utc) - last_t).total_seconds() < window)
    b = GrokBudget(db, config.grok_daily_call_limit).status()
    used, limit = b["used_today"], b["daily_limit"]
    pct = min(100, used / limit * 100) if limit else 100
    grok_txt = f"Grok {used}/{limit} today" if not b["blocked_reason"] else "Grok paused"
    st.html(f"""
    <div class="gd-head">
      <div>
        <div class="gd-brand">Grok Multi-Agent Trading Desk</div>
        <div class="gd-sub">Six AI agents watch new Solana tokens: scan → explain → risk-check → paper trade → alert</div>
      </div>
      <div class="gd-pills">
        <span class="pill paper">{esc(PAPER_LABEL)}</span>
        <span class="pill {'live' if live else 'idle'}"><span class="dot"></span>{'LIVE' if live else 'IDLE'} · {esc(ago(last[0]['ts']) if last else 'no activity yet')}</span>
        <span class="pill" title="{esc(b['blocked_reason'] or 'daily Grok call budget')}">{esc(grok_txt)}<span class="meter"><i style="width:{pct:.0f}%"></i></span></span>
      </div>
    </div>""")


def pipeline() -> None:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    n = db.counts_since(since)
    last = db.last_event_by_agent()
    acct = db.account(config.paper_bankroll_usd)
    counts = {
        "scanner": n.get("scanner.new_token", 0),
        "analyzer": n.get("analyzer.grok_analysis", 0),
        "risk": n.get("risk.blocked", 0) + n.get("risk.approved", 0),
        "executor": n.get("executor.paper_open", 0),
        "notifier": n.get("notifier.sent", 0),
        "monitor": acct["open_positions"],
    }
    risk_unit = f"{n.get('risk.blocked', 0)} blocked · {n.get('risk.approved', 0)} approved"
    cards = []
    now = datetime.now(timezone.utc)
    for key, icon, title, unit in AGENTS:
        ev = last.get(key)
        active = bool(ev and (now - parse_ts(ev["ts"])).total_seconds() < 12)
        msg = clip(ev["message"], 120) if ev else "waiting…"
        cards.append(f"""
        <div class="agent {'active' if active else ''}">
          <div class="top"><span class="name c-{key}">{esc(title)}</span><span class="icon">{icon}</span></div>
          <span class="ago">{esc(ago(ev['ts']) if ev else '')}</span>
          <div class="count">{counts[key]}</div>
          <div class="unit">{esc(risk_unit if key == 'risk' else unit + (' (24h)' if key != 'monitor' else ''))}</div>
          <div class="msg">{esc(msg)}</div>
        </div>""")
    st.html(f'<div class="pipe">{"".join(cards)}</div>')


def spotlight() -> None:
    tk = db.latest_decision_token()
    if not tk:
        st.html('<div class="card"><h3>Latest decision</h3><div class="empty">Waiting for the first token to reach the risk agent…</div></div>')
        return
    events = db.token_events(tk["token_address"])
    facts, checks, grok = {}, [], None
    for e in events:
        data = json.loads(e["data"]) if e["data"] else None
        if e["event"] == "new_token" and data:
            facts = data
        elif e["event"] in ("blocked", "approved") and data:
            checks = data.get("checks", [])
        elif e["event"] == "grok_analysis" and data:
            grok = data
    approved = tk["status"] in ("approved", "traded")
    stamp = '<span class="stamp approved">APPROVED</span>' if approved else '<span class="stamp blocked">BLOCKED</span>'
    chips = [("price", price(facts.get("price_usd"))), ("liquidity", compact(facts.get("liquidity_usd"))),
             ("FDV", compact(facts.get("fdv_usd"))), ("vol 1h", compact(facts.get("volume_h1_usd"))),
             ("buys/sells 1h", f"{facts.get('buys_h1', '–')}/{facts.get('sells_h1', '–')}"),
             ("pool age", f"{facts['pair_age_minutes']:.0f} min" if facts.get("pair_age_minutes") is not None else "–"),
             ("dex", facts.get("dex") or "–")]
    chip_html = "".join(f'<span class="chip"><b>{esc(k)}</b>{esc(str(v))}</span>' for k, v in chips)
    check_html = "".join(f'<div class="ck {"ok" if c["passed"] else "no"}">{esc(c["detail"])}</div>' for c in checks)
    if grok:
        flags = ""
        if grok.get("red_flags"):
            flags += "🚩 " + esc(" · ".join(grok["red_flags"][:4]))
        if grok.get("green_flags"):
            flags += ("<br>" if flags else "") + "✅ " + esc(" · ".join(grok["green_flags"][:4]))
        grok_html = (f'<div class="grok"><div class="who">GROK · {esc(grok["verdict"].upper())} · '
                     f'{grok["confidence"]:.0%} CONFIDENCE</div><p>{esc(grok["summary"])}</p>'
                     f'{f"<div class=flags>{flags}</div>" if flags else ""}</div>')
    else:
        note = next((c["detail"] for c in checks if c["rule"] == "grok"), "no Grok analysis")
        grok_html = f'<div class="grok"><div class="who">GROK</div><p style="color:var(--muted)">{esc(note)}</p></div>'
    tl = "".join(
        f'<div class="tl"><span class="t">{esc(parse_ts(e["ts"]).strftime("%H:%M:%S"))}</span>'
        f'<span class="c-{esc(e["agent"])}">{esc(e["agent"])}</span> · {esc(clip(e["message"], 110))}</div>'
        for e in events[-7:])
    link = (f' · <a href="{esc(tk["pair_url"])}" target="_blank" style="color:var(--cyan)">DexScreener ↗</a>'
            if (tk.get("pair_url") or "").startswith("https://dexscreener.com/") else "")
    st.html(f"""
    <div class="card">
      <h3>Latest decision · {esc(ago(tk['updated_at']))}</h3>
      <div class="spot-top">
        <div><div class="spot-sym">{esc(tk['symbol'] or tk['token_address'][:8])}</div>
             <div class="spot-name">{esc(clip(tk['name'], 60))} · <span class="mono">{esc(tk['token_address'][:6])}…{esc(tk['token_address'][-4:])}</span>{link}</div></div>
        {stamp}
      </div>
      <div class="chips">{chip_html}</div>
      {grok_html}
      <div class="checks">{check_html}</div>
      <div class="timeline">{tl}</div>
    </div>""")


def terminal() -> None:
    rows = db.recent_logs(80)
    if not rows:
        body = '<div class="empty">No agent activity yet.</div>'
    else:
        lines = []
        for r in rows:
            sym = f'<span class="sym">{esc(r["symbol"])}</span>' if r["symbol"] else ""
            lines.append(
                f'<div class="ln ev-{esc(r["event"])}"><span class="ts">{esc(parse_ts(r["ts"]).strftime("%H:%M:%S"))}</span>'
                f'<span class="ag c-{esc(r["agent"])}">{esc(r["agent"].upper())}</span>{sym}'
                f'{esc(clip(r["message"], 260))}</div>')
        body = "".join(lines)
    st.html(f'<div class="card"><h3>Agent terminal</h3><div class="term">{body}</div></div>')


def kpis() -> None:
    a = db.account(config.paper_bankroll_usd)
    k = st.columns(5)
    k[0].metric("Paper equity", money(a["equity_usd"]),
                f"{a['equity_usd'] - a['bankroll_usd']:+,.2f} vs start" if a["closed_trades"] or a["open_positions"] else None)
    k[1].metric("Paper cash", money(a["cash_usd"]))
    k[2].metric("Open positions", a["open_positions"],
                f"{a['unrealized_pnl_usd']:+,.2f} unrealized" if a["open_positions"] else None)
    k[3].metric("Realized P&L", money(a["realized_pnl_usd"]) if a["closed_trades"] else "–")
    k[4].metric("Closed trades", a["closed_trades"],
                f"{a['wins']} profitable" if a["closed_trades"] else None, delta_color="off")


def equity_chart() -> None:
    curve = db.equity_curve()
    if len(curve) < 2:
        st.html('<div class="card"><h3>Paper equity</h3><div class="empty">The equity curve starts after the first paper trade.</div></div>')
        return
    df = pd.DataFrame(curve)
    df["ts"] = pd.to_datetime(df["ts"])
    st.markdown("###### PAPER EQUITY")
    st.area_chart(df, x="ts", y="equity_usd", color="#00e38c", height=220, x_label="", y_label="USD")


def positions() -> None:
    trades = db.open_trades()
    st.markdown("###### OPEN PAPER POSITIONS")
    if not trades:
        st.html('<div class="card"><div class="empty">No open paper positions. The risk agent blocks most new tokens, as it should.</div></div>')
        return
    rows = []
    for t in trades:
        last = t["last_price_usd"]
        value = t["qty"] * last if last else None
        rows.append({
            "Token": t["symbol"], "Price": db.price_ticks(t["id"]),
            "P&L %": (value / t["size_usd"] - 1) * 100 if value else None,
            "P&L $": value - t["size_usd"] if value else None,
            "Entry": price(t["entry_price_usd"]), "Last": price(last),
            "Stop": price(t["stop_price_usd"]), "Target": price(t["target_price_usd"]),
            "Opened": ago(t["opened_at"]), "Chart": t["pair_url"],
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "Price": st.column_config.LineChartColumn("Live price", width="medium"),
        "P&L %": st.column_config.NumberColumn(format="%+.1f%%"),
        "P&L $": st.column_config.NumberColumn(format="$%+.2f"),
        "Chart": st.column_config.LinkColumn("Chart", display_text="DexScreener"),
    })


def token_stream() -> None:
    tokens = db.recent_tokens(10)
    if not tokens:
        body = '<div class="empty">Waiting for the scanner…</div>'
    else:
        items = []
        for tk in tokens:
            reasons = json.loads(tk["risk_reasons"]) if tk["risk_reasons"] else []
            label = {"traded": "PAPER TRADE", "approved": "APPROVED", "blocked": "BLOCKED",
                     "analyzed": "ANALYZING", "seen": "QUEUED", "error": "ERROR"}.get(tk["status"], tk["status"].upper())
            items.append(
                f'<div class="tok"><div><span class="s">{esc(clip(tk["symbol"] or tk["token_address"][:6], 14))}</span> '
                f'<span class="st {esc(tk["status"])}">{esc(label)}</span></div>'
                f'<div class="r">{esc(clip(reasons[0], 60)) if reasons and tk["status"] == "blocked" else ""}'
                f'<br>{esc(ago(tk["updated_at"]))}</div></div>')
        body = f'<div class="tokens">{"".join(items)}</div>'
    st.html(f'<div class="card"><h3>Token stream</h3>{body}</div>')


def closed_trades() -> None:
    closed = db.closed_trades(50)
    if not closed:
        return
    st.markdown("###### CLOSED PAPER TRADES")
    st.dataframe(pd.DataFrame([{
        "Token": t["symbol"], "Size": money(t["size_usd"]), "Entry": price(t["entry_price_usd"]),
        "Exit": price(t["exit_price_usd"]), "P&L $": t["pnl_usd"], "P&L %": t["pnl_pct"],
        "Reason": t["exit_reason"], "Closed": ago(t["closed_at"]),
    } for t in closed]), hide_index=True, width="stretch", column_config={
        "P&L $": st.column_config.NumberColumn(format="$%+.2f"),
        "P&L %": st.column_config.NumberColumn(format="%+.1f%%"),
    })


def footer() -> None:
    by = f" · Built by <b>{esc(config.built_by)}</b>, multi-agent automation" if config.built_by else ""
    st.html(f"""<div class="foot"><b>{esc(PAPER_LABEL)}</b>. Prices: DexScreener · Safety: RugCheck ·
      Analysis: xAI Grok ({esc(config.xai_model)}). Simulated fills include {config.paper_slippage_pct:g}% slippage each way.
      No wallet is connected and no real orders are placed. Not financial advice.{by}</div>""")


# -------------------------------------------------------------------------------- layout
@st.fragment(run_every=3)
def live() -> None:
    header()
    pipeline()
    left, right = st.columns([3, 2], gap="medium")
    with left:
        spotlight()
    with right:
        terminal()
    kpis()
    c1, c2 = st.columns([3, 2], gap="medium")
    with c1:
        equity_chart()
        positions()
    with c2:
        token_stream()
    closed_trades()
    footer()


live()
