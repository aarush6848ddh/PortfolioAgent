from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from api.db import get_db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/portfolio")
def get_portfolio():
    import os
    import requests

    conn = get_db()
    cur = conn.cursor()

    # Active holdings
    cur.execute("SELECT ticker, shares, cost_basis FROM holdings WHERE sold_at IS NULL")
    holdings_raw = cur.fetchall()

    cur.close()
    conn.close()

    # Fetch live quotes from Finnhub REST API
    finnhub_key = os.environ.get("FINNHUB_API_KEY", "")
    quotes = {}
    for ticker, _, _ in holdings_raw:
        if ticker not in quotes:
            try:
                r = requests.get(
                    f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={finnhub_key}",
                    timeout=5,
                )
                data = r.json()
                if data.get("c"):
                    quotes[ticker] = {
                        "current": float(data["c"]),
                        "prev_close": float(data["pc"]),
                        "day_change": float(data["d"]) if data.get("d") else 0,
                        "day_change_pct": float(data["dp"]) if data.get("dp") else 0,
                    }
            except Exception:
                pass

    holdings = []
    total_value = 0
    total_cost = 0

    for ticker, shares, cost_basis in holdings_raw:
        shares = float(shares)
        cost_basis = float(cost_basis)
        quote = quotes.get(ticker, {})
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

    # Compute weights
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
    conn = get_db()
    cur = conn.cursor()

    # Daily snapshots
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

    # Get active holdings for historical calc
    cur.execute("SELECT ticker, shares, cost_basis FROM holdings WHERE sold_at IS NULL")
    active = [(r[0], float(r[1]), float(r[2])) for r in cur.fetchall()]

    cur.close()
    conn.close()

    # Build history from daily_closes if snapshots are sparse
    if len(snapshot_rows) < 5 and close_rows:
        from collections import defaultdict
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
            total_cost = sum(shares * cb for _, shares, cb in active)
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

    # Use actual snapshots
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
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT date, score, rating FROM fear_greed_history ORDER BY date DESC LIMIT 30")
    rows = cur.fetchall()
    cur.close()
    conn.close()

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
    conn = get_db()
    cur = conn.cursor()

    # Latest reports by type
    cur.execute(
        "SELECT run_type, response, created_at FROM agent_logs "
        "WHERE run_type IN ('morning', 'daily', 'intraday', 'weekly') "
        "ORDER BY created_at DESC LIMIT 1"
    )
    latest = cur.fetchone()

    # Latest morning report (usually has bull/bear)
    cur.execute(
        "SELECT run_type, response, created_at FROM agent_logs "
        "WHERE run_type = 'morning' ORDER BY created_at DESC LIMIT 1"
    )
    morning = cur.fetchone()

    # Decision memory
    cur.execute(
        "SELECT date, run_type, takeaways, portfolio_value FROM decision_memory "
        "ORDER BY date DESC, created_at DESC LIMIT 5"
    )
    memories = cur.fetchall()

    cur.close()
    conn.close()

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
    conn = get_db()
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
    conn.close()

    def to_dict(row):
        if not row:
            return None
        return {"run_type": row[0], "response": row[1], "created_at": row[2].isoformat()}

    return {
        "weekly_report": to_dict(weekly),
        "morning_report": to_dict(morning),
    }


