"""Quantitative analysis module. All metrics derived from real data in daily_closes."""
import os
import numpy as np
import psycopg2
from datetime import date, timedelta
from dotenv import load_dotenv
from config import MONTE_CARLO_SIMULATIONS, MONTE_CARLO_DAYS

load_dotenv()

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.053

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

# --- Data retrieval ---

def get_daily_closes(ticker, lookback_days=365):
    conn = get_conn()
    cur = conn.cursor()
    cutoff = date.today() - timedelta(days=lookback_days)
    cur.execute(
        "SELECT date, close_price FROM daily_closes WHERE ticker = %s AND date >= %s ORDER BY date",
        (ticker, cutoff)
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_aligned_returns(tickers, lookback_days=365):
    all_data = {}
    for t in tickers:
        rows = get_daily_closes(t, lookback_days)
        all_data[t] = {r[0]: float(r[1]) for r in rows}

    common_dates = sorted(set.intersection(*[set(d.keys()) for d in all_data.values()]))
    if len(common_dates) < 2:
        return None, None

    prices = np.array([[all_data[t][d] for t in tickers] for d in common_dates])
    returns = np.diff(np.log(prices), axis=0)
    return returns, common_dates[1:]

# --- Beta ---

def calc_beta(ticker, benchmark="SPY", lookback_days=365):
    returns, dates = get_aligned_returns([ticker, benchmark], lookback_days)
    if returns is None or len(returns) < 20:
        return None
    asset_ret = returns[:, 0]
    bench_ret = returns[:, 1]
    cov = np.cov(asset_ret, bench_ret)[0, 1]
    var = np.var(bench_ret, ddof=1)
    if var == 0:
        return None
    return round(float(cov / var), 3)

# --- Correlation ---

def calc_correlation_matrix(tickers, lookback_days=365):
    returns, dates = get_aligned_returns(tickers, lookback_days)
    if returns is None or len(returns) < 20:
        return None
    corr = np.corrcoef(returns.T)
    result = {}
    for i, t1 in enumerate(tickers):
        for j, t2 in enumerate(tickers):
            if i < j:
                result[f"{t1}/{t2}"] = round(float(corr[i, j]), 3)
    return result

def calc_rolling_correlation(ticker1, ticker2, window=30, lookback_days=365):
    returns, dates = get_aligned_returns([ticker1, ticker2], lookback_days)
    if returns is None or len(returns) < window:
        return None
    r1 = returns[-window:, 0]
    r2 = returns[-window:, 1]
    corr = np.corrcoef(r1, r2)[0, 1]
    return round(float(corr), 3)

# --- Drawdown ---

def calc_portfolio_drawdown(holdings, lookback_days=365):
    tickers = [h["ticker"] for h in holdings]
    shares = {h["ticker"]: h["shares"] for h in holdings}

    all_data = {}
    for t in tickers:
        rows = get_daily_closes(t, lookback_days)
        all_data[t] = {r[0]: float(r[1]) for r in rows}

    common_dates = sorted(set.intersection(*[set(d.keys()) for d in all_data.values()]))
    if len(common_dates) < 2:
        return None

    port_values = []
    for d in common_dates:
        val = sum(all_data[t][d] * shares[t] for t in tickers)
        port_values.append(val)

    port_values = np.array(port_values)
    cummax = np.maximum.accumulate(port_values)
    drawdowns = (port_values - cummax) / cummax

    max_dd = float(np.min(drawdowns))
    max_dd_idx = int(np.argmin(drawdowns))
    max_dd_date = common_dates[max_dd_idx]

    peak_before = cummax[max_dd_idx]
    recovery_days = None
    for i in range(max_dd_idx + 1, len(port_values)):
        if port_values[i] >= peak_before:
            recovery_days = (common_dates[i] - max_dd_date).days
            break

    return {
        "max_drawdown_pct": round(max_dd * 100, 2),
        "trough_date": str(max_dd_date),
        "recovery_days": recovery_days,
    }

# --- Risk-adjusted returns ---

def calc_sharpe_sortino(holdings, lookback_days=365):
    tickers = [h["ticker"] for h in holdings]
    shares = {h["ticker"]: h["shares"] for h in holdings}

    all_data = {}
    for t in tickers:
        rows = get_daily_closes(t, lookback_days)
        all_data[t] = {r[0]: float(r[1]) for r in rows}

    common_dates = sorted(set.intersection(*[set(d.keys()) for d in all_data.values()]))
    if len(common_dates) < 20:
        return None

    port_values = np.array([
        sum(all_data[t][d] * shares[t] for t in tickers) for d in common_dates
    ])
    daily_returns = np.diff(port_values) / port_values[:-1]

    daily_rf = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
    excess = daily_returns - daily_rf

    sharpe = None
    if np.std(excess, ddof=1) > 0:
        sharpe = round(float(np.mean(excess) / np.std(excess, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)), 3)

    downside = excess[excess < 0]
    sortino = None
    if len(downside) > 0 and np.std(downside, ddof=1) > 0:
        sortino = round(float(np.mean(excess) / np.std(downside, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)), 3)

    return {"sharpe": sharpe, "sortino": sortino}

# --- Backtest vs VTI baseline ---

def backtest_vs_vti(holdings, lookback_days=365):
    tickers = [h["ticker"] for h in holdings]
    shares = {h["ticker"]: h["shares"] for h in holdings}

    all_data = {}
    for t in tickers + ["VTI"]:
        rows = get_daily_closes(t, lookback_days)
        all_data[t] = {r[0]: float(r[1]) for r in rows}

    all_tickers_for_dates = tickers + (["VTI"] if "VTI" not in tickers else [])
    common_dates = sorted(set.intersection(*[set(all_data[t].keys()) for t in all_tickers_for_dates]))
    if len(common_dates) < 2:
        return None

    first_date = common_dates[0]
    last_date = common_dates[-1]

    port_start = sum(all_data[t][first_date] * shares[t] for t in tickers)
    port_end = sum(all_data[t][last_date] * shares[t] for t in tickers)
    port_return = (port_end - port_start) / port_start * 100

    vti_start_price = all_data["VTI"][first_date]
    vti_shares = port_start / vti_start_price
    vti_end = vti_shares * all_data["VTI"][last_date]
    vti_return = (vti_end - port_start) / port_start * 100

    return {
        "period": f"{first_date} to {last_date}",
        "portfolio_return_pct": round(port_return, 2),
        "vti_baseline_return_pct": round(vti_return, 2),
        "alpha_pct": round(port_return - vti_return, 2),
    }

# --- Monte Carlo Simulation ---

def monte_carlo_simulation(holdings):
    """Monte Carlo simulation of future portfolio values.
    Returns percentile outcomes and probability of loss."""
    tickers = [h["ticker"] for h in holdings]
    shares = {h["ticker"]: h["shares"] for h in holdings}

    all_data = {}
    for t in tickers:
        rows = get_daily_closes(t)
        all_data[t] = {r[0]: float(r[1]) for r in rows}

    common_dates = sorted(set.intersection(*[set(d.keys()) for d in all_data.values()]))
    if len(common_dates) < 60:
        return None

    port_values = np.array([
        sum(all_data[t][d] * shares[t] for t in tickers) for d in common_dates
    ])
    daily_returns = np.diff(port_values) / port_values[:-1]

    current_value = port_values[-1]
    mu = np.mean(daily_returns)
    sigma = np.std(daily_returns)

    np.random.seed(42)
    simulations = np.zeros((MONTE_CARLO_SIMULATIONS, MONTE_CARLO_DAYS))
    for i in range(MONTE_CARLO_SIMULATIONS):
        daily_r = np.random.normal(mu, sigma, MONTE_CARLO_DAYS)
        price_path = current_value * np.cumprod(1 + daily_r)
        simulations[i] = price_path

    final_values = simulations[:, -1]

    return {
        "current_value": round(float(current_value), 2),
        "days_ahead": MONTE_CARLO_DAYS,
        "simulations": MONTE_CARLO_SIMULATIONS,
        "percentiles": {
            "5th": round(float(np.percentile(final_values, 5)), 2),
            "25th": round(float(np.percentile(final_values, 25)), 2),
            "50th": round(float(np.percentile(final_values, 50)), 2),
            "75th": round(float(np.percentile(final_values, 75)), 2),
            "95th": round(float(np.percentile(final_values, 95)), 2),
        },
        "prob_loss": round(float(np.mean(final_values < current_value) * 100), 1),
        "expected_return_pct": round(float((np.mean(final_values) - current_value) / current_value * 100), 1),
    }

# --- Full quant summary ---

def get_quant_summary(holdings):
    tickers = [h["ticker"] for h in holdings]

    summary = {
        "betas": {},
        "correlations": None,
        "rolling_corr_soxx_schg": None,
        "rolling_corr_soxx_vti": None,
        "drawdown": None,
        "risk_adjusted": None,
        "backtest": None,
        "monte_carlo": None,
    }

    for t in tickers:
        summary["betas"][t] = calc_beta(t)

    summary["correlations"] = calc_correlation_matrix(tickers)
    summary["rolling_corr_soxx_schg"] = calc_rolling_correlation("SOXX", "SCHG")
    summary["rolling_corr_soxx_vti"] = calc_rolling_correlation("SOXX", "VTI")
    summary["drawdown"] = calc_portfolio_drawdown(holdings)
    summary["risk_adjusted"] = calc_sharpe_sortino(holdings)
    summary["backtest"] = backtest_vs_vti(holdings)
    summary["monte_carlo"] = monte_carlo_simulation(holdings)

    return summary

def format_quant_for_prompt(summary):
    lines = []
    lines.append("=== QUANTITATIVE ANALYSIS (from real historical data) ===")

    if summary["betas"]:
        beta_parts = [f"{t}: {b}" for t, b in summary["betas"].items() if b is not None]
        if beta_parts:
            lines.append(f"Beta vs S&P 500: {', '.join(beta_parts)}")

    if summary["correlations"]:
        corr_parts = [f"{pair}: {val}" for pair, val in summary["correlations"].items()]
        lines.append(f"Correlation matrix: {', '.join(corr_parts)}")

    if summary["rolling_corr_soxx_schg"] is not None:
        lines.append(f"SOXX/SCHG 30-day rolling correlation: {summary['rolling_corr_soxx_schg']}")
    if summary["rolling_corr_soxx_vti"] is not None:
        lines.append(f"SOXX/VTI 30-day rolling correlation: {summary['rolling_corr_soxx_vti']}")

    dd = summary["drawdown"]
    if dd:
        recovery = f"{dd['recovery_days']} days" if dd["recovery_days"] else "not yet recovered"
        lines.append(f"Max drawdown: {dd['max_drawdown_pct']}% (trough: {dd['trough_date']}, recovery: {recovery})")

    ra = summary["risk_adjusted"]
    if ra:
        parts = []
        if ra["sharpe"] is not None:
            parts.append(f"Sharpe: {ra['sharpe']}")
        if ra["sortino"] is not None:
            parts.append(f"Sortino: {ra['sortino']}")
        if parts:
            lines.append(f"Risk-adjusted returns (annualized): {', '.join(parts)}")

    bt = summary["backtest"]
    if bt:
        lines.append(f"Backtest ({bt['period']}): portfolio {bt['portfolio_return_pct']}% vs 100% VTI {bt['vti_baseline_return_pct']}% (alpha: {bt['alpha_pct']}%)")

    mc = summary["monte_carlo"]
    if mc:
        p = mc["percentiles"]
        lines.append(f"\nMonte Carlo simulation ({mc['simulations']} runs, {mc['days_ahead']} trading days):")
        lines.append(f"  Current value: ${mc['current_value']}")
        lines.append(f"  Outcomes: 5th%=${p['5th']}, 25th%=${p['25th']}, 50th%=${p['50th']}, 75th%=${p['75th']}, 95th%=${p['95th']}")
        lines.append(f"  Probability of loss: {mc['prob_loss']}%")
        lines.append(f"  Expected return: {mc['expected_return_pct']}%")

    return "\n".join(lines)
