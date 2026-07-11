import asyncio
import time
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from api import quotes, stream
from api.db import get_db
from news import get_company_news

log = logging.getLogger("api")

DASHBOARD_ORIGIN = "https://aarush-box.tail8c0a93.ts.net"


# --- Rate limiting (per real client IP — Funnel sets X-Forwarded-For) ---

def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip, default_limits=["30/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(stream.finnhub_stream())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[DASHBOARD_ORIGIN],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_active_holdings(cur):
    cur.execute("SELECT ticker, shares, cost_basis FROM holdings WHERE sold_at IS NULL")
    return cur.fetchall()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/portfolio")
def get_portfolio():
    with get_db() as conn:
        cur = conn.cursor()
        holdings_raw = get_active_holdings(cur)
        cur.close()

    holdings = []
    total_value = 0
    total_cost = 0

    for ticker, shares, cost_basis in holdings_raw:
        shares = float(shares)
        cost_basis = float(cost_basis)
        quote = quotes.get_quote(ticker) or {}
        current_price = quote.get("current", cost_basis)
        day_change = quote.get("day_change", 0)
        day_change_pct = quote.get("day_change_pct", 0)
        value = shares * current_price
        cost = shares * cost_basis
        pnl = value - cost

        total_value += value
        total_cost += cost

        holdings.append({
            "ticker": ticker,
            "shares": shares,
            "cost_basis": cost_basis,
            "current_price": current_price,
            "value": round(value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / cost) * 100, 2) if cost else 0,
            "day_change": round(day_change, 2),
            "day_change_pct": round(day_change_pct, 2),
        })

    for h in holdings:
        h["weight"] = round((h["value"] / total_value) * 100, 2) if total_value else 0

    total_pnl = total_value - total_cost
    total_day_change = sum(h["day_change"] * h["shares"] for h in holdings)

    return {
        "holdings": holdings,
        "summary": {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round((total_pnl / total_cost) * 100, 2) if total_cost else 0,
            "day_change": round(total_day_change, 2),
            "day_change_pct": round((total_day_change / total_value) * 100, 2) if total_value else 0,
        },
    }


@app.get("/portfolio/history")
def get_portfolio_history(limit: int = Query(default=90, le=365)):
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT date, total_value, total_cost, day_pl, fear_greed_score "
            "FROM daily_snapshots ORDER BY date DESC LIMIT %s",
            (limit,),
        )
        snapshot_rows = cur.fetchall()

        # Also get daily closes to compute historical value if snapshots are sparse
        cur.execute("""
            SELECT dc.date, dc.ticker, dc.close_price
            FROM daily_closes dc
            WHERE dc.ticker IN (SELECT DISTINCT ticker FROM holdings WHERE sold_at IS NULL)
            ORDER BY dc.date DESC
            LIMIT %s
        """, (limit * 10,))
        close_rows = cur.fetchall()

        active = [(r[0], float(r[1]), float(r[2])) for r in get_active_holdings(cur)]
        cur.close()

    # Build history from daily_closes if snapshots are sparse
    if len(snapshot_rows) < 5 and close_rows:
        by_date = defaultdict(dict)
        for date, ticker, close in close_rows:
            by_date[date.isoformat()][ticker] = float(close)

        snapshots = []
        sorted_dates = sorted(by_date.keys())
        cumulative_pnl = 0
        prev_value = None
        for date_str in sorted_dates:
            prices = by_date[date_str]
            total_val = sum(shares * prices.get(t, cb) for t, shares, cb in active)
            day_pnl = (total_val - prev_value) if prev_value else 0
            cumulative_pnl += day_pnl
            prev_value = total_val
            snapshots.append({
                "date": date_str,
                "total_value": round(total_val, 2),
                "daily_pnl": round(day_pnl, 2),
                "cumulative_pnl": round(cumulative_pnl, 2),
            })
        return {"snapshots": snapshots[-limit:]}

    snapshots = []
    cumulative = 0
    for r in reversed(snapshot_rows):
        day_pnl = float(r[3]) if r[3] else 0
        cumulative += day_pnl
        snapshots.append({
            "date": r[0].isoformat(),
            "total_value": float(r[1]),
            "daily_pnl": day_pnl,
            "cumulative_pnl": round(cumulative, 2),
        })
    return {"snapshots": snapshots}


