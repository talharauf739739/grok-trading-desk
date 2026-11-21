SPEC.md: Grok Multi-Agent Trading Desk
Goal
A 40-second, honest demo: new Solana token appears → Grok explains it → risk agent blocks or
approves → paper trade opens → Telegram alert → dashboard updates.
Architecture
Scanner ──> Analyzer (Grok) ──> Risk agent ──> Paper executor ──> Notifier (Telegram)
 │ │ │ │
 └──────────────┴──── agent_log + trades (SQLite) ──┴──> Dashboard (Streamlit)
 Position monitor ──┘ (closes paper trades)
Data sources (verify current docs before coding)
DexScreener public API: latest token profiles / pairs and per-token pair data
(price, liquidity, volume, FDV, pair age).
RugCheck public API: token report summary (mint/freeze authority, top-holder share, LP status).
xAI Grok API: chat completions, JSON output.

