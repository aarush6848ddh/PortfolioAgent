"""Shared quantitative metric primitives.

Single source of truth for Sharpe, Sortino, beta, and drawdown so the agent
path (quant.py) and the dashboard path (api/main.py) can never disagree again.
Conventions applied everywhere:
  - sample standard deviation (ddof=1) — a return series is a sample of the
    underlying return process, not the full population
  - simple daily returns (p[t] / p[t-1] - 1)
  - 252 trading days per year for annualization
"""
import os
import numpy as np

TRADING_DAYS_PER_YEAR = 252
DDOF = 1  # sample std everywhere
RISK_FREE_RATE = float(os.environ.get("RISK_FREE_RATE", "0.05"))
DAILY_RF = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR

# A ticker needs at least this many daily closes before it enters
# portfolio-level aggregates. A short-history holding would otherwise collapse
# the shared date window for the whole portfolio (see api/main.py, quant.py).
MIN_HISTORY_DAYS = 60

# Trailing window (calendar days) both the agent path (quant.py) and the
# dashboard path (api/main.py) pull history over. A bounded ~1-year window is
# the natural denominator for annualized metrics; all-history would keep growing
# and silently mix ever-older regimes. quant.py already used 365 for
# get_daily_closes / beta / correlations — this makes it the single source.
LOOKBACK_DAYS = 365


def daily_returns(prices):
    """Simple daily returns from a 1-D price (or value) series."""
    prices = np.asarray(prices, dtype=float)
    return np.diff(prices) / prices[:-1]


def log_returns(prices):
    """Log daily returns from a 1-D price (or value) series.

    Used for the Monte Carlo drift: modeling log returns as Normal and taking
    the price path as exp(cumsum(...)) is geometric-Brownian-motion consistent,
    so the median terminal value isn't biased upward the way an arithmetic-mean
    drift in a cumprod(1+r) model is.
    """
    prices = np.asarray(prices, dtype=float)
    return np.diff(np.log(prices))


def sharpe_ratio(returns, daily_rf=DAILY_RF):
    """Annualized Sharpe ratio. None when there is no dispersion to divide by."""
    excess = np.asarray(returns, dtype=float) - daily_rf
    sd = np.std(excess, ddof=DDOF)
    if not np.isfinite(sd) or sd == 0:
        return None
    return float(np.mean(excess) / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(returns, daily_rf=DAILY_RF):
    """Annualized Sortino ratio (downside deviation of below-rf excess returns)."""
    excess = np.asarray(returns, dtype=float) - daily_rf
    downside = excess[excess < 0]
    if len(downside) == 0:
        return None
    dsd = np.std(downside, ddof=DDOF)
    if not np.isfinite(dsd) or dsd == 0:
        return None
    return float(np.mean(excess) / dsd * np.sqrt(TRADING_DAYS_PER_YEAR))


def beta(asset_returns, benchmark_returns):
    """Beta of an asset/portfolio return series against a benchmark series."""
    a = np.asarray(asset_returns, dtype=float)
    b = np.asarray(benchmark_returns, dtype=float)
    var = np.var(b, ddof=DDOF)
    if not np.isfinite(var) or var == 0:
        return None
    cov = np.cov(a, b, ddof=DDOF)[0, 1]
    return float(cov / var)


def max_drawdown(series):
    """Max drawdown of a value (or cumulative-return) series.

    Returns a dict with the drawdown percentage, the index of the trough, and
    the full drawdown array. Callers map trough_index back to their own dates
    and derive recovery windows, since date handling differs per caller.
    """
    values = np.asarray(series, dtype=float)
    running_max = np.maximum.accumulate(values)
    drawdowns = (values - running_max) / running_max
    return {
        "max_drawdown_pct": float(np.min(drawdowns) * 100),
        "trough_index": int(np.argmin(drawdowns)),
        "drawdowns": drawdowns,
    }
