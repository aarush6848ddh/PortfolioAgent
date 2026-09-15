import asyncio
import time
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, timedelta

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
import metrics
from metrics import MIN_HISTORY_DAYS, LOOKBACK_DAYS

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


# Portfolio-level aggregates (return, vol, Sharpe, drawdown) are built from a
# single daily return series summed across holdings, which requires those
# holdings to share a common date window. A ticker with very little history
# (e.g. a recent buy) would collapse that window for the whole portfolio, so we
# exclude anything below this many trading days from portfolio-level math until
# it has enough data. Excluded tickers are surfaced in `insufficient_history`.
# MIN_HISTORY_DAYS is imported from metrics (single source of truth).

EMPTY_QUANT_METRICS = {
    "sharpe_ratio": 0, "sortino_ratio": 0, "beta": 0,
    "max_drawdown": 0, "max_drawdown_date": None, "recovery_days": None,
    "annualized": False,
    "annualized_return": None, "annualized_volatility": 0,
    "period_return": 0, "period_start": None, "period_end": None,
    "correlation_matrix": {"tickers": [], "matrix": []},
    "insufficient_history": [],
    "unrealized_pnl": None, "realized_pnl": None, "total_pnl": None,
    "total_return_pct": None, "total_return_partial": False,
    "priced_closed_positions": 0, "total_closed_positions": 0,
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

        # Trailing LOOKBACK_DAYS window (shared with quant.py) so the dashboard
        # and agent paths annualize over the same ~1-year sample.
        cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
        cur.execute(
            "SELECT ticker, date, close_price FROM daily_closes "
            "WHERE ticker = ANY(%s) AND date >= %s ORDER BY date",
            (all_tickers, cutoff),
        )
        rows = cur.fetchall()

        holdings = [(r[0], float(r[1]), float(r[2])) for r in get_active_holdings(cur)]

        # Realized/unrealized inputs for the partial total-return figure.
        cur.execute("SELECT total_value, total_cost FROM daily_snapshots ORDER BY date DESC LIMIT 1")
        snap = cur.fetchone()
        cur.execute(
            "SELECT COALESCE(SUM((sale_price - cost_basis) * shares), 0), "
            "COALESCE(SUM(cost_basis * shares), 0), COUNT(*) "
            "FROM holdings WHERE sold_at IS NOT NULL AND sale_price IS NOT NULL"
        )
        realized_pnl, priced_closed_cost, priced_closed_positions = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM holdings WHERE sold_at IS NOT NULL")
        total_closed_positions = cur.fetchone()[0]
        cur.close()

    # Partial total return = unrealized P&L on current holdings (from the latest
    # snapshot) + realized P&L from the closed positions that have a recorded
    # sale_price. 8 of 14 closed trades have NULL sale_price (missing trade
    # confirmations, see TODO.md), so this is explicitly partial. The % divides
    # dollar P&L by summed cost basis and does not net recycled capital (sells
    # that funded later buys), so it slightly understates the true return.
    if snap is not None:
        cur_value, cur_cost = float(snap[0]), float(snap[1])
        unrealized_pnl = cur_value - cur_cost
        total_pnl = unrealized_pnl + float(realized_pnl)
        denom = cur_cost + float(priced_closed_cost)
        realized_block = {
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(float(realized_pnl), 2),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(total_pnl / denom * 100, 2) if denom else None,
            "total_return_partial": total_closed_positions > priced_closed_positions,
            "priced_closed_positions": int(priced_closed_positions),
            "total_closed_positions": int(total_closed_positions),
        }
    else:
        realized_block = {
            "unrealized_pnl": None, "realized_pnl": None, "total_pnl": None,
            "total_return_pct": None, "total_return_partial": False,
            "priced_closed_positions": int(priced_closed_positions),
            "total_closed_positions": int(total_closed_positions),
        }

    closes = defaultdict(dict)
    for ticker, dt, close in rows:
        closes[ticker][dt] = float(close)

    port_tickers_with_data = [t for t in portfolio_tickers if len(closes.get(t, {})) >= MIN_HISTORY_DAYS]
    insufficient_history = sorted(
        t for t in portfolio_tickers if 2 <= len(closes.get(t, {})) < MIN_HISTORY_DAYS
    )
    if not port_tickers_with_data or len(closes.get("SPY", {})) < 2:
        return {**EMPTY_QUANT_METRICS, "insufficient_history": insufficient_history, **realized_block}

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

    # Dollar-weighted portfolio value series: actual shares held, valued at each
    # day's close. This is the single canonical construction — the agent path
    # (quant.py) computes Sharpe/Sortino/drawdown from the exact same series, so
    # the two paths can no longer disagree. (The old fixed-current-weight,
    # daily-rebalanced return series lived only here and had drifted from
    # quant.py and metrics.py.)
    shares_by_ticker = {t: shares for t, shares, _ in holdings if t in returns_by_ticker}
    port_values = np.array([
        sum(shares * closes[t][d] for t, shares in shares_by_ticker.items())
        for d in common_dates
    ])
    if port_values[0] == 0:
        return EMPTY_QUANT_METRICS

    port_returns = metrics.daily_returns(port_values)

    # --- Metrics (all from metrics.py, ddof=1 everywhere) ---
    sharpe = metrics.sharpe_ratio(port_returns)
    sortino = metrics.sortino_ratio(port_returns)
    beta = metrics.beta(port_returns, spy_ret)
    # Coalesce None -> frontend-safe defaults (no dispersion / no downside days).
    sharpe = 0.0 if sharpe is None else sharpe
    sortino = 0.0 if sortino is None else sortino
    beta = 1.0 if beta is None else beta

    dd = metrics.max_drawdown(port_values)
    max_dd = dd["max_drawdown_pct"]
    drawdowns = dd["drawdowns"]
    dd_idx = dd["trough_index"]
    # drawdowns is aligned to the value series, so trough_index maps straight to
    # common_dates (no +1 offset like the old returns-indexed array).
    max_dd_date = common_dates[dd_idx].isoformat()

    recovery_days = None
    if dd_idx < len(drawdowns) - 1:
        recovery = np.where(drawdowns[dd_idx:] >= 0)[0]
        if len(recovery) > 0:
            recovery_days = int(recovery[0])

    # Raw cumulative return over the actual window. Annualizing this with
    # ** (252 / N) is only meaningful with enough observations; on a short
    # window it extrapolates a few weeks into a fictional yearly rate (e.g. a
    # 5.18% / 25-day gain became 66%). Below MIN_HISTORY_DAYS we don't
    # annualize and let the caller show the raw period return instead.
    n_obs = len(port_returns)
    growth = port_values[-1] / port_values[0]
    period_return = float((growth - 1) * 100)
    period_start = common_dates[0].isoformat()
    period_end = common_dates[-1].isoformat()
    annualized = n_obs >= MIN_HISTORY_DAYS
    ann_return = float((growth ** (252 / n_obs) - 1) * 100) if annualized else None
    ann_vol = float(np.std(port_returns, ddof=metrics.DDOF) * np.sqrt(252) * 100)

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
        "annualized": annualized,
        "annualized_return": round(ann_return, 2) if ann_return is not None else None,
        "period_return": round(period_return, 2),
        "period_start": period_start,
        "period_end": period_end,
        "annualized_volatility": round(ann_vol, 2),
        "correlation_matrix": {
            "tickers": corr_tickers,
            "matrix": [[round(v, 3) for v in row] for row in corr_matrix],
        },
        "insufficient_history": insufficient_history,
        **realized_block,
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