@app.get("/fear-greed")
def get_fear_greed():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT date, score, rating FROM fear_greed_history ORDER BY date DESC LIMIT 30")
        rows = cur.fetchall()
        cur.close()

    if not rows:
        return {"value": 0, "label": "N/A", "history": []}

    latest = rows[0]
    return {
        "value": float(latest[1]),
        "label": latest[2].upper() if latest[2] else "N/A",
        "history": [
            {"date": r[0].isoformat(), "value": float(r[1])}
            for r in reversed(rows)
        ],
    }


@app.get("/portfolio/analysis")
def get_portfolio_analysis():
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT run_type, response, created_at FROM agent_logs "
            "WHERE run_type IN ('morning', 'daily', 'intraday', 'weekly') "
            "ORDER BY created_at DESC LIMIT 1"
        )
        latest = cur.fetchone()

        cur.execute(
            "SELECT run_type, response, created_at FROM agent_logs "
            "WHERE run_type = 'morning' ORDER BY created_at DESC LIMIT 1"
        )
        morning = cur.fetchone()

        cur.execute(
            "SELECT date, run_type, takeaways, portfolio_value FROM decision_memory "
            "ORDER BY date DESC, created_at DESC LIMIT 5"
        )
        memories = cur.fetchall()
        cur.close()

    def to_report(row):
        if not row:
            return None
        return {
            "run_type": row[0],
            "response": row[1],
            "created_at": row[2].isoformat(),
        }

    return {
        "latest_report": to_report(latest),
        "morning_report": to_report(morning),
        "decision_memory": [
            {
                "date": m[0].isoformat(),
                "run_type": m[1],
                "takeaway": m[2],
                "portfolio_value": float(m[3]) if m[3] is not None else None,
            }
            for m in memories
        ],
    }


@app.get("/portfolio/quant")
def get_portfolio_quant():
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT run_type, response, created_at FROM agent_logs "
            "WHERE run_type = 'weekly' ORDER BY created_at DESC LIMIT 1"
        )
        weekly = cur.fetchone()

        cur.execute(
            "SELECT run_type, response, created_at FROM agent_logs "
            "WHERE run_type = 'morning' ORDER BY created_at DESC LIMIT 1"
        )
        morning = cur.fetchone()
        cur.close()

    def to_dict(row):
        if not row:
            return None
        return {"run_type": row[0], "response": row[1], "created_at": row[2].isoformat()}

    return {
        "weekly_report": to_dict(weekly),
        "morning_report": to_dict(morning),
    }


EMPTY_QUANT_METRICS = {
    "sharpe_ratio": 0, "sortino_ratio": 0, "beta": 0,
    "max_drawdown": 0, "max_drawdown_date": None, "recovery_days": None,
    "annualized_return": 0, "annualized_volatility": 0,
    "correlation_matrix": {"tickers": [], "matrix": []},
}


