# PortfolioAgent

> A self-hosted, multi-agent AI system that watches my real investment portfolio, debates its own outlook, and briefs me over Telegram, with a live web dashboard on the side.

PortfolioAgent is a personal quantitative research analyst that never sleeps. Six specialist LLM agents run on a schedule (and on demand), pulling live market data, news, insider activity, and quant metrics, then argue a bull vs. bear case before synthesizing a plain-English briefing. I log trades by simply texting the bot, or by sending it a screenshot of a broker confirmation, which a vision model reads automatically.

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white">
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-1.2-1C3C3C">
  <img alt="Groq" src="https://img.shields.io/badge/LLM-Groq%20gpt--oss--120b-F55036">
  <img alt="FastAPI" src="https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/Dashboard-Next.js%2016-000000?logo=nextdotjs&logoColor=white">
  <img alt="Postgres" src="https://img.shields.io/badge/DB-PostgreSQL%2018%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
</p>

---

## Table of contents

- [Why I built it](#why-i-built-it)
- [Highlights](#highlights)
- [Architecture](#architecture)
- [The multi-agent pipeline](#the-multi-agent-pipeline)
- [Data sources](#data-sources)
- [Quant toolkit](#quant-toolkit)
- [The Telegram bot](#the-telegram-bot)
- [Scheduled intelligence](#scheduled-intelligence)
- [Web dashboard & live prices](#web-dashboard--live-prices)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Data model](#data-model)
- [Getting started](#getting-started)
- [Deployment](#deployment)
- [Design notes & engineering lessons](#design-notes--engineering-lessons)
- [Disclaimer](#disclaimer)

---

## Why I built it

I wanted to actually understand what my money was doing instead of glancing at a broker app once a day. Off-the-shelf tools either dumbed everything down or drowned me in numbers with no interpretation. So I built an analyst that:

- Speaks to me like a smart friend explaining finance, not a Bloomberg terminal.
- Forms a real opinion by making it argue *against itself* (bull vs. bear) before concluding.
- Combines **live data, news, and hard quant math**, not just one of them.
- Lives entirely on my own hardware, with secrets that never leave the box.

It's also my playground for production agentic-AI patterns: parallel graph execution, retry/backoff around flaky networks, rate-limit-aware prompt budgeting, and decision memory so the agents don't contradict themselves week to week.

---

## Highlights

- **6-agent LangGraph pipeline** with true parallel fan-out and a bull/bear debate stage.
- **Multimodal trade logging.** Log a trade by typing it, or by sending a broker screenshot parsed by a vision LLM.
- **Live streaming dashboard.** One Finnhub WebSocket is fanned out to browsers; the API key never touches the client.
- **Real quant, not vibes.** Beta, correlation matrix, Sharpe/Sortino, max drawdown, Monte Carlo, and a backtest vs. VTI.
- **Decision memory.** The agent remembers its recent calls and stays consistent.
- **Self-healing cron.** Detects a missed scheduled digest and re-runs it.
- **Hardened by default.** Rate limiting, locked CORS, GET-only API, IPv4 pinning around a flaky network, and retry/backoff everywhere.

---

## Architecture

```mermaid
flowchart TB
    subgraph Sources["External Data"]
        FH["Finnhub<br/>news, insiders, earnings<br/>recommendations, social"]
        YF["yfinance<br/>price history"]
        FG["CNN Fear & Greed"]
        TG_IN["Telegram<br/>(me: trades & questions)"]
    end

    subgraph Core["PortfolioAgent Core (Python)"]
        direction TB
        CRON["cron scheduler"] --> AGENT["agent.py<br/>run modes"]
        AGENT --> ORCH["orchestrator.py<br/>LangGraph pipeline"]
        BOT["bot.py<br/>Telegram bot"] --> ORCH
        BOT --> PARSER["trade_parser.py<br/>text + vision LLM"]
        ALERTS["alerts.py<br/>LLM-free move alerts"]
        HEAL["self_heal.py<br/>missed-run recovery"]
        ORCH <--> GROQ["Groq LLMs<br/>gpt-oss-120b, qwen3-vl"]
    end

    subgraph Store["State"]
        PG[("PostgreSQL 18<br/>+ pgvector")]
    end

    subgraph Serve["Serving Layer"]
        API["FastAPI<br/>REST + /ws"]
        WS["Finnhub WebSocket<br/>to browser fan-out"]
        DASH["Next.js Dashboard<br/>React 19, recharts"]
    end

    Sources --> Core
    Core <--> PG
    API <--> PG
    API --> WS
    DASH <--> API
    ORCH --> TG_OUT["Telegram briefings"]
    ALERTS --> TG_OUT
    PARSER --> PG

    classDef ext fill:#1e293b,stroke:#475569,color:#e2e8f0
    classDef core fill:#312e81,stroke:#6366f1,color:#e0e7ff
    classDef serve fill:#134e4a,stroke:#14b8a6,color:#ccfbf1
    class FH,YF,FG,TG_IN ext
    class CRON,AGENT,ORCH,BOT,PARSER,ALERTS,HEAL,GROQ core
    class API,WS,DASH serve
```

Everything runs on a single self-hosted Ubuntu mini PC as three `systemd` services (API, bot, dashboard), exposed to the internet over Tailscale Funnel with automatic HTTPS.

---

## The multi-agent pipeline

The heart of the system is a [LangGraph](https://langchain-ai.github.io/langgraph/) state graph. Three research agents run **in parallel**, feed a **bull/bear debate**, and a synthesis agent writes the final briefing.

```mermaid
flowchart LR
    START((START)) --> DATA[data_agent]
    START --> NEWS[news_agent]
    START --> QUANT[quant_agent]

    DATA --> BULL[bull_agent]
    NEWS --> BULL
    QUANT --> BULL
    DATA --> BEAR[bear_agent]
    NEWS --> BEAR
    QUANT --> BEAR

    BULL --> SYN[synthesis_agent]
    BEAR --> SYN
    SYN --> END((END))

    classDef research fill:#1e3a8a,stroke:#3b82f6,color:#dbeafe
    classDef debate fill:#7c2d12,stroke:#f97316,color:#ffedd5
    classDef synth fill:#14532d,stroke:#22c55e,color:#dcfce7
    class DATA,NEWS,QUANT research
    class BULL,BEAR debate
    class SYN synth
```

| Agent | Role |
|-------|------|
| **data_agent** | Portfolio snapshot: live prices, P&L, win/loss streaks, allocation, performance attribution, threshold alerts, and drift-from-target detection. |
| **news_agent** | Pulls full market intelligence (news, insider activity, earnings, analyst actions, social sentiment) and has the LLM synthesize what actually matters. |
| **quant_agent** | Runs the quant engine (beta, correlations, drawdown, Sharpe/Sortino, Monte Carlo) and translates the numbers into intuition. |
| **bull_agent** | Builds the strongest *data-cited* optimistic case over the next one to three months. |
| **bear_agent** | Builds the strongest *data-cited* pessimistic case: concentration risk, downgrades, macro headwinds. |
| **synthesis_agent** | Weighs both sides against recent decision memory and writes the final, mode-specific briefing. |

The graph adapts its output to the current **mode** (morning / intraday / daily / friday / weekly / interactive), from a terse intraday nudge to a full weekend report with charts. Intraday runs can even choose to stay `SILENT` when nothing is worth pinging me about.

---

## Data sources

| Source | What it provides |
|--------|------------------|
| **Finnhub** | Company news, insider sentiment & transactions, analyst recommendations, upcoming earnings & surprises, upgrades/downgrades, price targets, congressional trading, Reddit/social sentiment, ETF holdings & sector exposure, economic calendar. |
| **Finnhub WebSocket** | Real-time trade ticks for live prices. |
| **yfinance** | Historical daily closes for the quant engine and dividend history. |
| **CNN Fear & Greed Index** | Market sentiment, with sustained-fear detection. |

---

## Quant toolkit

`quant.py` computes real portfolio math over aligned return series:

- **Beta** of each holding vs. the S&P 500.
- **Correlation matrix** across holdings.
- **Max drawdown** with trough and recovery dates.
- **Sharpe & Sortino** ratios (configurable risk-free rate).
- **Monte Carlo simulation** of forward portfolio value (default 1,000 runs over 252 trading days).
- **Backtest vs. VTI** as a total-market benchmark.

The REST API also exposes a richer `/portfolio/quant-metrics` endpoint that honestly flags partial data (e.g. closed positions missing a recorded sale price) rather than silently reporting a wrong number.

---

## The Telegram bot

The bot is my entire interface to the system:

- **Ask anything.** Free-text questions kick off the full agent pipeline in interactive mode and stream back a chunked answer.
- **Log a trade by typing it.** "bought 2 NVDA at 178" is parsed by an LLM into a structured trade and shown for confirmation.
- **Log a trade from a screenshot.** Send a broker confirmation image and a **vision model (`qwen3-vl`)** extracts the trade. (The Telegram file URL embeds the bot token, so the image is downloaded to bytes first and never handed to a third party.)
- **Inline confirmation buttons.** Every trade is confirmed before it hits the database.
- **`/menu`** for quick actions, and **`/target`** to set target allocations that power drift alerts.

---

## Scheduled intelligence

Cron drives `agent.py` in different modes (ET):

| When | Mode | Output |
|------|------|--------|
| 8:55 AM (weekdays) | `--morning` | Pre-market briefing (with disclaimer). |
| Every 30 min, market hours | *(default)* intraday | Notable-move check; stays silent if nothing matters. |
| 4:05 PM (weekdays) | `--summary` | End-of-day summary. |
| 4:35 PM (Friday) | `--friday` | Weekly P&L digest. |
| 9:00 AM (Saturday) | `--weekly` | Full weekend report with charts. |
| Every 5 min, market hours | `alerts.py` | LLM-free big-move alerts (per-ticker bands, deduped). |
| After each digest | `self_heal.py` | Re-runs any scheduled digest that failed or hung. |

Every run is recorded in `agent_runs` so `self_heal.py` can detect stuck/failed jobs, and any top-level failure sends a plain fallback Telegram alert.

---

## Web dashboard & live prices

A **Next.js 16 / React 19** dashboard (Tailwind 4, Recharts, Framer Motion) visualizes holdings, history, quant metrics, sparklines, fear & greed, and news.

Live prices use a clean fan-out pattern: **one** asyncio task holds the single allowed Finnhub WebSocket connection, subscribes to all active holdings plus SPY, and broadcasts every tick to browsers connected to the FastAPI `/ws` endpoint. The Finnhub key stays server-side; the browser never sees it. The subscription list refreshes every 5 minutes so newly bought tickers stream automatically.

**Key API endpoints:** `/portfolio`, `/portfolio/history`, `/portfolio/analysis`, `/portfolio/quant`, `/portfolio/quant-metrics`, `/portfolio/sparklines`, `/fear-greed`, `/news`, `/ws`, `/health`.

---

## Tech stack

| Layer | Tech |
|-------|------|
| **Agents / LLM** | LangGraph, LangChain, Groq (`openai/gpt-oss-120b` for reasoning, `qwen3-vl` for vision) |
| **Backend** | Python 3.14, FastAPI, Uvicorn, websockets |
| **Bot** | python-telegram-bot |
| **Quant** | NumPy, pandas, matplotlib |
| **Data** | Finnhub, yfinance, CNN Fear & Greed |
| **Database** | PostgreSQL 18 + pgvector, psycopg2 |
| **Dashboard** | Next.js 16, React 19, Tailwind CSS 4, Recharts, Framer Motion |
| **Ops** | systemd, Tailscale Funnel, cron, slowapi (rate limiting) |

---

## Project structure

```
portfolioagent/
├── agent.py            # Cron entry point: run modes (morning/intraday/daily/friday/weekly)
├── orchestrator.py     # LangGraph 6-agent pipeline
├── bot.py              # Telegram bot (Q&A + trade logging)
├── trade_parser.py     # Text + vision LLM trade parsing
├── portfolio.py        # Shared DB utils, holdings, quotes, prompts
├── quant.py            # Beta, correlations, drawdown, Sharpe/Sortino, Monte Carlo
├── news.py             # Finnhub market intelligence
├── sentiment.py        # Fear & Greed index + sustained-fear detection
├── alerts.py           # LLM-free big-move alerts
├── self_heal.py        # Missed/hung run recovery
├── retry_utils.py      # Retry/backoff around rate limits & network gaps
├── tg_helpers.py       # Telegram send helpers
├── api/
│   ├── main.py         # FastAPI app + REST routes
│   ├── stream.py       # Finnhub WS to browser fan-out (/ws)
│   ├── quotes.py       # 30s TTL shared quote cache
│   └── db.py           # Connection pool
├── dashboard/          # Next.js frontend
├── db/                 # schema.sql + migrations
└── scripts/systemd/    # Service unit files
```

---

## Data model

PostgreSQL 18 (with pgvector). Core tables:

| Table | Purpose |
|-------|---------|
| `holdings` | Positions (ticker, shares, cost basis, buy/sell dates & prices). Active = `sold_at IS NULL`; a partial unique index enforces one open position per ticker. |
| `daily_closes` | One OHLCV row per ticker per day for the quant engine. |
| `daily_snapshots` | Portfolio value snapshots for history/charts. |
| `agent_logs` | Every reasoning run: prompt, response, whether it was sent, and why. |
| `agent_runs` | Run status (running/success/silent/skipped/failed) for self-healing. |
| `alert_state` | Dedup state for big-move alerts. |
| `fear_greed_history` | Daily Fear & Greed readings. |
| `decision_memory` | The agent's recent decisions, for cross-run consistency. |
| `target_allocation` | User targets that drive drift alerts. |
| `contributions` | Buy-transaction log. |
| `dividends` | Per-share dividend events from yfinance. |

---

## Getting started

> This is a personal, single-user project (my Telegram chat ID is the only authorized user). It's shared as a reference and portfolio piece rather than a turnkey product, but here's the shape of a local setup.

**Prerequisites:** Python 3.14, PostgreSQL 18 (+ pgvector), Node.js 20+, and a Telegram bot token.

```bash
# 1. Clone and enter
git clone https://github.com/aarush6848ddh/PortfolioAgent.git
cd PortfolioAgent

# 2. Python environment
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Database
createdb portfolioagent
psql portfolioagent -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql portfolioagent -f db/schema.sql
psql portfolioagent -f db/migrations_v2.sql
psql portfolioagent -f db/migrations_v3.sql

# 4. Configure secrets (see below)
cp .env.example .env   # then fill it in

# 5. Run the pieces
python bot.py                                   # Telegram bot
uvicorn api.main:app --host 127.0.0.1 --port 8000   # REST + /ws
python agent.py --morning                       # one-off briefing
cd dashboard && npm install && npm run dev      # dashboard
```

### Environment variables

**Required**

| Var | Purpose |
|-----|---------|
| `GROQ_API_KEY` | Groq LLM access. |
| `FINNHUB_API_KEY` | Market data + WebSocket. |
| `DATABASE_URL` | PostgreSQL connection string. |
| `TELEGRAM_BOT_TOKEN` | Telegram bot. |
| `TELEGRAM_CHAT_ID` | The one authorized chat. |

**Optional tuning** (defaults shown)

| Var | Default | Meaning |
|-----|---------|---------|
| `BIG_MOVE_PCT` | `3.0` | Alert band per ticker. |
| `DRAWDOWN_ALERT_PCT` | `5.0` | Drawdown alert threshold. |
| `DRIFT_ALERT_PCT` | `10.0` | Allocation drift threshold. |
| `CONCENTRATION_BASE_PCT` / `CONCENTRATION_STEP_PCT` | `50` / `5` | Concentration alerting. |
| `FEAR_THRESHOLD` / `FEAR_SUSTAINED_DAYS` | `30` / `5` | Sustained-fear alert. |
| `MONTE_CARLO_SIMULATIONS` / `MONTE_CARLO_DAYS` | `1000` / `252` | Monte Carlo config. |
| `RISK_FREE_RATE` | `0.05` | For Sharpe/Sortino. |
| `MORNING_WORD_LIMIT` / `INTRADAY_WORD_LIMIT` | `150` / `80` | Briefing length caps. |
| `HEALTH_CHECK_PORT` | `8111` | Bot health check port. |

Secrets always live in `.env` and are never hardcoded.

---

## Deployment

Running as three `systemd` services on a self-hosted Ubuntu box:

```bash
sudo systemctl {status,restart} portfolio-api portfolio-bot portfolio-dashboard
journalctl -u portfolio-api -f
```

- **Networking:** uvicorn on `127.0.0.1:8000`, Next.js on `127.0.0.1:3000`, exposed via **Tailscale Funnel** (443 for dashboard, 8443 for API) with automatic HTTPS certs.
- **Scheduling:** cron drives `agent.py`, `alerts.py`, and `self_heal.py`.
- **Deploy flow:** edit local mirror, rsync to server (excluding `venv`, `node_modules`, `.next`, `__pycache__`, logs), run `npm run build` for the dashboard, then restart services.

---

## Design notes & engineering lessons

A few things I'm proud of, and problems I solved building it:

- **Rate-limit-aware prompt budgeting.** Groq enforces a per-minute token cap. The synthesis agent is the only one combining all five reports, so it truncates its inputs to stay under the limit, while carefully preserving the appended *decision memory* that a naive head-slice would drop.
- **Retry/backoff for a flaky network.** The box's WiFi has a periodic roam gap, so LLM and data calls retry with `2/8/30s` backoff on both rate-limit *and* connection errors, but fail fast on a non-retryable "prompt too large" 413 instead of pointlessly retrying.
- **IPv4 pinning.** yfinance (and GitHub) would silently return empty results because the box's IPv6 route is blackholed; the fix forces IPv4 for those hosts.
- **Honest quant.** Metrics explicitly flag partial data (e.g. `total_return_partial`) rather than confidently reporting a number computed from missing sale prices.
- **Self-healing.** `agent_runs` records every run's lifecycle so a hung "running" row (no `finished_at`) can be detected and the digest re-triggered.
- **Security boundaries.** The Finnhub key never reaches the browser; the Telegram file URL (which embeds the bot token) is never sent to any third-party API; the API is GET-only, CORS-locked to the dashboard origin, and rate-limited per IP.

---

## Disclaimer

PortfolioAgent is a personal educational project. Nothing it produces is financial advice; it's an experiment in agentic AI applied to my own money. Do your own research.
