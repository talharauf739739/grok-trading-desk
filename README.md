# Grok Multi-Agent Trading Desk

**Paper trading · live market data.** A team of small agents watches newly listed Solana tokens.
Grok explains each one, a rule-based risk agent approves or blocks it, approved tokens get a
simulated (paper) trade at the live price, Telegram sends an alert, and a Streamlit dashboard
shows each step as it happens.

There is no wallet, no private key, no signing and no real orders. Nothing in this repo can send a
transaction. All P&L shown is simulated, and this is not financial advice.

## How it works

```
Scanner ──> Analyzer (Grok) ──> Risk agent ──> Paper executor ──> Notifier (Telegram)
   │              │                  │                │
   └──────────────┴──── agent_log + trades (SQLite) ──┴──> Dashboard (Streamlit)
                         Position monitor ──┘ (closes paper trades)
```

| Agent | What it does | Data source |
|---|---|---|
| Scanner | Polls the latest token profiles and keeps new Solana tokens whose main pool is under 24h old | DexScreener `token-profiles/latest/v1`, `token-pairs/v1` |
| Analyzer | Pulls the safety report, then asks Grok for a plain-English explanation, a verdict (`candidate` / `watch` / `avoid`) and a confidence score | RugCheck `/v1/tokens/{mint}/report`, xAI chat completions (structured JSON output) |
| Risk agent | Applies fixed rules. Grok's opinion counts as one input and cannot override a rule. Missing data counts as a failed check. | — |
| Paper executor | Re-fetches the live pool price and records a simulated buy with slippage | DexScreener |
| Position monitor | Re-prices open paper trades and closes them on the stop loss, take profit or time limit | DexScreener `tokens/v1` |
| Notifier | Sends Telegram alerts labelled `[PAPER TRADE · live market data]` | Telegram Bot API |

Every agent writes what it did to `agent_log`. The dashboard reads only from SQLite, so every
number on it comes from a real API response or a real paper-trade record. There is no seeded or
example data.

### Risk rules (defaults, all configurable)

A token is blocked if any of these is true:

- RugCheck reports it as rugged, lists a `danger` risk, or has no report
- The mint authority or freeze authority is still enabled
- The top 10 holders own more than 30% of supply (pool and AMM accounts are excluded)
- Less than 90% of LP is locked, or the lock status is unknown
- Pool liquidity is under $10,000, or unknown
- Grok's verdict is not `candidate`, its confidence is under 60%, or Grok is unavailable
- 5 paper positions are already open, paper cash is too low, or this token was already traded

### Paper fills

- Entry is the live DexScreener `priceUsd` plus 1% simulated slippage. Exit is the live price
  minus 1%.
- Each trade is $100 from a $1,000 paper bankroll.
- Exits: stop loss −25%, take profit +50%, or a time exit after 240 minutes.

### Grok budget (stops by itself)

Grok is the only part that can cost money, so it has three automatic stops:

1. Grok is only called for tokens that already pass the free safety checks (RugCheck +
   liquidity). Most new tokens fail those, so most tokens never reach Grok.
2. A hard daily cap, `GROK_DAILY_CALL_LIMIT` (default 30 calls per UTC day). At the cap,
   Grok stops until 00:00 UTC.
3. If xAI answers "no credits" or rejects the key (HTTP 401/402/403), Grok pauses until the next
   day. A rate limit (HTTP 429) pauses it for 15 minutes. It never retries in a loop.

While Grok is paused, the desk keeps running on the free data and blocks tokens with the reason
"Grok paused". The header shows calls used today. To make sure you are never billed, use prepaid
xAI credits with auto top-up turned off: when the credits run out, Grok simply stops.

## Free hosting on Streamlit Community Cloud

The dashboard can run the agents in the same process (`EMBED_AGENTS=true`), so the whole desk
runs as one free Streamlit app.

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app**, choose this repository, branch `master`, main file `dashboard.py`.
3. Under **Advanced settings**, pick Python 3.12 and paste the secrets:
   ```toml
   EMBED_AGENTS = "true"
   XAI_API_KEY = "your key"
   GROK_DAILY_CALL_LIMIT = "30"
   TELEGRAM_BOT_TOKEN = ""   # optional
   TELEGRAM_CHAT_ID = ""     # optional
   ```
4. Deploy. The agents start when the first visitor opens the app.

Things to know about the free tier: the app sleeps after 12 hours without visitors (agents
stop, so no Grok calls either), and its disk is wiped on restart, so paper-trade history starts
over after a reboot or redeploy. Visitors only read the dashboard; they cannot trigger Grok
calls or see your keys.

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

Fill in `.env`:

| Variable | Required | Notes |
|---|---|---|
| `XAI_API_KEY` | yes | From console.x.ai. Without it, every token is blocked as "no Grok analysis". |
| `XAI_MODEL` | no | Defaults to `grok-4.7`. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | no | Create a bot with @BotFather. If unset, alerts are off. |

Optional tuning, also via `.env`: `SCAN_INTERVAL_S`, `MONITOR_INTERVAL_S`, `MAX_ANALYSES_PER_SCAN`,
`MIN_LIQUIDITY_USD`, `MAX_TOP10_HOLDER_PCT`, `MIN_LP_LOCKED_PCT`, `MIN_GROK_CONFIDENCE`,
`MAX_OPEN_POSITIONS`, `PAPER_BANKROLL_USD`, `PAPER_TRADE_SIZE_USD`, `PAPER_SLIPPAGE_PCT`,
`STOP_LOSS_PCT`, `TAKE_PROFIT_PCT`, `MAX_HOLD_MINUTES`, `NOTIFY_BLOCKED`, `DESK_DB_PATH`,
`GROK_DAILY_CALL_LIMIT`, `EMBED_AGENTS`, `BUILT_BY`.

## Run

Use two terminals:

```bash
python run_desk.py              # agents: scan every 45s, re-price every 15s
streamlit run dashboard.py      # dashboard at http://localhost:8501
```

`python run_desk.py --once` runs a single scan and a single monitor pass, then exits.

To start over, stop both processes and delete `data/desk.db`.

## Tests

```bash
pytest
```

The tests cover the risk rules, RugCheck and DexScreener parsing, Grok output validation and
paper P&L. They also enforce the project's hard rules: no wallet or signing code, no signing
dependencies, no profit claims, empty `.env.example`, and the paper label on the dashboard.

## Notes

- Grok sees the creator's profile text as untrusted data, and its prompt says never to follow
  instructions inside it. The dashboard escapes all token and Grok text before rendering it.
- The httpx request logger is silenced so the Telegram bot token, which is part of the API URL,
  never appears in logs.
- Most new tokens are blocked. That is expected: the desk demonstrates the risk process, and
  open trades are rare.
