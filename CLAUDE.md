CLAUDE.md: Grok Multi-Agent Trading Desk (paper trading)
What this project is
A portfolio demo for Talha (@ai_talha_agents): a multi-agent trading desk for new Solana tokens.
Agents scan, analyze with Grok, apply risk rules, place PAPER trades on live prices, notify Telegram,
and show everything on a live dashboard. It will be screen-recorded for X and shown to clients.
Hard rules (never break)
PAPER TRADING ONLY. No wallet, no private keys, no seed phrases, no signing, no real orders.
Do not add any code path that can send a real transaction, even behind a flag.
Every number on the dashboard comes from real API data or real paper-trade records in the DB.
Never generate fake trades, fake prices, fake P&L or seeded "example" history.
The dashboard always shows a visible label: "Paper trading · live market data".
Secrets live only in .env. Commit .env.example with empty values. .env is in .gitignore
before the first commit. Never print keys in logs.
No profit claims anywhere in the UI, README or logs ("guaranteed", "100x", etc.).