@app.get("/portfolio/quant-metrics")
def get_quant_metrics():
    import numpy as np
    from collections import defaultdict

    conn = get_db()
    cur = conn.cursor()

    # Get active tickers
    cur.execute("SELECT DISTINCT ticker FROM holdings WHERE sold_at IS NULL")
    portfolio_tickers = [r[0] for r in cur.fetchall()]

    if not portfolio_tickers:
        return {
            "sharpe_ratio": 0, "sortino_ratio": 0, "beta": 0,
            "max_drawdown": 0, "max_drawdown_date": None, "recovery_days": None,
            "annualized_return": 0, "annualized_volatility": 0,
            "correlation_matrix": {"tickers": [], "matrix": []},
        }

    # All tickers we need (portfolio + SPY benchmark)
    all_tickers = list(set(portfolio_tickers + ["SPY"]))

    # Get daily closes
    cur.execute(
        "SELECT ticker, date, close_price FROM daily_closes "
        "WHERE ticker = ANY(%s) ORDER BY date",
        (all_tickers,),
    )
    rows = cur.fetchall()

    # Get holdings for portfolio weighting
    cur.execute("SELECT ticker, shares, cost_basis FROM holdings WHERE sold_at IS NULL")
    holdings = [(r[0], float(r[1]), float(r[2])) for r in cur.fetchall()]

    cur.close()
    conn.close()

    # Organize prices by ticker
    prices_by_ticker = defaultdict(list)
    for ticker, date, close in rows:
        prices_by_ticker[ticker].append((date, float(close)))

    # Sort by date
    for t in prices_by_ticker:
        prices_by_ticker[t].sort(key=lambda x: x[0])

    # Compute daily returns per ticker
    returns_by_ticker = {}
    for t, price_series in prices_by_ticker.items():
        prices = np.array([p[1] for p in price_series])
        if len(prices) < 2:
            continue
        returns_by_ticker[t] = np.diff(prices) / prices[:-1]

    if not returns_by_ticker or "SPY" not in returns_by_ticker:
        return {
            "sharpe_ratio": 0, "sortino_ratio": 0, "beta": 0,
            "max_drawdown": 0, "max_drawdown_date": None, "recovery_days": None,
            "annualized_return": 0, "annualized_volatility": 0,
            "correlation_matrix": {"tickers": [], "matrix": []},
        }

    spy_returns = returns_by_ticker["SPY"]

    # Compute portfolio-weighted daily returns
    # Use latest prices for weights
    total_value = 0
    ticker_weights = {}
    for t, shares, _ in holdings:
        if t in prices_by_ticker:
            latest_price = prices_by_ticker[t][-1][1]
            val = shares * latest_price
            ticker_weights[t] = val
            total_value += val

    if total_value == 0:
        return {
            "sharpe_ratio": 0, "sortino_ratio": 0, "beta": 0,
            "max_drawdown": 0, "max_drawdown_date": None, "recovery_days": None,
            "annualized_return": 0, "annualized_volatility": 0,
            "correlation_matrix": {"tickers": [], "matrix": []},
        }

    for t in ticker_weights:
        ticker_weights[t] /= total_value

    # Check if any portfolio tickers have return data
    port_tickers_with_data = [t for t in portfolio_tickers if t in returns_by_ticker]
    if not port_tickers_with_data:
        return {
            "sharpe_ratio": 0, "sortino_ratio": 0, "beta": 0,
            "max_drawdown": 0, "max_drawdown_date": None, "recovery_days": None,
            "annualized_return": 0, "annualized_volatility": 0,
            "correlation_matrix": {"tickers": [], "matrix": []},
        }

    # Align returns length (use shortest)
    min_len = min(
        len(spy_returns),
        *(len(returns_by_ticker[t]) for t in port_tickers_with_data)
    )
    spy_ret = spy_returns[-min_len:]

    port_returns = np.zeros(min_len)
    for t in portfolio_tickers:
        if t in returns_by_ticker and t in ticker_weights:
            port_returns += ticker_weights[t] * returns_by_ticker[t][-min_len:]

    # --- Metrics ---
    rf_daily = 0.05 / 252  # 5% risk-free rate

    # Sharpe ratio (annualized)
    excess = port_returns - rf_daily
    sharpe = float(np.mean(excess) / np.std(excess) * np.sqrt(252)) if np.std(excess) > 0 else 0

    # Sortino ratio (annualized)
    downside = excess[excess < 0]
    downside_std = np.std(downside) if len(downside) > 0 else 1e-10
    sortino = float(np.mean(excess) / downside_std * np.sqrt(252))

    # Beta vs SPY
    cov = np.cov(port_returns, spy_ret)
    beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else 1.0

    # Max drawdown
    cum_returns = np.cumprod(1 + port_returns)
    running_max = np.maximum.accumulate(cum_returns)
    drawdowns = (cum_returns - running_max) / running_max
    max_dd = float(np.min(drawdowns) * 100)

    # Find max drawdown date
    dd_idx = int(np.argmin(drawdowns))
    dates = [p[0] for p in prices_by_ticker[portfolio_tickers[0]]]
    max_dd_date = dates[min(dd_idx + 1, len(dates) - 1)].isoformat() if dates else None

    # Recovery: days from max DD to new high
    recovery_days = None
    if dd_idx < len(drawdowns) - 1:
        recovery = np.where(drawdowns[dd_idx:] >= 0)[0]
        if len(recovery) > 0:
            recovery_days = int(recovery[0])

    # Annualized return & volatility
    ann_return = float((cum_returns[-1] ** (252 / len(port_returns)) - 1) * 100)
    ann_vol = float(np.std(port_returns) * np.sqrt(252) * 100)

    # Correlation matrix (portfolio tickers + SPY)
    corr_tickers = [t for t in portfolio_tickers if t in returns_by_ticker] + ["SPY"]
    corr_returns = []
    for t in corr_tickers:
        corr_returns.append(returns_by_ticker[t][-min_len:])
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