@app.get("/portfolio/quant-metrics")
def get_quant_metrics():
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT DISTINCT ticker FROM holdings WHERE sold_at IS NULL")
        portfolio_tickers = [r[0] for r in cur.fetchall()]

        if not portfolio_tickers:
            cur.close()
            return EMPTY_QUANT_METRICS

        all_tickers = list(set(portfolio_tickers + ["SPY"]))

        cur.execute(
            "SELECT ticker, date, close_price FROM daily_closes "
            "WHERE ticker = ANY(%s) ORDER BY date",
            (all_tickers,),
        )
        rows = cur.fetchall()

        holdings = [(r[0], float(r[1]), float(r[2])) for r in get_active_holdings(cur)]
        cur.close()

    closes = defaultdict(dict)
    for ticker, date, close in rows:
        closes[ticker][date] = float(close)

    port_tickers_with_data = [t for t in portfolio_tickers if len(closes.get(t, {})) >= 2]
    if not port_tickers_with_data or len(closes.get("SPY", {})) < 2:
        return EMPTY_QUANT_METRICS

    # Align all series on dates where every ticker traded, so returns
    # are computed for the same day across tickers (mixed history lengths
    # or holiday gaps would otherwise skew beta/correlations).
    common_dates = sorted(
        set.intersection(*(set(closes[t]) for t in port_tickers_with_data + ["SPY"]))
    )
    if len(common_dates) < 2:
        return EMPTY_QUANT_METRICS

    returns_by_ticker = {}
    for t in port_tickers_with_data + ["SPY"]:
        prices = np.array([closes[t][d] for d in common_dates])
        returns_by_ticker[t] = np.diff(prices) / prices[:-1]

    spy_ret = returns_by_ticker["SPY"]

    # Portfolio-weighted daily returns (latest prices for weights)
    total_value = 0
    ticker_weights = {}
    for t, shares, _ in holdings:
        if t in returns_by_ticker:
            val = shares * closes[t][common_dates[-1]]
            ticker_weights[t] = val
            total_value += val

    if total_value == 0:
        return EMPTY_QUANT_METRICS

    for t in ticker_weights:
        ticker_weights[t] /= total_value

    port_returns = np.zeros(len(spy_ret))
    for t, weight in ticker_weights.items():
        port_returns += weight * returns_by_ticker[t]

    # --- Metrics ---
    rf_daily = 0.05 / 252  # 5% risk-free rate

    excess = port_returns - rf_daily
    sharpe = float(np.mean(excess) / np.std(excess) * np.sqrt(252)) if np.std(excess) > 0 else 0

    downside = excess[excess < 0]
    downside_std = np.std(downside) if len(downside) > 0 else 1e-10
    sortino = float(np.mean(excess) / downside_std * np.sqrt(252))

    cov = np.cov(port_returns, spy_ret)
    beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else 1.0

    cum_returns = np.cumprod(1 + port_returns)
    running_max = np.maximum.accumulate(cum_returns)
    drawdowns = (cum_returns - running_max) / running_max
    max_dd = float(np.min(drawdowns) * 100)

    dd_idx = int(np.argmin(drawdowns))
    # returns[i] corresponds to common_dates[i + 1]
    max_dd_date = common_dates[min(dd_idx + 1, len(common_dates) - 1)].isoformat()

    recovery_days = None
    if dd_idx < len(drawdowns) - 1:
        recovery = np.where(drawdowns[dd_idx:] >= 0)[0]
        if len(recovery) > 0:
            recovery_days = int(recovery[0])

    ann_return = float((cum_returns[-1] ** (252 / len(port_returns)) - 1) * 100)
    ann_vol = float(np.std(port_returns) * np.sqrt(252) * 100)

    corr_tickers = port_tickers_with_data + ["SPY"]
    corr_returns = [returns_by_ticker[t] for t in corr_tickers]
    corr_matrix = np.corrcoef(corr_returns).tolist()

    return {
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "beta": round(beta, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_date": max_dd_date,
        "recovery_days": recovery_days,
        "annualized_return": round(ann_return, 2),
        "annualized_volatility": round(ann_vol, 2),
        "correlation_matrix": {
            "tickers": corr_tickers,
            "matrix": [[round(v, 3) for v in row] for row in corr_matrix],
        },
    }


# --- Sparklines (last 30 closes per ticker, cached 10 min) ---

_sparklines_cache = {"expires": 0.0, "data": None}


@app.get("/portfolio/sparklines")
def get_sparklines():
    if _sparklines_cache["data"] is not None and _sparklines_cache["expires"] > time.time():
        return _sparklines_cache["data"]

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, date, close_price FROM (
                SELECT ticker, date, close_price,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                FROM daily_closes
                WHERE ticker IN (SELECT DISTINCT ticker FROM holdings WHERE sold_at IS NULL)
                   OR ticker = 'SPY'
            ) t WHERE rn <= 30 ORDER BY ticker, date
        """)
        rows = cur.fetchall()
        cur.close()

    series = defaultdict(list)
    for ticker, date, close in rows:
        series[ticker].append({"date": date.isoformat(), "close": float(close)})

    data = {"sparklines": series}
    _sparklines_cache["data"] = data
    _sparklines_cache["expires"] = time.time() + 600
    return data


# --- News (cached 15 min server-side) ---

_news_cache = {"expires": 0.0, "data": None}


@app.get("/news")
def get_news():
    if _news_cache["data"] is not None and _news_cache["expires"] > time.time():
        return _news_cache["data"]

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT ticker FROM holdings WHERE sold_at IS NULL")
        tickers = [r[0] for r in cur.fetchall()]
        cur.close()

    articles = []
    for t in tickers:
        for a in get_company_news(t, days=3):
            articles.append({**a, "ticker": t})
    # datetime is "YYYY-MM-DD HH:MM" — lexicographic sort works
    articles.sort(key=lambda a: a["datetime"], reverse=True)

    data = {"articles": articles[:30]}
    _news_cache["data"] = data
    _news_cache["expires"] = time.time() + 900
    return data


# --- Live price WebSocket (browser fan-out) ---

@app.websocket("/ws")
async def ws_prices(websocket: WebSocket):
    if stream.client_count() >= stream.MAX_CLIENTS:
        await websocket.close(code=1013)  # try again later
        return
    await websocket.accept()
    stream.add_client(websocket)
    try:
        while True:
            # Clients don't send data; this just detects disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        stream.remove_client(websocket)
